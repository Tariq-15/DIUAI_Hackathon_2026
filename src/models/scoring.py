"""Turn a feature frame into model outputs with a saved bundle (shared by evaluate + API)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.common.config import resolve
from src.features.spec import ALL_FEATURES, ANOMALY_FEATURES, CATEGORICAL
from .fusion import ScoreMapper, fuse, graph_score, policy_bands

BUNDLE = "model_bundle.joblib"


def X_of(df: pd.DataFrame, features=None) -> pd.DataFrame:
    X = df[features or ALL_FEATURES].astype(np.float64)
    for c in CATEGORICAL:
        if c in X:
            X[c] = X[c].fillna(-1).astype(np.int32)
    return X


def anomaly_scores(bundle, df):
    A = df[ANOMALY_FEATURES].astype(np.float64).fillna(bundle["if_fill"])
    raw = -bundle["iforest"].score_samples(A.to_numpy())
    ref = bundle["if_ref"]
    return np.interp(raw, ref, np.linspace(0, 1, len(ref)))


def score_frame(bundle: dict, df: pd.DataFrame) -> pd.DataFrame:
    X = X_of(df, bundle["features"])
    p = bundle["lgbm"].predict_proba(X)[:, 1]
    anom = anomaly_scores(bundle, df)
    gs = graph_score(df)
    fused = fuse(bundle["weights"], p, anom, gs)
    mapper = ScoreMapper(**bundle["mapper"])
    score = mapper(fused)
    band, why = policy_bands(df, score, bundle["bands"], bundle.get("established_parties_cap", True),
                             bundle.get("evidence_floors", True))
    return pd.DataFrame({"p_fraud": p, "p_cal": bundle["calibrator"].predict(p), "anomaly": anom, "graph": gs,
                         "fused": fused, "risk_score": np.round(score, 1), "band": band, "policy_override": why},
                        index=df.index)


def load_bundle(cfg) -> dict:
    import joblib
    return joblib.load(resolve(cfg, "artifacts_dir") / BUNDLE)
