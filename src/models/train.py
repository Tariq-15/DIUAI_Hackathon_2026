"""Train every model on TRAIN, tune on VAL-FIT, fit fusion/bands on VAL-CAL. TEST is not read.

    python -m src.models.train                 # Optuna trials from config (30)
    python -m src.models.train --trials 0      # skip tuning, use config params

Time split (from config, 1-based days):  train 1-40 | val_fit 41-45 | val_cal 46-50 | test 51-60
"""
from __future__ import annotations

import argparse
import time

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.isotonic import IsotonicRegression
from xgboost import XGBClassifier

from src.common.config import load_config, resolve, save_json
from src.features.spec import ALL_FEATURES, ANOMALY_FEATURES, CATEGORICAL
from .baselines import isflagged_baseline, logistic, rules_score
from .fusion import ScoreMapper, fit_weights, fuse, graph_score, policy_bands
from .metrics import band_report, summary
from .scoring import BUNDLE, X_of


def load_splits(cfg, features_path=None):
    p = features_path or resolve(cfg, "features_dir") / "features.parquet"
    df = pd.read_parquet(p)
    df = df[df.scored].reset_index(drop=True)
    v0, v1 = cfg["splits"]["val_days"]
    mid = (v0 + v1) // 2                                   # 1-based last day of val_fit
    day1 = df.day + 1
    df["subsplit"] = np.where(df.split == "val", np.where(day1 <= mid, "val_fit", "val_cal"), df.split)
    return df


def lgbm_model(params: dict, n_estimators: int, seed: int):
    return lgb.LGBMClassifier(objective="binary", n_estimators=n_estimators, random_state=seed, n_jobs=-1,
                              verbose=-1, **params)


def fit_lgbm(params, Xtr, ytr, Xva, yva, seed, n_estimators=3000, es=100):
    m = lgbm_model(params, n_estimators, seed)
    m.fit(Xtr, ytr, eval_set=[(Xva, yva)], eval_metric="average_precision",
          categorical_feature=[c for c in CATEGORICAL if c in Xtr.columns],
          callbacks=[lgb.early_stopping(es, verbose=False)])
    return m


def tune(Xtr, ytr, Xva, yva, base: dict, trials: int, seed: int):
    if trials <= 0:
        return base, None
    import optuna
    from sklearn.metrics import average_precision_score
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    neg_pos = float((ytr == 0).sum() / max(ytr.sum(), 1))

    def objective(trial):
        params = dict(
            learning_rate=trial.suggest_float("learning_rate", 0.02, 0.12, log=True),
            num_leaves=trial.suggest_int("num_leaves", 15, 127, log=True),
            min_child_samples=trial.suggest_int("min_child_samples", 10, 300, log=True),
            subsample=trial.suggest_float("subsample", 0.5, 1.0), subsample_freq=1,
            colsample_bytree=trial.suggest_float("colsample_bytree", 0.4, 1.0),
            reg_lambda=trial.suggest_float("reg_lambda", 1e-3, 20, log=True),
            min_split_gain=trial.suggest_float("min_split_gain", 0.0, 1.0),
            scale_pos_weight=trial.suggest_float("scale_pos_weight", 1.0, min(neg_pos, 200.0), log=True),
        )
        m = fit_lgbm(params, Xtr, ytr, Xva, yva, seed, n_estimators=2000, es=80)
        trial.set_user_attr("best_iter", int(m.best_iteration_ or m.n_estimators))
        return average_precision_score(yva, m.predict_proba(Xva)[:, 1])

    study = optuna.create_study(direction="maximize", sampler=optuna.samplers.TPESampler(seed=seed))
    study.optimize(objective, n_trials=trials, show_progress_bar=False)
    best = dict(study.best_params)
    best["subsample_freq"] = 1
    hist = [dict(number=t.number, value=t.value, **t.params) for t in study.trials]
    return best, dict(best_value=study.best_value, trials=hist)


def train(cfg, features_path=None, trials=None, verbose=True):
    log = (lambda *a: print(*a, flush=True)) if verbose else (lambda *a: None)
    seed = cfg["seed"]
    mc = cfg["model"]
    t_all = time.time()
    df = load_splits(cfg, features_path)
    tr, vf, vc = (df[df.subsplit == s] for s in ("train", "val_fit", "val_cal"))
    log(f"[train] rows train={len(tr):,} (fraud {int(tr.is_fraud.sum())}) val_fit={len(vf):,} "
        f"({int(vf.is_fraud.sum())}) val_cal={len(vc):,} ({int(vc.is_fraud.sum())}); test not loaded into training")
    Xtr, Xvf, Xvc = X_of(tr), X_of(vf), X_of(vc)
    ytr, yvf, yvc = tr.is_fraud.values, vf.is_fraud.values, vc.is_fraud.values

    # ---------------- supervised: LightGBM (+ Optuna)
    base = {k: v for k, v in mc["lgbm"].items() if k not in ("n_estimators", "early_stopping_rounds")}
    base["scale_pos_weight"] = float(np.sqrt((ytr == 0).sum() / max(ytr.sum(), 1)))
    n_trials = mc["optuna_trials"] if trials is None else trials
    t0 = time.time()
    params, study = tune(Xtr, ytr, Xvf, yvf, base, n_trials, seed)
    log(f"[train] tuning: {n_trials} trials in {time.time() - t0:.0f}s"
        + (f", best val_fit PR-AUC {study['best_value']:.4f}" if study else " (skipped)"))
    t0 = time.time()
    lgbm = fit_lgbm(params, Xtr, ytr, Xvf, yvf, seed, mc["lgbm"]["n_estimators"] * 2, mc["lgbm"]["early_stopping_rounds"])
    log(f"[train] LightGBM: {lgbm.best_iteration_} trees in {time.time() - t0:.0f}s")

    # ---------------- comparison models
    t0 = time.time()
    spw = float(np.sqrt((ytr == 0).sum() / max(ytr.sum(), 1)))
    xgb = XGBClassifier(tree_method="hist", n_estimators=2000, learning_rate=0.05, max_depth=7, subsample=0.8,
                        colsample_bytree=0.8, min_child_weight=3, scale_pos_weight=spw, eval_metric="aucpr",
                        early_stopping_rounds=100, random_state=seed, n_jobs=-1)
    xgb.fit(Xtr, ytr, eval_set=[(Xvf, yvf)], verbose=False)
    log(f"[train] XGBoost: {xgb.best_iteration} trees in {time.time() - t0:.0f}s")
    t0 = time.time()
    logit = logistic(Xtr, ytr, seed)
    log(f"[train] logistic regression in {time.time() - t0:.0f}s")

    # ---------------- unsupervised: Isolation Forest on behaviour-deviation features (labels unused)
    t0 = time.time()
    A = tr[ANOMALY_FEATURES].astype(float)
    fill = A.median()
    ic = mc["isolation_forest"]
    iforest = IsolationForest(n_estimators=ic["n_estimators"], max_samples=ic["max_samples"], random_state=seed,
                              n_jobs=-1).fit(A.fillna(fill).to_numpy())
    raw_tr = -iforest.score_samples(A.fillna(fill).to_numpy())
    if_ref = np.quantile(raw_tr, np.linspace(0, 1, 1001))
    log(f"[train] Isolation Forest in {time.time() - t0:.0f}s")

    def anom(d):
        r = -iforest.score_samples(d[ANOMALY_FEATURES].astype(float).fillna(fill).to_numpy())
        return np.interp(r, if_ref, np.linspace(0, 1, len(if_ref)))

    # ---------------- fusion + calibration + bands on VAL-CAL
    p_vc = lgbm.predict_proba(Xvc)[:, 1]
    a_vc, g_vc = anom(vc), graph_score(vc)
    weights, wfit = fit_weights(yvc, p_vc, a_vc, g_vc, fpr_target=cfg["policy"]["target_fpr"]["STEP_UP"])
    fused_vc = fuse(weights, p_vc, a_vc, g_vc)
    mapper = ScoreMapper.fit(fused_vc, yvc, cfg["policy"]["target_fpr"], cfg["policy"]["bands"],
                             cfg["policy"].get("target_precision"))
    calibrator = IsotonicRegression(out_of_bounds="clip", y_min=0, y_max=1).fit(p_vc, yvc)
    log(f"[train] fusion weights {weights} (val_cal recall@0.5%FPR={wfit['recall_at_fpr']:.3f}); "
        f"score knots {np.round(mapper.kx, 4).tolist()}")

    # ---------------- validation report (VAL-CAL)
    comps = {
        "rules_baseline": rules_score(vc), "paysim_isFlagged_rule": isflagged_baseline(vc),
        "logistic_regression": logit.predict_proba(Xvc)[:, 1], "xgboost": xgb.predict_proba(Xvc)[:, 1],
        "lightgbm": p_vc, "isolation_forest": a_vc, "graph_rules": g_vc, "fused_prohori": fused_vc,
    }
    val_rows = [summary(yvc, s, k) for k, s in comps.items()]
    score_vc = mapper(fused_vc)
    cap = cfg["policy"].get("established_parties_cap", True)
    floors = cfg["policy"].get("evidence_floors", True)
    bands_vc = pd.DataFrame({"band": policy_bands(vc, score_vc, cfg["policy"]["bands"], cap, floors)[0], "is_fraud": yvc})
    imp = pd.Series(lgbm.booster_.feature_importance("gain"), index=ALL_FEATURES).sort_values(ascending=False)
    bundle = dict(features=ALL_FEATURES, lgbm=lgbm, params=params, xgb=xgb, logit=logit, iforest=iforest, if_fill=fill,
                  if_ref=if_ref, weights=weights, mapper=mapper.to_dict(), calibrator=calibrator,
                  bands=cfg["policy"]["bands"], target_fpr=cfg["policy"]["target_fpr"], established_parties_cap=cap,
                  evidence_floors=floors,
                  target_precision=cfg["policy"].get("target_precision"),
                  trained_rows=int(len(tr)), seed=seed)
    art = resolve(cfg, "artifacts_dir")
    joblib.dump(bundle, art / BUNDLE, compress=3)
    lgbm.booster_.save_model(str(art / "lgbm_model.txt"))
    report = dict(
        split_rows=dict(train=int(len(tr)), val_fit=int(len(vf)), val_cal=int(len(vc))),
        split_fraud=dict(train=int(ytr.sum()), val_fit=int(yvf.sum()), val_cal=int(yvc.sum())),
        lgbm_params=params, lgbm_trees=int(lgbm.best_iteration_ or 0), optuna=study and dict(
            best_value=study["best_value"], n_trials=len(study["trials"])),
        fusion_weights=weights, fusion_fit=wfit, score_mapper=mapper.to_dict(),
        val_cal_metrics=val_rows, val_cal_bands=band_report(bands_vc),
        top_features_gain=imp.head(30).round(1).to_dict(), seconds=round(time.time() - t_all, 1),
    )
    rep = resolve(cfg, "reports_dir")
    save_json(report, rep / "metrics_val.json")
    if study:
        pd.DataFrame(study["trials"]).to_csv(rep / "optuna_trials.csv", index=False)
    log("[train] VAL-CAL comparison:")
    log(pd.DataFrame(val_rows)[["model", "pr_auc", "roc_auc", "recall_at_fpr_0p5", "recall_at_fpr_2"]].to_string(index=False))
    log(f"[train] done in {report['seconds']}s -> {art / BUNDLE}")
    return bundle, report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=None)
    ap.add_argument("--features", default=None)
    ap.add_argument("--trials", type=int, default=None)
    ap.add_argument("--artifacts", default=None)
    ap.add_argument("--reports", default=None)
    a = ap.parse_args()
    cfg = load_config(a.config)
    if a.artifacts:
        cfg["paths"]["artifacts_dir"] = a.artifacts
    if a.reports:
        cfg["paths"]["reports_dir"] = a.reports
    train(cfg, a.features, a.trials)


if __name__ == "__main__":
    main()
