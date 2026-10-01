"""Train M4 and M5 on the synthetic world and write honest metrics against baselines.

Train on days 0-60 (with 5% label noise), stop early on days 60-75, report on days 75-90.
The test window also contains a scam variant (job offers) the models never saw in training.
"""

from __future__ import annotations

import json
import pickle
import warnings

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import (brier_score_loss, confusion_matrix, f1_score, precision_recall_fscore_support,
                             roc_auc_score)

from ferot import config
from ferot.features.evidence import FEATURES, GRAPH_FEATURES, TEXT_FEATURES, CaseHistory, build_evidence
from ferot.features.ledger import load_ledger
from ferot.models.classifier import CLASSES, CaseClassifier, keyword_baseline, make_model
from ferot.models.extract import extract_rules
from ferot.models.matcher import match_transaction
from ferot.models.recoverability import HORIZONS_MIN, REC_FEATURES, Recoverability
from ferot.models.recoverability import make_model as make_rec_model

MODEL_VERSION = "ferot-2026.10.01"
warnings.filterwarnings("ignore", message=".*'eval_set' is deprecated.*")


def build_table() -> tuple[pd.DataFrame, dict]:
    ledger = load_ledger()
    cases = ledger.world.cases
    history = CaseHistory(cases)
    rows, extraction_hits = [], {"amount": [], "number": [], "lang": []}
    match_hits = []
    for _, c in cases.iterrows():
        e = extract_rules(c["complaint_text"])
        m = match_transaction(ledger, c["claimant"], e, int(c["complaint_minute"]))
        match_hits.append(m["trx_id"] == c["disputed_trx_id"])
        extraction_hits["amount"].append(e.amount is not None and abs(e.amount - c["stated_amount"]) < 1)
        stated = str(c["stated_number"])
        extraction_hits["number"].append((e.number == stated) if len(stated) == 11 else (e.number_last4 == stated))
        extraction_hits["lang"].append(c["text_language"])
        ev = build_evidence(ledger, c["claimant"], c["disputed_trx_id"], int(c["complaint_minute"]), e, history)
        row = dict(ev.features)
        row.update({"case_id": c["case_id"], "case_type": c["case_type"], "label_train": c["label_train"],
                    "split": c["split"], "variant": c["variant"], "golden": c["golden"],
                    "recoverable_now": ev.recoverable_now, "amount": float(c["amount"]),
                    "intended_ok": ev.intended.get("candidate") == c["intended_number"] if c["intended_number"] else None})
        tx_row = ledger.row(c["disputed_trx_id"])
        recipient = str(tx_row["receiver"])
        for h in HORIZONS_MIN:
            hold = min(float(c["amount"]), max(ledger.balance_at(recipient, int(c["complaint_minute"]) + h), 0.0))
            row[f"held_{h}"] = int(hold >= 0.5 * float(c["amount"])) if not row["tech_failure"] else np.nan
        rows.append(row)
    table = pd.DataFrame(rows)
    lang = np.array(extraction_hits["lang"])
    m1 = {"amount_accuracy": float(np.mean(extraction_hits["amount"])),
          "number_accuracy": float(np.mean(extraction_hits["number"])),
          "by_language": {l: {"amount": float(np.mean(np.array(extraction_hits["amount"])[lang == l])),
                              "number": float(np.mean(np.array(extraction_hits["number"])[lang == l]))}
                          for l in sorted(set(lang))}}
    return table, {"m1_extraction": m1, "m2_matching": {"top1_accuracy": float(np.mean(match_hits))}}


def _ece(proba: np.ndarray, y_true_idx: np.ndarray, bins: int = 10) -> float:
    conf = proba.max(axis=1)
    pred = proba.argmax(axis=1)
    ece = 0.0
    for lo in np.linspace(0, 1, bins, endpoint=False):
        mask = (conf > lo) & (conf <= lo + 1 / bins)
        if mask.any():
            ece += mask.mean() * abs((pred[mask] == y_true_idx[mask]).mean() - conf[mask].mean())
    return float(ece)


def _fit_classifier(train: pd.DataFrame, valid: pd.DataFrame, features: list[str]):
    model = make_model()
    model.fit(train[features].astype(float), train["label_train"],
              eval_set=[(valid[features].astype(float), valid["label_train"])],
              callbacks=[lgb.early_stopping(40, verbose=False)])
    return CaseClassifier(model, features)


def _classifier_report(clf: CaseClassifier, test: pd.DataFrame) -> dict:
    proba = clf.predict_proba(test.to_dict("records"))
    pred = [CLASSES[i] for i in proba.argmax(axis=1)]
    y = test["case_type"].tolist()
    p, r, f, _ = precision_recall_fscore_support(y, pred, labels=CLASSES, zero_division=0)
    return {
        "macro_f1": round(float(f1_score(y, pred, labels=CLASSES, average="macro")), 4),
        "per_class": {c: {"precision": round(float(p[i]), 3), "recall": round(float(r[i]), 3), "f1": round(float(f[i]), 3)}
                      for i, c in enumerate(CLASSES)},
        "ece": round(_ece(proba, np.array([CLASSES.index(t) for t in y])), 4),
        "confusion_matrix": {"labels": CLASSES, "matrix": confusion_matrix(y, pred, labels=CLASSES).tolist()},
    }


def train_all() -> dict:
    s = config.settings()
    table, metrics = build_table()
    train = table[table["split"] == "train"]
    valid = table[table["split"] == "valid"]
    test = table[table["split"] == "test"]

    clf = _fit_classifier(train, valid, FEATURES)
    m4 = _classifier_report(clf, test)
    job = test[test["variant"] == "job_offer"]
    if len(job):
        jp = clf.predict_proba(job.to_dict("records")).argmax(axis=1)
        m4["held_out_job_offer_scam_recall"] = round(float(np.mean([CLASSES[i] == "scam_victim" for i in jp])), 3)

    kw_pred = [keyword_baseline(r) for r in test.to_dict("records")]
    baselines = {
        "keyword_rules_macro_f1": round(float(f1_score(test["case_type"], kw_pred, labels=CLASSES, average="macro")), 4),
        "text_only_model": _classifier_report(_fit_classifier(train, valid, TEXT_FEATURES), test)["macro_f1"],
        "without_graph_features": _classifier_report(
            _fit_classifier(train, valid, [f for f in FEATURES if f not in GRAPH_FEATURES]), test)["macro_f1"],
        "without_text_features": _classifier_report(
            _fit_classifier(train, valid, [f for f in FEATURES if f not in TEXT_FEATURES]), test)["macro_f1"],
    }

    rec_models, m5 = {}, {}
    for h in HORIZONS_MIN:
        col = f"held_{h}"
        tr, va, te = (d[d[col].notna()] for d in (train, valid, test))
        model = make_rec_model()
        model.fit(tr[REC_FEATURES].astype(float), tr[col].astype(int),
                  eval_set=[(va[REC_FEATURES].astype(float), va[col].astype(int))],
                  callbacks=[lgb.early_stopping(30, verbose=False)])
        rec_models[h] = model
        p = model.predict_proba(te[REC_FEATURES].astype(float))[:, 1]
        base = (te["recoverable_share_now"] >= 0.5).astype(float)
        yt = te[col].astype(int)
        m5[f"{h}min"] = {"brier_model": round(float(brier_score_loss(yt, p)), 4),
                         "brier_baseline_balance_now": round(float(brier_score_loss(yt, base)), 4),
                         "auc_model": round(float(roc_auc_score(yt, p)), 4) if yt.nunique() > 1 else None,
                         "positives": int(yt.sum()), "n": int(len(yt))}

    genuine = table[table["case_type"] == "genuine_wrong_send"]
    m3 = {"top1_accuracy_on_genuine_typos": round(float(genuine["intended_ok"].astype(float).mean()), 4)}
    nongen = table[table["case_type"] != "genuine_wrong_send"]
    m3["false_match_rate_other_cases"] = round(float(nongen["intended_found"].mean()), 4)

    metrics.update({"m3_intended_number": m3, "m4_classifier": m4, "m4_baselines": baselines,
                    "m5_recoverability": m5, "model_version": MODEL_VERSION,
                    "data": {"cases": int(len(table)), "train": int(len(train)), "valid": int(len(valid)),
                             "test": int(len(test)), "label_noise": config.assumptions()["cases"]["label_noise"]}})
    metrics["summary"] = {
        "m1_amount_accuracy": round(metrics["m1_extraction"]["amount_accuracy"], 3),
        "m1_number_accuracy": round(metrics["m1_extraction"]["number_accuracy"], 3),
        "m2_match_top1": round(metrics["m2_matching"]["top1_accuracy"], 3),
        "m3_intended_top1": m3["top1_accuracy_on_genuine_typos"],
        "m4_macro_f1": m4["macro_f1"], "m4_scam_recall": m4["per_class"]["scam_victim"]["recall"],
        "keyword_baseline_macro_f1": baselines["keyword_rules_macro_f1"],
        "text_only_macro_f1": baselines["text_only_model"],
        "m5_brier_6h_model_vs_baseline": [m5["360min"]["brier_model"], m5["360min"]["brier_baseline_balance_now"]],
    }

    s.artifact_dir.mkdir(parents=True, exist_ok=True)
    with open(s.artifact_dir / "models.pkl", "wb") as fh:
        pickle.dump({"classifier": clf, "recoverability": Recoverability(rec_models), "version": MODEL_VERSION}, fh)
    reports = config.ROOT / "reports"
    reports.mkdir(exist_ok=True)
    (reports / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    (s.artifact_dir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    table.to_parquet(s.artifact_dir / "feature_table.parquet", index=False)
    return metrics


def load_models() -> dict:
    with open(config.settings().artifact_dir / "models.pkl", "rb") as fh:
        return pickle.load(fh)
