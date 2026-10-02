"""
src/evaluation/evaluate_and_plot.py
===================================
Comprehensive evaluation and visualization suite for Prohori fraud detection models.

Generates:
  1. Detailed performance metrics (PR-AUC, ROC-AUC, Recall@5% FAR, Recall@1% FAR, F1, P, R).
  2. Operating threshold analysis (5% FAR, 1% FAR, Best F1).
  3. Confusion matrices with normalized & raw counts.
  4. Per-scenario and per-fraud-class recall analysis.
  5. Benign lookalike false-positive resistance analysis.
  6. Publication-quality visual plots saved as PNGs:
     - roc_curves.png
     - pr_curves.png
     - confusion_matrices.png
     - feature_importance.png
     - score_distribution.png
     - threshold_tuning.png
     - fraud_class_recall.png
     - benign_lookalike_resilience.png
  7. JSON and Markdown report summaries.
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
import matplotlib
matplotlib.use("Agg")  # Non-interactive backend for server/script runs
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.metrics import (
    average_precision_score,
    roc_auc_score,
    roc_curve,
    precision_recall_curve,
    confusion_matrix,
    classification_report,
    f1_score,
    brier_score_loss,
)
from joblib import load

# Configure plotting style
plt.style.use("seaborn-v0_8-whitegrid")
plt.rcParams["font.sans-serif"] = "DejaVu Sans"
plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["figure.dpi"] = 300
plt.rcParams["axes.titlesize"] = 14
plt.rcParams["axes.labelsize"] = 12
plt.rcParams["xtick.labelsize"] = 10
plt.rcParams["ytick.labelsize"] = 10
plt.rcParams["legend.fontsize"] = 11

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

CATEGORICAL_COLS = ["txn_type", "channel"]

FRAUD_CLASS_NAMES = {
    "S1": "Account Takeover (ATO)",
    "S2": "Agent Churn / Collusion",
    "S3": "Split Cash-In / Mule Funnel",
    "S4": "Fast Cash-Out / Ponzi Drain",
    "S5": "Dormant Account Wakeup",
    "S6": "Inflow / Outflow Mismatch",
    "S7": "Structural / Ring Anomaly",
}


def prepare_features(feat_df: pd.DataFrame) -> pd.DataFrame:
    """Ensure categorical encodings and bounded numeric features."""
    from sklearn.preprocessing import LabelEncoder

    df = feat_df.copy()
    for col in CATEGORICAL_COLS:
        if col in df.columns:
            le = LabelEncoder()
            df[f"{col}_enc"] = le.fit_transform(df[col].fillna("UNKNOWN").astype(str))

    df["amount_to_median_ratio"] = df["amount_to_median_ratio"].clip(0, 100)
    df["balance_drain_ratio"] = df["balance_drain_ratio"].clip(0, 1)
    df["recipient_cashout_ratio"] = df["recipient_cashout_ratio"].clip(0, 5)
    df["agent_peer_zscore"] = df["agent_peer_zscore"].clip(-5, 50)

    for c in FEATURE_COLS_BASIC:
        if c not in df.columns:
            df[c] = 0.0

    df[FEATURE_COLS_BASIC] = df[FEATURE_COLS_BASIC].fillna(0)
    return df


def calculate_metrics_at_far(y_true: np.ndarray, y_scores: np.ndarray, target_far: float = 0.05):
    """Compute threshold, recall, precision, and confusion matrix at target False Alert Rate."""
    n_neg = (y_true == 0).sum()
    n_pos = (y_true == 1).sum()

    thresholds = np.linspace(0.001, 0.999, 1000)
    best_thr = 0.5
    for thr in thresholds:
        far = ((y_scores >= thr) & (y_true == 0)).sum() / max(n_neg, 1)
        if far <= target_far:
            best_thr = thr
            break

    y_pred = (y_scores >= best_thr).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred).ravel()

    actual_far = fp / max(n_neg, 1)
    recall = tp / max(n_pos, 1)
    precision = tp / max(tp + fp, 1)
    f1 = 2 * precision * recall / max(precision + recall, 1e-9)

    return {
        "target_far": target_far,
        "threshold": float(best_thr),
        "actual_far": float(actual_far),
        "recall": float(recall),
        "precision": float(precision),
        "f1": float(f1),
        "tp": int(tp),
        "fp": int(fp),
        "tn": int(tn),
        "fn": int(fn),
    }


def calculate_best_f1_metrics(y_true: np.ndarray, y_scores: np.ndarray):
    """Find threshold that maximizes F1 score."""
    n_neg = (y_true == 0).sum()
    n_pos = (y_true == 1).sum()

    thresholds = np.linspace(0.01, 0.95, 200)
    best_f1 = -1.0
    best_metrics = {}

    for thr in thresholds:
        y_pred = (y_scores >= thr).astype(int)
        tn, fp, fn, tp = confusion_matrix(y_true, y_pred).ravel()
        recall = tp / max(n_pos, 1)
        precision = tp / max(tp + fp, 1)
        f1 = 2 * precision * recall / max(precision + recall, 1e-9)
        far = fp / max(n_neg, 1)

        if f1 > best_f1:
            best_f1 = f1
            best_metrics = {
                "threshold": float(thr),
                "f1": float(f1),
                "recall": float(recall),
                "precision": float(precision),
                "far": float(far),
                "tp": int(tp),
                "fp": int(fp),
                "tn": int(tn),
                "fn": int(fn),
            }

    return best_metrics


def plot_roc_curves(eval_data: dict, out_path: str):
    """Plot ROC curves for all models."""
    fig, ax = plt.subplots(figsize=(8, 6.5))

    colors = {
        "LightGBM": "#1f77b4",
        "XGBoost": "#2ca02c",
        "Fused Ensemble": "#d62728",
        "Isolation Forest": "#9467bd",
    }

    for name, d in eval_data.items():
        fpr, tpr, _ = roc_curve(d["y_true"], d["scores"])
        auc_val = roc_auc_score(d["y_true"], d["scores"])
        c = colors.get(name, "#333333")
        lw = 2.5 if "Fused" in name or "LightGBM" in name else 1.8
        ax.plot(fpr, tpr, label=f"{name} (ROC-AUC = {auc_val:.4f})", color=c, lw=lw)

    ax.plot([0, 1], [0, 1], "k--", lw=1.2, alpha=0.6, label="Random Guess (AUC = 0.5000)")
    ax.axvline(x=0.05, color="orange", linestyle=":", lw=1.5, label="5% FAR Benchmark")

    ax.set_xlim([-0.01, 1.01])
    ax.set_ylim([-0.01, 1.02])
    ax.set_xlabel("False Alert Rate (FAR / FPR)")
    ax.set_ylabel("True Positive Rate (Detection Recall)")
    ax.set_title("Receiver Operating Characteristic (ROC) Curves - Test Set", fontweight="bold", pad=12)
    ax.legend(loc="lower right", frameon=True, facecolor="white", framealpha=0.9)
    plt.tight_layout()
    plt.savefig(out_path, dpi=300)
    plt.close()


def plot_pr_curves(eval_data: dict, out_path: str):
    """Plot Precision-Recall curves for all models."""
    fig, ax = plt.subplots(figsize=(8, 6.5))

    colors = {
        "LightGBM": "#1f77b4",
        "XGBoost": "#2ca02c",
        "Fused Ensemble": "#d62728",
        "Isolation Forest": "#9467bd",
    }

    first_key = list(eval_data.keys())[0]
    baseline_prev = np.mean(eval_data[first_key]["y_true"])

    for name, d in eval_data.items():
        prec, rec, _ = precision_recall_curve(d["y_true"], d["scores"])
        ap_val = average_precision_score(d["y_true"], d["scores"])
        c = colors.get(name, "#333333")
        lw = 2.5 if "Fused" in name or "LightGBM" in name else 1.8
        ax.plot(rec, prec, label=f"{name} (PR-AUC / AP = {ap_val:.4f})", color=c, lw=lw)

    ax.plot([0, 1], [baseline_prev, baseline_prev], "k--", lw=1.2, alpha=0.6,
            label=f"Baseline Prevalence ({baseline_prev*100:.2f}%)")

    ax.set_xlim([-0.01, 1.01])
    ax.set_ylim([-0.01, 1.02])
    ax.set_xlabel("Recall (Fraud Detected)")
    ax.set_ylabel("Precision (Positive Predictive Value)")
    ax.set_title("Precision-Recall (PR) Curves - Test Set", fontweight="bold", pad=12)
    ax.legend(loc="upper right", frameon=True, facecolor="white", framealpha=0.9)
    plt.tight_layout()
    plt.savefig(out_path, dpi=300)
    plt.close()


def plot_confusion_matrices(eval_data: dict, out_path: str):
    """Plot Confusion Matrix Heatmaps at 5% FAR for LightGBM, XGBoost, and Fused Ensemble."""
    models_to_plot = [m for m in ["LightGBM", "XGBoost", "Fused Ensemble"] if m in eval_data]
    n_models = len(models_to_plot)

    fig, axes = plt.subplots(1, n_models, figsize=(5.5 * n_models, 4.8))
    if n_models == 1:
        axes = [axes]

    for ax, name in zip(axes, models_to_plot):
        d = eval_data[name]
        m5 = d["metrics_5pct_far"]
        cm = np.array([[m5["tn"], m5["fp"]], [m5["fn"], m5["tp"]]])

        # Annotations with counts and row percentages
        cm_norm = cm.astype(float) / cm.sum(axis=1, keepdims=True)
        annot = np.empty_like(cm, dtype=object)
        for i in range(2):
            for j in range(2):
                annot[i, j] = f"{cm[i, j]:,}\n({cm_norm[i, j]*100:.1f}%)"

        sns.heatmap(cm, annot=annot, fmt="", cmap="Blues", cbar=False, ax=ax,
                    xticklabels=["Normal", "Fraud"], yticklabels=["Normal", "Fraud"],
                    linewidths=1.5, linecolor="white", annot_kws={"size": 11, "weight": "bold"})

        ax.set_title(f"{name}\n(Thr={m5['threshold']:.2f}, Recall={m5['recall']*100:.1f}%)",
                     fontweight="bold", fontsize=12)
        ax.set_xlabel("Predicted Label")
        ax.set_ylabel("True Label")

    plt.suptitle("Confusion Matrices at Operational 5% FAR Threshold (Test Set)",
                 fontweight="bold", fontsize=14, y=1.03)
    plt.tight_layout()
    plt.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close()


def plot_feature_importance(lgbm_model, xgb_model, feature_names: list[str], out_path: str):
    """Plot Feature Importance bar charts for tree models."""
    fig, axes = plt.subplots(1, 2, figsize=(14, 7))

    # LightGBM importance
    if lgbm_model and hasattr(lgbm_model, "feature_importances_"):
        lgb_imp = lgbm_model.feature_importances_
        idx = np.argsort(lgb_imp)[-15:]
        y_pos = np.arange(len(idx))

        axes[0].barh(y_pos, lgb_imp[idx], color="#1f77b4", edgecolor="#0b4068")
        axes[0].set_yticks(y_pos)
        axes[0].set_yticklabels([feature_names[i] for i in idx], fontsize=10)
        axes[0].set_xlabel("Importance (Split Count)")
        axes[0].set_title("LightGBM Top 15 Features", fontweight="bold")
    else:
        axes[0].text(0.5, 0.5, "LightGBM Model Not Available", ha="center")

    # XGBoost importance
    if xgb_model and hasattr(xgb_model, "feature_importances_"):
        xgb_imp = xgb_model.feature_importances_
        idx = np.argsort(xgb_imp)[-15:]
        y_pos = np.arange(len(idx))

        axes[1].barh(y_pos, xgb_imp[idx], color="#2ca02c", edgecolor="#145914")
        axes[1].set_yticks(y_pos)
        axes[1].set_yticklabels([feature_names[i] for i in idx], fontsize=10)
        axes[1].set_xlabel("Importance (Gain / Weight)")
        axes[1].set_title("XGBoost Top 15 Features", fontweight="bold")
    else:
        axes[1].text(0.5, 0.5, "XGBoost Model Not Available", ha="center")

    plt.suptitle("Feature Importance Breakdown", fontweight="bold", fontsize=15, y=1.01)
    plt.tight_layout()
    plt.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close()


def plot_score_distributions(eval_data: dict, out_path: str):
    """Plot risk score distribution comparison for legitimate vs fraud transactions."""
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))

    models = [m for m in ["LightGBM", "Fused Ensemble"] if m in eval_data]
    if len(models) < 2 and "XGBoost" in eval_data:
        models.append("XGBoost")

    for ax, name in zip(axes, models[:2]):
        d = eval_data[name]
        scores = d["scores"]
        y_true = d["y_true"]

        normal_scores = scores[y_true == 0]
        fraud_scores = scores[y_true == 1]

        # Subsample normal for fast plotting if very large
        if len(normal_scores) > 20000:
            np.random.seed(42)
            normal_scores = np.random.choice(normal_scores, size=20000, replace=False)

        ax.hist(normal_scores, bins=50, density=True, alpha=0.6, color="#1f77b4", label=f"Normal (N={len(scores[y_true==0]):,})")
        ax.hist(fraud_scores, bins=50, density=True, alpha=0.7, color="#d62728", label=f"Fraud (N={len(fraud_scores):,})")

        ax.axvline(x=d["metrics_5pct_far"]["threshold"], color="orange", linestyle="--", lw=2,
                   label=f"5% FAR Thr ({d['metrics_5pct_far']['threshold']:.2f})")

        ax.set_title(f"{name} Score Distribution", fontweight="bold")
        ax.set_xlabel("Predicted Fraud Risk Score")
        ax.set_ylabel("Density")
        ax.legend(loc="upper center", frameon=True, facecolor="white", framealpha=0.9)

    plt.suptitle("Risk Score Separation: Legitimate vs Fraudulent", fontweight="bold", fontsize=14, y=1.02)
    plt.tight_layout()
    plt.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close()


def plot_threshold_tuning(eval_data: dict, model_name: str, out_path: str):
    """Plot Precision, Recall, and F1 curve across varying decision thresholds."""
    if model_name not in eval_data:
        return

    d = eval_data[model_name]
    y_true = d["y_true"]
    scores = d["scores"]

    thresholds = np.linspace(0.01, 0.99, 100)
    precisions = []
    recalls = []
    f1s = []
    fars = []

    n_neg = (y_true == 0).sum()
    n_pos = (y_true == 1).sum()

    for thr in thresholds:
        y_pred = (scores >= thr).astype(int)
        tp = ((y_pred == 1) & (y_true == 1)).sum()
        fp = ((y_pred == 1) & (y_true == 0)).sum()

        r = tp / max(n_pos, 1)
        p = tp / max(tp + fp, 1)
        f = 2 * p * r / max(p + r, 1e-9)
        far = fp / max(n_neg, 1)

        precisions.append(p)
        recalls.append(r)
        f1s.append(f)
        fars.append(far)

    fig, ax = plt.subplots(figsize=(8.5, 5.5))
    ax.plot(thresholds, recalls, label="Recall (Detection Rate)", color="#2ca02c", lw=2.2)
    ax.plot(thresholds, precisions, label="Precision (PPV)", color="#1f77b4", lw=2.2)
    ax.plot(thresholds, f1s, label="F1 Score", color="#ff7f0e", lw=2.2)
    ax.plot(thresholds, fars, label="False Alert Rate (FAR)", color="#d62728", linestyle="--", lw=1.5)

    # Annotate best F1 and 5% FAR
    best_f1_idx = np.argmax(f1s)
    ax.axvline(x=thresholds[best_f1_idx], color="#ff7f0e", linestyle=":", lw=1.5,
               label=f"Max F1 ({f1s[best_f1_idx]:.3f} @ Thr={thresholds[best_f1_idx]:.2f})")

    ax.axvline(x=d["metrics_5pct_far"]["threshold"], color="black", linestyle=":", lw=1.5,
               label=f"5% FAR Thr ({d['metrics_5pct_far']['threshold']:.2f})")

    ax.set_xlim([0, 1])
    ax.set_ylim([0, 1.05])
    ax.set_xlabel("Decision Threshold")
    ax.set_ylabel("Metric Value")
    ax.set_title(f"Threshold Optimization Curves ({model_name})", fontweight="bold", pad=12)
    ax.legend(loc="center right", frameon=True, facecolor="white", framealpha=0.9)
    plt.tight_layout()
    plt.savefig(out_path, dpi=300)
    plt.close()


def plot_fraud_class_recall(class_recall_df: pd.DataFrame, out_path: str):
    """Plot detection recall grouped by fraud classification category."""
    if class_recall_df.empty:
        return

    fig, ax = plt.subplots(figsize=(10, 5.5))
    df = class_recall_df.sort_values("recall", ascending=True)

    y_pos = np.arange(len(df))
    bars = ax.barh(y_pos, df["recall"] * 100, color="#1f77b4", edgecolor="#0e4165", height=0.6)

    ax.set_yticks(y_pos)
    labels = [f"{c}: {FRAUD_CLASS_NAMES.get(c, c)}" for c in df["fraud_class"]]
    ax.set_yticklabels(labels, fontsize=10)
    ax.set_xlabel("Recall / Detection Rate (%)")
    ax.set_xlim([0, 105])
    ax.set_title("Model Detection Rate by Fraud Typology (Test Set @ 5% FAR)", fontweight="bold", pad=12)

    for bar, count, r in zip(bars, df["total"], df["recall"]):
        ax.text(bar.get_width() + 1.2, bar.get_y() + bar.get_height() / 2,
                f"{r*100:.1f}% (N={count:,})", va="center", fontsize=9, weight="bold")

    plt.tight_layout()
    plt.savefig(out_path, dpi=300)
    plt.close()


def plot_benign_lookalike_resilience(lookalike_df: pd.DataFrame, out_path: str):
    """Plot false alarm comparison between benign lookalikes and regular benign txns."""
    if lookalike_df.empty:
        return

    fig, ax = plt.subplots(figsize=(7, 4.5))
    bars = ax.bar(lookalike_df["category"], lookalike_df["far"] * 100,
                  color=["#2ca02c", "#d62728"], edgecolor="black", width=0.45)

    ax.set_ylabel("False Alarm Rate (%)")
    ax.set_ylim([0, max(lookalike_df["far"] * 100) * 1.35 + 1.0])
    ax.set_title("Resilience: False Alarms on Benign Lookalikes vs Normal", fontweight="bold", pad=12)

    for bar in bars:
        h = bar.get_height()
        ax.text(bar.get_x() + bar.get_width() / 2, h + 0.3,
                f"{h:.2f}%", ha="center", va="bottom", fontsize=11, weight="bold")

    plt.tight_layout()
    plt.savefig(out_path, dpi=300)
    plt.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="data")
    parser.add_argument("--models", default="models")
    parser.add_argument("--features", default=None)
    parser.add_argument("--output", default="eval_results")
    args = parser.parse_args()

    os.makedirs(args.output, exist_ok=True)
    t0 = time.time()
    print("[EVAL] Starting Comprehensive Prohori Evaluation & Graph Generation...")

    # Load data
    txn_path = os.path.join(args.data, "transactions.csv")
    lbl_path = os.path.join(args.data, "labels.csv")
    feat_path = args.features or os.path.join(args.data, "features.parquet")

    if not os.path.exists(feat_path):
        print(f"[ERR] Features file not found at {feat_path}. Cannot evaluate.")
        sys.exit(1)

    print(f"   Loading features from {feat_path}...")
    feat_df = pd.read_parquet(feat_path)
    print(f"   Loaded features: {feat_df.shape}")

    print(f"   Loading labels from {lbl_path}...")
    lbl_df = pd.read_csv(lbl_path, low_memory=False)

    print(f"   Loading transactions metadata...")
    txn_df = pd.read_csv(txn_path, usecols=["txn_id", "timestamp", "txn_type"])
    txn_df["timestamp"] = pd.to_datetime(txn_df["timestamp"], format="mixed")

    # Time split
    t_min = txn_df["timestamp"].min()
    txn_df["day_offset"] = (txn_df["timestamp"] - t_min).dt.days

    merged_meta = txn_df.merge(lbl_df, on="txn_id", how="left")
    merged_meta["is_fraud"] = merged_meta["is_fraud"].fillna(0).astype(int)

    # Test split is Day 50+
    test_meta = merged_meta[merged_meta["day_offset"] >= 50].reset_index(drop=True)
    val_meta = merged_meta[(merged_meta["day_offset"] >= 40) & (merged_meta["day_offset"] <= 49)].reset_index(drop=True)
    train_meta = merged_meta[merged_meta["day_offset"] <= 39].reset_index(drop=True)

    print(f"   Splits: Train={len(train_meta):,} (Fraud={train_meta['is_fraud'].sum():,})")
    print(f"           Valid={len(val_meta):,} (Fraud={val_meta['is_fraud'].sum():,})")
    print(f"           Test={len(test_meta):,} (Fraud={test_meta['is_fraud'].sum():,})")

    # Prepare features for test set
    test_feats = test_meta[["txn_id"]].merge(feat_df, on="txn_id", how="left")
    test_feats = prepare_features(test_feats)
    X_test = test_feats[FEATURE_COLS_BASIC].values
    y_test = test_meta["is_fraud"].values

    # Load models
    lgbm_path = os.path.join(args.models, "lgbm_model.joblib")
    xgb_path = os.path.join(args.models, "xgb_model.joblib")
    iso_path = os.path.join(args.models, "iso_forest.joblib")

    lgbm_model = load(lgbm_path) if os.path.exists(lgbm_path) else None
    xgb_model = load(xgb_path) if os.path.exists(xgb_path) else None
    iso_model = load(iso_path) if os.path.exists(iso_path) else None

    if not lgbm_model and not xgb_model:
        print("[ERR] Neither LightGBM nor XGBoost model found in models/.")
        sys.exit(1)

    eval_data = {}

    # Score LightGBM
    if lgbm_model:
        print("   Scoring LightGBM...")
        p_lgb = lgbm_model.predict_proba(X_test)[:, 1]
        eval_data["LightGBM"] = {
            "y_true": y_test,
            "scores": p_lgb,
            "pr_auc": float(average_precision_score(y_test, p_lgb)),
            "roc_auc": float(roc_auc_score(y_test, p_lgb)),
            "brier_score": float(brier_score_loss(y_test, p_lgb)),
            "metrics_5pct_far": calculate_metrics_at_far(y_test, p_lgb, target_far=0.05),
            "metrics_1pct_far": calculate_metrics_at_far(y_test, p_lgb, target_far=0.01),
            "best_f1_metrics": calculate_best_f1_metrics(y_test, p_lgb),
        }

    # Score XGBoost
    if xgb_model:
        print("   Scoring XGBoost...")
        p_xgb = xgb_model.predict_proba(X_test)[:, 1]
        eval_data["XGBoost"] = {
            "y_true": y_test,
            "scores": p_xgb,
            "pr_auc": float(average_precision_score(y_test, p_xgb)),
            "roc_auc": float(roc_auc_score(y_test, p_xgb)),
            "brier_score": float(brier_score_loss(y_test, p_xgb)),
            "metrics_5pct_far": calculate_metrics_at_far(y_test, p_xgb, target_far=0.05),
            "metrics_1pct_far": calculate_metrics_at_far(y_test, p_xgb, target_far=0.01),
            "best_f1_metrics": calculate_best_f1_metrics(y_test, p_xgb),
        }

    # Score Isolation Forest (Anomaly)
    p_iso = None
    if iso_model:
        print("   Scoring Isolation Forest...")
        raw_iso = -iso_model.score_samples(X_test)
        p_iso = (raw_iso - raw_iso.min()) / (raw_iso.max() - raw_iso.min() + 1e-9)
        eval_data["Isolation Forest"] = {
            "y_true": y_test,
            "scores": p_iso,
            "pr_auc": float(average_precision_score(y_test, p_iso)),
            "roc_auc": float(roc_auc_score(y_test, p_iso)),
            "metrics_5pct_far": calculate_metrics_at_far(y_test, p_iso, target_far=0.05),
            "metrics_1pct_far": calculate_metrics_at_far(y_test, p_iso, target_far=0.01),
            "best_f1_metrics": calculate_best_f1_metrics(y_test, p_iso),
        }

    # Fused Ensemble
    if lgbm_model and xgb_model and iso_model:
        print("   Computing Fused Ensemble (0.45 LGBM + 0.35 XGB + 0.20 ISO)...")
        p_fused = 0.45 * p_lgb + 0.35 * p_xgb + 0.20 * p_iso
        eval_data["Fused Ensemble"] = {
            "y_true": y_test,
            "scores": p_fused,
            "pr_auc": float(average_precision_score(y_test, p_fused)),
            "roc_auc": float(roc_auc_score(y_test, p_fused)),
            "brier_score": float(brier_score_loss(y_test, p_fused)),
            "metrics_5pct_far": calculate_metrics_at_far(y_test, p_fused, target_far=0.05),
            "metrics_1pct_far": calculate_metrics_at_far(y_test, p_fused, target_far=0.01),
            "best_f1_metrics": calculate_best_f1_metrics(y_test, p_fused),
        }

    # Generate Visualizations
    print("\n[PLOT] Generating Publication-Quality Plots...")
    roc_img = os.path.join(args.output, "roc_curves.png")
    plot_roc_curves(eval_data, roc_img)
    print(f"   -> {roc_img}")

    pr_img = os.path.join(args.output, "pr_curves.png")
    plot_pr_curves(eval_data, pr_img)
    print(f"   -> {pr_img}")

    cm_img = os.path.join(args.output, "confusion_matrices.png")
    plot_confusion_matrices(eval_data, cm_img)
    print(f"   -> {cm_img}")

    fi_img = os.path.join(args.output, "feature_importance.png")
    plot_feature_importance(lgbm_model, xgb_model, FEATURE_COLS_BASIC, fi_img)
    print(f"   -> {fi_img}")

    dist_img = os.path.join(args.output, "score_distribution.png")
    plot_score_distributions(eval_data, dist_img)
    print(f"   -> {dist_img}")

    # Threshold tuning plot for Primary Model (LightGBM or Fused)
    primary_name = "Fused Ensemble" if "Fused Ensemble" in eval_data else "LightGBM"
    tt_img = os.path.join(args.output, "threshold_tuning.png")
    plot_threshold_tuning(eval_data, primary_name, tt_img)
    print(f"   -> {tt_img}")

    # Breakdown by Fraud Class
    print("\n[ANALYSIS] Detailed Breakdown by Fraud Typology & Lookalikes...")
    primary_scores = eval_data[primary_name]["scores"]
    primary_thr_5pct = eval_data[primary_name]["metrics_5pct_far"]["threshold"]
    test_meta["pred_fraud_5pct"] = (primary_scores >= primary_thr_5pct).astype(int)

    fraud_test = test_meta[test_meta["is_fraud"] == 1]
    class_stats = []
    if "fraud_class" in fraud_test.columns:
        for f_cls, grp in fraud_test.groupby("fraud_class"):
            n_tot = len(grp)
            n_det = grp["pred_fraud_5pct"].sum()
            rec = n_det / max(n_tot, 1)
            class_stats.append({
                "fraud_class": str(f_cls),
                "total": int(n_tot),
                "detected": int(n_det),
                "recall": float(rec),
            })
    class_recall_df = pd.DataFrame(class_stats)

    fc_img = os.path.join(args.output, "fraud_class_recall.png")
    plot_fraud_class_recall(class_recall_df, fc_img)
    print(f"   -> {fc_img}")

    # Benign lookalike resistance
    lookalike_stats = []
    normal_test = test_meta[test_meta["is_fraud"] == 0]
    if "is_benign_lookalike" in normal_test.columns:
        for is_look, name in [(0, "Standard Benign"), (1, "Benign Lookalike")]:
            sub = normal_test[normal_test["is_benign_lookalike"] == is_look]
            if len(sub) > 0:
                fp_cnt = sub["pred_fraud_5pct"].sum()
                far = fp_cnt / len(sub)
                lookalike_stats.append({
                    "category": name,
                    "total": int(len(sub)),
                    "false_positives": int(fp_cnt),
                    "far": float(far),
                })
    lookalike_df = pd.DataFrame(lookalike_stats)

    bl_img = os.path.join(args.output, "benign_lookalike_resilience.png")
    plot_benign_lookalike_resilience(lookalike_df, bl_img)
    print(f"   -> {bl_img}")

    # Save summary JSON
    summary_json_path = os.path.join(args.output, "evaluation_metrics.json")
    clean_eval_data = {}
    for m_name, d in eval_data.items():
        clean_eval_data[m_name] = {k: v for k, v in d.items() if k not in ("scores", "y_true")}

    output_payload = {
        "models_evaluated": list(eval_data.keys()),
        "test_set_size": int(len(test_meta)),
        "test_fraud_count": int(test_meta["is_fraud"].sum()),
        "metrics": clean_eval_data,
        "fraud_class_performance": class_stats,
        "benign_lookalike_resilience": lookalike_stats,
        "evaluation_time_seconds": round(time.time() - t0, 2),
    }

    with open(summary_json_path, "w", encoding="utf-8") as f:
        json.dump(output_payload, f, indent=2)
    print(f"\n[OK] Metrics saved to {summary_json_path}")

    # Save Markdown Report
    report_md_path = os.path.join(args.output, "evaluation_summary.md")
    with open(report_md_path, "w", encoding="utf-8") as f:
        f.write("# Prohori Fraud Detection Evaluation Report\n\n")
        f.write(f"- **Test Set Transactions:** {len(test_meta):,}\n")
        f.write(f"- **Test Fraud Instances:** {test_meta['is_fraud'].sum():,} ({test_meta['is_fraud'].mean()*100:.2f}%)\n")
        f.write(f"- **Primary Evaluation Benchmark:** False Alert Rate (FAR) ≤ 5.0%\n\n")

        f.write("## 1. Model Performance Benchmark (Test Set)\n\n")
        f.write("| Model | ROC-AUC | PR-AUC (AP) | Recall @ 5% FAR | Precision @ 5% FAR | Best F1 | Threshold @ 5% FAR |\n")
        f.write("| :--- | :---: | :---: | :---: | :---: | :---: | :---: |\n")
        for m_name, d in eval_data.items():
            if m_name == "Isolation Forest":
                continue
            m5 = d["metrics_5pct_far"]
            bf1 = d["best_f1_metrics"]
            f.write(f"| **{m_name}** | {d['roc_auc']:.4f} | {d['pr_auc']:.4f} | **{m5['recall']*100:.2f}%** | {m5['precision']*100:.2f}% | {bf1['f1']:.4f} | `{m5['threshold']:.3f}` |\n")

        f.write("\n## 2. Detection Recall by Fraud Typology (@ 5% FAR)\n\n")
        f.write("| Typology Code | Fraud Scenario Family | Total Test Samples | Detected | Detection Recall |\n")
        f.write("| :--- | :--- | :---: | :---: | :---: |\n")
        for cs in class_stats:
            c = cs["fraud_class"]
            name = FRAUD_CLASS_NAMES.get(c, c)
            f.write(f"| `{c}` | {name} | {cs['total']:,} | {cs['detected']:,} | **{cs['recall']*100:.2f}%** |\n")

        f.write("\n## 3. False Alarm Resilience on Benign Lookalikes\n\n")
        f.write("| Cohort | Total Transactions | False Positives | False Alarm Rate (FAR) |\n")
        f.write("| :--- | :---: | :---: | :---: |\n")
        for ls in lookalike_stats:
            f.write(f"| {ls['category']} | {ls['total']:,} | {ls['false_positives']:,} | **{ls['far']*100:.2f}%** |\n")

        f.write("\n\n*Generated automatically by Prohori Evaluation Suite.*")

    print(f"[OK] Markdown summary saved to {report_md_path}")
    print(f"[ALL DONE] in {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
