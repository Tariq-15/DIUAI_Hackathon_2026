"""
src/training/train.py
======================
Training pipeline for Prohori fraud detection.

Models trained:
  1. LightGBM (primary, fast on CPU)
  2. XGBoost  (secondary, for ensemble)
  3. Isolation Forest (unsupervised anomaly scorer)

Outputs saved to models/:
  lgbm_model.joblib
  xgb_model.joblib
  iso_forest.joblib
  feature_list.json
  training_report.txt

Usage:
    python -m src.training.train --data data/ --models models/ --tune
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
from sklearn.metrics import (average_precision_score, roc_auc_score,
                              precision_recall_curve, classification_report)
from sklearn.preprocessing import LabelEncoder
from joblib import dump, load

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.features.feature_store import replay_features


# ── Feature engineering pipeline ─────────────────────────────────────────────

CATEGORICAL_COLS = ["txn_type", "channel"]
FEATURE_COLS_BASIC = [
    "amount_tk", "fee_tk", "hour", "weekday",
    "is_new_device", "location_changed",
    "session_seconds", "pin_attempts", "counterparty_first_time",
    "amount_to_median_ratio", "balance_drain_ratio", "hour_deviation",
    "recipient_age_hours",
    "recipient_unique_senders_3h", "recipient_unique_senders_24h",
    "recipient_unique_senders_48h",
    "recipient_first_time_sender_ratio",
    "recipient_inflow_outflow_lag_min",
    "recipient_cashout_ratio",
    "agent_peer_zscore",
    "txn_type_enc", "channel_enc",
]


def prepare_features(feat_df: pd.DataFrame) -> pd.DataFrame:
    """Encode categoricals and select model columns."""
    df = feat_df.copy()

    for col in CATEGORICAL_COLS:
        if col in df.columns:
            le = LabelEncoder()
            df[f"{col}_enc"] = le.fit_transform(df[col].fillna("UNKNOWN").astype(str))

    # Clip extreme values
    df["amount_to_median_ratio"] = df["amount_to_median_ratio"].clip(0, 100)
    df["balance_drain_ratio"]    = df["balance_drain_ratio"].clip(0, 1)
    df["recipient_cashout_ratio"]= df["recipient_cashout_ratio"].clip(0, 5)
    df["agent_peer_zscore"]      = df["agent_peer_zscore"].clip(-5, 50)

    # Fill NaN
    df[FEATURE_COLS_BASIC] = df[FEATURE_COLS_BASIC].fillna(0)
    return df


# ── Time-based split ──────────────────────────────────────────────────────────

def time_split(txn_df: pd.DataFrame, lbl_df: pd.DataFrame):
    """
    Returns (train, valid, test) DataFrames merged with labels.
    Days 1-40 / 41-50 / 51-60.
    """
    txn = txn_df.copy()
    txn["timestamp"] = pd.to_datetime(txn["timestamp"])
    t_min = txn["timestamp"].min()

    txn["day_offset"] = (txn["timestamp"] - t_min).dt.days

    merged = txn.merge(lbl_df, on="txn_id", how="left")
    merged["is_fraud"] = merged["is_fraud"].fillna(0).astype(int)

    train = merged[merged["day_offset"] <= 39]
    valid = merged[(merged["day_offset"] >= 40) & (merged["day_offset"] <= 49)]
    test  = merged[merged["day_offset"] >= 50]

    print(f"   Train: {len(train):,}  Valid: {len(valid):,}  Test: {len(test):,}")
    print(f"   Train fraud: {train['is_fraud'].sum():,}  "
          f"Valid: {valid['is_fraud'].sum():,}  Test: {test['is_fraud'].sum():,}")
    return train, valid, test


# ── LightGBM ──────────────────────────────────────────────────────────────────

def train_lgbm(X_train, y_train, X_val, y_val, tune: bool = False):
    try:
        import lightgbm as lgb
    except ImportError:
        print("  LightGBM not installed. pip install lightgbm")
        return None

    base_params = dict(
        objective="binary",
        metric="average_precision",
        learning_rate=0.05,
        num_leaves=63,
        n_estimators=500,
        min_child_samples=20,
        subsample=0.8,
        colsample_bytree=0.8,
        scale_pos_weight=int((y_train == 0).sum() / max((y_train == 1).sum(), 1)),
        random_state=42,
        n_jobs=-1,
        verbose=-1,
    )

    if tune:
        try:
            import optuna
            optuna.logging.set_verbosity(optuna.logging.WARNING)

            def _objective(trial):
                params = {
                    "objective": "binary", "metric": "average_precision",
                    "learning_rate": trial.suggest_float("lr", 0.02, 0.2, log=True),
                    "num_leaves":    trial.suggest_int("nl", 31, 255),
                    "n_estimators":  trial.suggest_int("ne", 100, 800),
                    "min_child_samples": trial.suggest_int("mcs", 10, 50),
                    "subsample": trial.suggest_float("ss", 0.6, 1.0),
                    "scale_pos_weight": base_params["scale_pos_weight"],
                    "random_state": 42, "n_jobs": -1, "verbose": -1,
                }
                m = lgb.LGBMClassifier(**params)
                m.fit(X_train, y_train,
                      eval_set=[(X_val, y_val)],
                      callbacks=[lgb.early_stopping(30, verbose=False)])
                p = m.predict_proba(X_val)[:, 1]
                return average_precision_score(y_val, p)

            study = optuna.create_study(direction="maximize",
                                        sampler=optuna.samplers.TPESampler(seed=42))
            study.optimize(_objective, n_trials=30, show_progress_bar=True)
            base_params.update(study.best_params)
            print(f"   Best params: {study.best_params}")
        except ImportError:
            print("  optuna not installed; skipping tuning.")

    model = lgb.LGBMClassifier(**base_params)
    model.fit(X_train, y_train,
              eval_set=[(X_val, y_val)],
              callbacks=[lgb.early_stopping(50, verbose=False),
                         lgb.log_evaluation(100)])
    return model


# ── XGBoost ───────────────────────────────────────────────────────────────────

def train_xgb(X_train, y_train, X_val, y_val):
    try:
        from xgboost import XGBClassifier
    except ImportError:
        print("  XGBoost not installed. pip install xgboost")
        return None

    scale_pw = int((y_train == 0).sum() / max((y_train == 1).sum(), 1))
    model = XGBClassifier(
        n_estimators=400, learning_rate=0.05, max_depth=6,
        subsample=0.8, colsample_bytree=0.8,
        scale_pos_weight=scale_pw,
        use_label_encoder=False, eval_metric="aucpr",
        random_state=42, n_jobs=-1, verbosity=0,
    )
    model.fit(X_train, y_train,
              eval_set=[(X_val, y_val)],
              verbose=False)
    return model


# ── Isolation Forest ──────────────────────────────────────────────────────────

def train_iso_forest(X_train):
    from sklearn.ensemble import IsolationForest
    iso = IsolationForest(
        n_estimators=200, contamination=0.005,
        random_state=42, n_jobs=-1,
    )
    iso.fit(X_train)
    return iso


# ── Evaluation ────────────────────────────────────────────────────────────────

def evaluate(model, X, y, name: str, iso=None) -> dict:
    if model is None:
        return {}
    prob  = model.predict_proba(X)[:, 1]
    pr_auc = average_precision_score(y, prob)
    roc    = roc_auc_score(y, prob)

    # Anomaly score from isolation forest (optional)
    if iso is not None:
        iso_score = -iso.score_samples(X)   # higher = more anomalous
        iso_score = (iso_score - iso_score.min()) / (iso_score.max() - iso_score.min() + 1e-9)
        # Fusion (0.5 model + 0.3 anomaly + 0.2 graph=0)
        fused = 0.5 * prob + 0.3 * iso_score
    else:
        fused = prob

    # Precision at recall=0.80
    prec_arr, rec_arr, thr_arr = precision_recall_curve(y, fused)
    p_at_r80 = 0.0
    for p, r in zip(prec_arr, rec_arr):
        if r >= 0.80:
            p_at_r80 = p
            break

    print(f"\n  [{name}] PR-AUC={pr_auc:.4f}  ROC-AUC={roc:.4f}  "
          f"P@R80={p_at_r80:.4f}")

    # Threshold at 5% FAR
    n_neg = (y == 0).sum()
    for thr in np.arange(0.01, 1.0, 0.01):
        far = ((fused >= thr) & (y == 0)).sum() / max(n_neg, 1)
        if far <= 0.05:
            recall_at_far = ((fused >= thr) & (y == 1)).sum() / max((y == 1).sum(), 1)
            print(f"  Recall at 5% FAR: {recall_at_far:.3f}  (thr={thr:.2f})")
            break

    return dict(pr_auc=pr_auc, roc_auc=roc, p_at_r80=p_at_r80)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data",   default="data")
    ap.add_argument("--models", default="models")
    ap.add_argument("--tune",   action="store_true", help="Run Optuna HPO (~30 trials)")
    ap.add_argument("--features", default=None,
                    help="Pre-computed features parquet (skip replay if given)")
    args = ap.parse_args()

    os.makedirs(args.models, exist_ok=True)
    t0 = time.time()
    print("🔬 Prohori Training Pipeline")

    # ── Load data ─────────────────────────────────────────────────────────────
    txn_path = os.path.join(args.data, "transactions.csv")
    lbl_path = os.path.join(args.data, "labels.csv")
    print(f"   Loading {txn_path}…")
    txn_df = pd.read_csv(txn_path)
    lbl_df = pd.read_csv(lbl_path)

    # ── Feature replay ────────────────────────────────────────────────────────
    if args.features and os.path.exists(args.features):
        print(f"   Loading pre-computed features from {args.features}…")
        feat_df = pd.read_parquet(args.features)
    else:
        feat_df = replay_features(txn_df)
        feat_out = os.path.join(args.data, "features.parquet")
        feat_df.to_parquet(feat_out, index=False)
        print(f"   Features saved → {feat_out}")

    # ── Time split ────────────────────────────────────────────────────────────
    print("\n📅 Splitting by time…")
    train_raw, valid_raw, test_raw = time_split(txn_df, lbl_df)

    def _get_X_y(split_df, feat_df):
        merged = split_df[["txn_id"]].merge(feat_df, on="txn_id", how="left")
        merged = prepare_features(merged)
        # ensure all feature cols exist
        for c in FEATURE_COLS_BASIC:
            if c not in merged.columns:
                merged[c] = 0
        X = merged[FEATURE_COLS_BASIC].values
        y = split_df["is_fraud"].values
        return X, y

    X_train, y_train = _get_X_y(train_raw, feat_df)
    X_val,   y_val   = _get_X_y(valid_raw, feat_df)
    X_test,  y_test  = _get_X_y(test_raw,  feat_df)

    print(f"\n   Feature matrix: {X_train.shape[1]} features")
    print(f"   Class balance train: {y_train.sum()} fraud / {(y_train==0).sum()} normal")

    # ── Train models ──────────────────────────────────────────────────────────
    print("\n🌲 Training LightGBM…")
    lgbm = train_lgbm(X_train, y_train, X_val, y_val, tune=args.tune)

    print("\n⚡ Training XGBoost…")
    xgb  = train_xgb(X_train, y_train, X_val, y_val)

    print("\n🌀 Training Isolation Forest…")
    iso  = train_iso_forest(X_train)

    # ── Evaluate ──────────────────────────────────────────────────────────────
    print("\n📊 Evaluation on Validation Set:")
    eval_lgbm = evaluate(lgbm, X_val, y_val, "LightGBM-val", iso)
    eval_xgb  = evaluate(xgb,  X_val, y_val, "XGBoost-val",  iso)

    print("\n📊 Evaluation on Test Set (locked):")
    eval_lgbm_test = evaluate(lgbm, X_test, y_test, "LightGBM-test", iso)
    eval_xgb_test  = evaluate(xgb,  X_test, y_test, "XGBoost-test",  iso)

    # ── Save artifacts ────────────────────────────────────────────────────────
    if lgbm:
        dump(lgbm, os.path.join(args.models, "lgbm_model.joblib"))
    if xgb:
        dump(xgb,  os.path.join(args.models, "xgb_model.joblib"))
    if iso:
        dump(iso,  os.path.join(args.models, "iso_forest.joblib"))

    with open(os.path.join(args.models, "feature_list.json"), "w") as f:
        json.dump(FEATURE_COLS_BASIC, f, indent=2)

    report = dict(
        lgbm_val=eval_lgbm, xgb_val=eval_xgb,
        lgbm_test=eval_lgbm_test, xgb_test=eval_xgb_test,
        n_features=len(FEATURE_COLS_BASIC),
        n_train=int(len(X_train)), n_valid=int(len(X_val)), n_test=int(len(X_test)),
        runtime_s=round(time.time() - t0, 1),
    )
    with open(os.path.join(args.models, "training_report.json"), "w") as f:
        json.dump(report, f, indent=2)

    print(f"\n✅ Training complete in {time.time()-t0:.1f}s")
    print(f"   Models → {args.models}/")


if __name__ == "__main__":
    main()
