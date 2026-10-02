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
from sklearn.ensemble import IsolationForest
from sklearn.metrics import (average_precision_score, brier_score_loss, confusion_matrix, f1_score,
                             precision_recall_fscore_support, roc_auc_score)

from ferot import config
from ferot.features.evidence import FEATURES, GRAPH_FEATURES, TEXT_FEATURES, CaseHistory, build_evidence
from ferot.features.ledger import load_ledger
from ferot.models.classifier import CLASSES, CaseClassifier, keyword_baseline, make_model
from ferot.models.extract import extract_rules
from ferot.models.guard import ANOMALY_FEATURES, GUARD_FEATURES, Guard, guard_features
from ferot.models.guard import make_model as make_guard_model
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


URBAN = {"Dhaka", "Chattogram", "Gazipur", "Narayanganj"}


def _slices(frame: pd.DataFrame, wallets: pd.DataFrame, who: str) -> pd.DataFrame:
    w = wallets.set_index("wallet_no")
    out = frame.copy()
    out["age_band"] = out[who].map(w["age_band"]).fillna("unknown")
    out["area"] = np.where(out[who].map(w["district"]).isin(URBAN), "urban", "rural")
    out["kyc"] = out[who].map(w["kyc_level"]).fillna("unknown")
    return out


def fairness_report(test: pd.DataFrame, proba: np.ndarray, cases: pd.DataFrame, wallets: pd.DataFrame) -> dict:
    """M4 errors by customer group. The harmful error is a genuine or scam case recommended for rejection."""
    t = test.copy()
    t["pred"] = [CLASSES[i] for i in proba.argmax(axis=1)]
    t["conf"] = proba.max(axis=1)
    c = cases.set_index("case_id")
    t["claimant"] = t["case_id"].map(c["claimant"])
    t["language"] = t["case_id"].map(c["text_language"])
    t["channel"] = t["case_id"].map(c["channel"])
    t = _slices(t, wallets, "claimant")
    victims = t["case_type"].isin(["genuine_wrong_send", "scam_victim"])
    t["wrongful"] = victims & t["pred"].isin(["false_claim", "double_recovery"]) & (t["conf"] >= 0.7)
    out = {}
    for col in ("language", "channel", "age_band", "area", "kyc"):
        rows = {}
        for g, d in t.groupby(col):
            scam = d[d["case_type"] == "scam_victim"]
            vic = d[d["case_type"].isin(["genuine_wrong_send", "scam_victim"])]
            rows[str(g)] = {"n": int(len(d)), "accuracy": round(float((d["pred"] == d["case_type"]).mean()), 3),
                            "scam_recall": round(float((scam["pred"] == "scam_victim").mean()), 3) if len(scam) else None,
                            "wrongful_rejection_rate": round(float(vic["wrongful"].mean()), 3) if len(vic) else None}
        acc = [r["accuracy"] for r in rows.values() if r["n"] >= 10]
        out[col] = {"groups": rows, "max_accuracy_gap": round(max(acc) - min(acc), 3) if acc else None}
    return out


def alerting_metrics(test: pd.DataFrame, proba: np.ndarray) -> dict:
    """The playbook's questions for the scam class: how many caught, how many false alarms."""
    thr = next(r["when"]["min_prob"] for r in config.policy_rules()["rules"] if r["id"] == "R-SCAM-01")
    y = (test["case_type"] == "scam_victim").to_numpy().astype(int)
    p = proba[:, CLASSES.index("scam_victim")]
    top = proba.argmax(axis=1) == CLASSES.index("scam_victim")
    flag = top & (p >= thr)
    victims = test["case_type"].isin(["genuine_wrong_send", "scam_victim"]).to_numpy()
    harmful = victims & np.isin(proba.argmax(axis=1), [CLASSES.index("false_claim"), CLASSES.index("double_recovery")]) \
        & (proba.max(axis=1) >= 0.7)
    return {"policy_threshold": thr, "scam_pr_auc": round(float(average_precision_score(y, p)), 4),
            "scam_precision_at_policy": round(float(y[flag].mean()) if flag.any() else 0.0, 4),
            "scam_recall_at_policy": round(float(flag[y == 1].mean()), 4),
            "false_alarm_rate_non_scam": round(float(flag[y == 0].mean()), 4),
            "wrongful_rejections": int(harmful.sum()), "victim_cases": int(victims.sum()),
            "note": ("Case-level task: every row is a complaint, so classes are balanced by design. A PR-AUC near 1.0 "
                     "means the synthetic scam pattern is very clean; expect lower on real data.")}


def train_guard(ledger, seed: int = 42) -> tuple[Guard, dict]:
    """Ferot Guard on transfer-level data: every send is scored as it happens (heavily imbalanced)."""
    cases = ledger.world.cases
    history = CaseHistory(cases)
    rng = np.random.default_rng(seed)
    sp = config.assumptions()["splits"]
    scam = cases[cases["case_type"] == "scam_victim"]
    typo_cases = cases[(cases["case_type"] == "genuine_wrong_send") & (cases["intended_number"] != "")]
    disputed = set(cases["disputed_trx_id"])
    tx = ledger.tx
    owner = dict(zip(ledger.world.wallets["wallet_no"], ledger.world.wallets["owner_type"]))
    normal = tx[(tx["type"] == "send_money") & ~tx["trx_id"].isin(disputed) & (tx["status"] == "success")]
    normal = normal[normal["sender"].map(owner) == "customer"]
    normal = normal.iloc[rng.choice(len(normal), size=min(7000, len(normal)), replace=False)]

    rows = []
    for _, c in scam.iterrows():
        rows.append((c["claimant"], c["recipient"], float(c["amount"]), int(c["transfer_minute"]), 1, "scam"))
    for _, c in typo_cases.iterrows():
        rows.append((c["claimant"], c["recipient"], float(c["amount"]), int(c["transfer_minute"]), 0, "typo"))
    for r in normal.itertuples(index=False):
        rows.append((r.sender, r.receiver, float(r.amount), int(r.minute), 0, "normal"))
    typo_cfg = config.load_yaml("guard.yaml")["typo"]
    feats = []
    for sender, recipient, amount, minute, y, kind in rows:
        f = guard_features(ledger, history, sender, recipient, amount, minute)
        typo_flag = int(f["first_ever"] and f["intended_found"] and f["intended_distance"] <= typo_cfg["max_distance"]
                        and f["_intended"]["count"] >= typo_cfg["min_earlier_sends"])
        row = {k: v for k, v in f.items() if not k.startswith("_")}
        row.update({"y": y, "kind": kind, "sender": sender, "day": minute // 1440, "typo_flag": typo_flag})
        feats.append(row)
    d = pd.DataFrame(feats)
    d["split"] = np.where(d["day"] < sp["train_days"][1], "train",
                          np.where(d["day"] < sp["valid_days"][1], "valid", "test"))
    fit = d[d["kind"] != "typo"]
    tr, va, te = (fit[fit["split"] == name] for name in ("train", "valid", "test"))

    model = make_guard_model(seed)
    model.fit(tr[GUARD_FEATURES].astype(float), tr["y"], eval_set=[(va[GUARD_FEATURES].astype(float), va["y"])],
              callbacks=[lgb.early_stopping(40, verbose=False)])
    iso = IsolationForest(n_estimators=200, contamination="auto", random_state=seed)
    base = tr[tr["y"] == 0][ANOMALY_FEATURES].astype(float)
    iso.fit(base)
    raw = -iso.score_samples(base)
    scale = (float(np.percentile(raw, 1)), float(np.percentile(raw, 99)))

    best = (-1.0, 1.0, 0.0)  # fusion weight chosen on the validation window
    for wa in (0.0, 0.1, 0.2, 0.3, 0.4):
        g = Guard(model, iso, scale, (1 - wa, wa))
        ap = average_precision_score(va["y"], g.risk(va.to_dict("records")))
        if ap > best[0] + 1e-6:
            best = (ap, 1 - wa, wa)
    guard = Guard(model, iso, scale, (best[1], best[2]))
    vf = guard.fused(va.to_dict("records"))
    vn = vf[va["y"].to_numpy() == 0]
    cut_warn = float(np.quantile(vn, 0.99))     # about 1 in 100 innocent transfers warned
    cut_review = float(np.quantile(vn, 0.999))  # about 1 in 1,000 paused
    cut_review = max(cut_review, cut_warn * 1.5)
    guard = Guard(model, iso, scale, (best[1], best[2]), (cut_warn, cut_review))

    risk = guard.risk(te.to_dict("records"))
    y = te["y"].to_numpy()
    bands = config.load_yaml("guard.yaml")["bands"]
    warn, review = risk >= bands["warn_at"], risk >= bands["review_at"]
    model_only = Guard(model, iso, scale, (1.0, 0.0), (cut_warn, cut_review)).risk(te.to_dict("records"))
    typo_te = d[(d["kind"] == "typo") & (d["split"] == "test")]
    normals = te[te["y"] == 0].copy()
    metrics = {
        "test_transfers": int(len(te)), "test_scams": int(y.sum()), "scam_share": round(float(y.mean()), 4),
        "pr_auc": round(float(average_precision_score(y, risk)), 4),
        "pr_auc_model_only": round(float(average_precision_score(y, model_only)), 4),
        "roc_auc": round(float(roc_auc_score(y, risk)), 4),
        "recall_at_warn": round(float(warn[y == 1].mean()), 4),
        "recall_at_review": round(float(review[y == 1].mean()), 4),
        "precision_at_warn": round(float(y[warn].mean()) if warn.any() else 0.0, 4),
        "precision_at_review": round(float(y[review].mean()) if review.any() else 0.0, 4),
        "innocent_warned_per_100": round(float(warn[y == 0].mean() * 100), 2),
        "innocent_reviewed_per_100": round(float(review[y == 0].mean() * 100), 2),
        "typo_caught_rate": round(float(typo_te["typo_flag"].mean()), 4) if len(typo_te) else None,
        "typo_false_alarm_per_100_normal": round(float(normals["typo_flag"].mean() * 100), 2),
        "fusion": {"w_model": round(best[1], 2), "w_anomaly": round(best[2], 2), "valid_pr_auc": round(best[0], 4)},
        "band_cuts": {"warn_score": round(cut_warn, 6), "review_score": round(cut_review, 6),
                      "rule": "set on validation normals: 99th and 99.9th percentile of the fused score"},
        "bands": bands,
    }
    normals["warned"] = warn[y == 0]
    normals = _slices(normals, ledger.world.wallets, "sender")
    normals["channel"] = normals["sender"].map(ledger.world.wallets.set_index("wallet_no")["channel"])
    fair = {}
    for col in ("channel", "age_band", "area"):
        g = normals.groupby(col)["warned"].agg(["mean", "size"])
        fair[col] = {str(k): {"n": int(v["size"]), "innocent_warned_per_100": round(float(v["mean"] * 100), 2)}
                     for k, v in g.iterrows()}
    metrics["fairness"] = fair
    return guard, metrics


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

    test_proba = clf.predict_proba(test.to_dict("records"))
    ledger = load_ledger()
    fairness = fairness_report(test, test_proba, ledger.world.cases, ledger.world.wallets)
    alerting = alerting_metrics(test, test_proba)
    guard, guard_metrics = train_guard(ledger)

    genuine = table[table["case_type"] == "genuine_wrong_send"]
    m3 = {"top1_accuracy_on_genuine_typos": round(float(genuine["intended_ok"].astype(float).mean()), 4)}
    nongen = table[table["case_type"] != "genuine_wrong_send"]
    m3["false_match_rate_other_cases"] = round(float(nongen["intended_found"].mean()), 4)

    metrics.update({"m4_alerting": alerting, "fairness": fairness, "guard": guard_metrics,
                    "m3_intended_number": m3, "m4_classifier": m4, "m4_baselines": baselines,
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
        "m4_scam_recall_at_policy": alerting["scam_recall_at_policy"],
        "guard_pr_auc": guard_metrics["pr_auc"], "guard_recall_at_warn": guard_metrics["recall_at_warn"],
        "guard_innocent_warned_per_100": guard_metrics["innocent_warned_per_100"],
        "guard_typo_caught": guard_metrics["typo_caught_rate"],
        "max_accuracy_gap_by_channel": fairness["channel"]["max_accuracy_gap"],
    }

    s.artifact_dir.mkdir(parents=True, exist_ok=True)
    with open(s.artifact_dir / "models.pkl", "wb") as fh:
        pickle.dump({"classifier": clf, "recoverability": Recoverability(rec_models), "guard": guard,
                     "version": MODEL_VERSION}, fh)
    reports = config.ROOT / "reports"
    reports.mkdir(exist_ok=True)
    (reports / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    (s.artifact_dir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    table.to_parquet(s.artifact_dir / "feature_table.parquet", index=False)
    return metrics


def load_models() -> dict:
    with open(config.settings().artifact_dir / "models.pkl", "rb") as fh:
        return pickle.load(fh)
