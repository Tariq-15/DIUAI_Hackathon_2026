"""
src/inference/score.py
=======================
Inference endpoint – scores a single transaction dict and returns:
  {
    "risk_score": 89,
    "band": "HIGH",
    "p_fraud": 0.90,
    "anomaly_score": 0.80,
    "graph_score": 1.00,
    "top_reasons": [...],
    "warning_text": {...},
    "action": "HOLD"
  }

Can be used as a FastAPI endpoint or called directly.
Loads models once (singleton pattern) for low-latency inference.
"""
from __future__ import annotations

import json
import os
import sys
from typing import Optional

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# ── Model singleton ───────────────────────────────────────────────────────────

_MODELS: dict = {}
_FEATURE_COLS: list = []
_WARNINGS_BN: dict = {}


def _load_models(models_dir: str = "models"):
    global _MODELS, _FEATURE_COLS, _WARNINGS_BN
    if _MODELS:
        return   # already loaded

    from joblib import load

    for name, fname in [("lgbm", "lgbm_model.joblib"),
                         ("xgb",  "xgb_model.joblib"),
                         ("iso",  "iso_forest.joblib")]:
        path = os.path.join(models_dir, fname)
        if os.path.exists(path):
            _MODELS[name] = load(path)

    feat_path = os.path.join(models_dir, "feature_list.json")
    if os.path.exists(feat_path):
        with open(feat_path) as f:
            _FEATURE_COLS = json.load(f)

    # Load Bangla warning strings
    bn_path = os.path.join(PROJECT_ROOT, "prohori_warnings_bn.json")
    if os.path.exists(bn_path):
        with open(bn_path, encoding="utf-8") as f:
            _WARNINGS_BN = json.load(f)


# ── Feature preparation ───────────────────────────────────────────────────────

def _prepare_single(txn_features: dict) -> Optional[np.ndarray]:
    """Convert a feature dict to the model input array."""
    import pandas as pd
    from src.training.train import prepare_features, FEATURE_COLS_BASIC

    df = pd.DataFrame([txn_features])
    df = prepare_features(df)
    cols = _FEATURE_COLS or FEATURE_COLS_BASIC
    for c in cols:
        if c not in df.columns:
            df[c] = 0
    return df[cols].values


# ── Risk band logic ───────────────────────────────────────────────────────────

def _band_from_score(score: float) -> tuple[str, str]:
    if score >= 85:
        return "HIGH", "HOLD"
    if score >= 60:
        return "WARN", "ALERT"
    if score >= 30:
        return "NUDGE", "MONITOR"
    return "ALLOW", "LOG"


# ── Top reasons ───────────────────────────────────────────────────────────────

def _top_reasons(feat: dict, n: int = 3) -> list[dict]:
    """Return top-3 human-readable risk reasons from feature values."""
    reasons = []
    if feat.get("recipient_age_hours", 0) < 72:
        reasons.append({
            "key": "wallet_age",
            "text_en": f"Recipient wallet opened {feat['recipient_age_hours']:.0f} h ago.",
            "text_bn": _WARNINGS_BN.get("reason_wallet_age", "").format(
                days=max(1, int(feat['recipient_age_hours'] // 24))
            ),
        })
    if feat.get("recipient_unique_senders_24h", 0) > 5:
        reasons.append({
            "key": "unique_senders",
            "text_en": f"{feat['recipient_unique_senders_24h']} different senders in last 24 h.",
            "text_bn": _WARNINGS_BN.get("reason_unique_senders", "").format(
                hours=24, n=int(feat['recipient_unique_senders_24h'])
            ),
        })
    if feat.get("amount_to_median_ratio", 1) > 3:
        reasons.append({
            "key": "amount",
            "text_en": f"Amount is {feat['amount_to_median_ratio']:.1f}× your usual.",
            "text_bn": _WARNINGS_BN.get("reason_amount", "").format(
                x=round(feat['amount_to_median_ratio'], 1)
            ),
        })
    if feat.get("recipient_cashout_ratio", 0) > 0.7:
        reasons.append({
            "key": "cashout_fast",
            "text_en": "Funds from this wallet are cashed out within minutes.",
            "text_bn": _WARNINGS_BN.get("reason_cashout_fast", ""),
        })
    if feat.get("counterparty_first_time", 0):
        reasons.append({
            "key": "first_time",
            "text_en": "First time sending to this number.",
            "text_bn": _WARNINGS_BN.get("reason_first_time", ""),
        })
    if feat.get("is_new_device", 0):
        hour = feat.get("hour", 12)
        reasons.append({
            "key": "new_device_night",
            "text_en": f"Transaction from a new device at {hour}:00.",
            "text_bn": _WARNINGS_BN.get("reason_new_device_night", "").format(time=hour),
        })
    return reasons[:n]


# ── Main score function ───────────────────────────────────────────────────────

def score_transaction(
    txn_features: dict,
    models_dir: str = "models",
    graph_score: float = 0.0,
) -> dict:
    """
    Score a single transaction given its pre-computed features.

    Parameters
    ----------
    txn_features : dict
        Feature dict as returned by FeatureStore.get_features().
    models_dir   : str
        Path to directory containing .joblib model files.
    graph_score  : float
        0-1 graph-based risk score (pass in from graph engine if available).

    Returns
    -------
    dict with risk_score, band, action, top_reasons, warning_text.
    """
    _load_models(models_dir)

    X = _prepare_single(txn_features)
    if X is None:
        return {"error": "Feature preparation failed"}

    # Model probabilities
    p_fraud = 0.5
    if "lgbm" in _MODELS:
        p_fraud = float(_MODELS["lgbm"].predict_proba(X)[:, 1][0])
    elif "xgb" in _MODELS:
        p_fraud = float(_MODELS["xgb"].predict_proba(X)[:, 1][0])

    # Anomaly score from isolation forest (normalised to 0-1)
    anomaly = 0.0
    if "iso" in _MODELS:
        raw = float(-_MODELS["iso"].score_samples(X)[0])
        # Rough normalisation; calibrate on validation set for production
        anomaly = min(1.0, max(0.0, (raw + 0.2) / 0.6))

    # Fusion: 0.5 × P(fraud) + 0.3 × anomaly + 0.2 × graph
    fused = 0.5 * p_fraud + 0.3 * anomaly + 0.2 * graph_score
    risk_score = int(min(100, max(0, round(fused * 100))))

    band, action = _band_from_score(risk_score)
    reasons      = _top_reasons(txn_features, n=3)

    # Warning text (English + Bangla from JSON)
    warning = {
        "header_en":    f"{'Stop and check!' if band == 'HIGH' else 'Careful - check!'} "
                        f"Risk: {risk_score}/100 ({band})",
        "header_bn":    _WARNINGS_BN.get(f"header_{band.lower()}", ""),
        "reasons":      reasons,
        "question_en":  "Do you personally know and trust this person?",
        "question_bn":  _WARNINGS_BN.get("question", ""),
        "authority_en": "upay never asks for your PIN or OTP by phone.",
        "authority_bn": _WARNINGS_BN.get("authority", ""),
        "btn_cancel_bn": _WARNINGS_BN.get("btn_cancel", ""),
        "btn_continue_bn": _WARNINGS_BN.get("btn_continue", ""),
    }
    if band == "HIGH":
        warning["hold_msg_bn"] = _WARNINGS_BN.get("hold_wallet", "")

    return dict(
        risk_score    = risk_score,
        band          = band,
        action        = action,
        p_fraud       = round(p_fraud, 4),
        anomaly_score = round(anomaly, 4),
        graph_score   = round(graph_score, 4),
        top_reasons   = reasons,
        warning_text  = warning,
    )


# ── FastAPI app (optional) ────────────────────────────────────────────────────

try:
    from fastapi import FastAPI
    from pydantic import BaseModel

    app = FastAPI(
        title="Prohori – upay Scam Shield",
        description="Real-time fraud risk scoring API for Bangladesh MFS",
        version="1.0.0",
    )

    class TransactionFeatures(BaseModel):
        txn_id: str = ""
        amount_tk: float = 0.0
        txn_type: str = "P2P_SEND"
        channel: str = "APP"
        hour: int = 12
        weekday: int = 0
        is_new_device: int = 0
        location_changed: int = 0
        session_seconds: int = 42
        pin_attempts: int = 1
        counterparty_first_time: int = 0
        amount_to_median_ratio: float = 1.0
        balance_drain_ratio: float = 0.1
        hour_deviation: float = 0.0
        recipient_age_hours: float = 720.0
        recipient_unique_senders_3h: int = 0
        recipient_unique_senders_24h: int = 0
        recipient_unique_senders_48h: int = 0
        recipient_first_time_sender_ratio: float = 0.0
        recipient_inflow_outflow_lag_min: float = -1.0
        recipient_cashout_ratio: float = 0.0
        agent_peer_zscore: float = 0.0
        graph_score: float = 0.0
        models_dir: str = "models"

    @app.post("/score")
    def score_endpoint(req: TransactionFeatures):
        feat = req.dict()
        gs   = feat.pop("graph_score", 0.0)
        md   = feat.pop("models_dir", "models")
        return score_transaction(feat, models_dir=md, graph_score=gs)

    @app.get("/health")
    def health():
        _load_models()
        return {"status": "ok", "models": list(_MODELS.keys())}

except ImportError:
    # FastAPI not installed; score_transaction still usable directly
    pass


# ── CLI demo ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="models")
    ap.add_argument("--serve", action="store_true", help="Start FastAPI server")
    args = ap.parse_args()

    if args.serve:
        import uvicorn
        uvicorn.run("src.inference.score:app", host="0.0.0.0", port=8000, reload=False)
    else:
        # Demo: simulate SC-01 features
        demo_feat = dict(
            txn_id="SC-01-DEMO", amount_tk=20000.0, txn_type="P2P_SEND",
            channel="APP", hour=21, weekday=4,
            is_new_device=0, location_changed=0, session_seconds=38, pin_attempts=1,
            counterparty_first_time=1, amount_to_median_ratio=10.0,
            balance_drain_ratio=0.85, hour_deviation=0.3,
            recipient_age_hours=68.0, recipient_unique_senders_3h=5,
            recipient_unique_senders_24h=29, recipient_unique_senders_48h=29,
            recipient_first_time_sender_ratio=0.83, recipient_inflow_outflow_lag_min=6.0,
            recipient_cashout_ratio=0.96, agent_peer_zscore=0.0,
            txn_type_enc=0, channel_enc=0,
        )
        result = score_transaction(demo_feat, models_dir=args.models, graph_score=1.0)
        print(json.dumps(result, ensure_ascii=False, indent=2))
