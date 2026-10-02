"""Baselines the ML must beat: a hand-written MFS rulebook and a logistic regression."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

RULES = {
    "big_first_time_transfer": lambda d: (d["amount"] >= 20000) & (d["pair_first"] == 1),
    "night_new_device": (lambda d: (d["is_night"] == 1) & (d["device_age_hours"].fillna(999) < 1)),
    "very_new_recipient": lambda d: d["cp_age_days"].fillna(9999) < 3,
    "account_drain": lambda d: d["drain_ratio"].fillna(0) > 0.8,
    "many_new_senders_to_recipient": lambda d: d["cp_in_new_24h"].fillna(0) >= 5,
}


def rules_score(df: pd.DataFrame) -> np.ndarray:
    hits = np.vstack([fn(df).to_numpy(dtype=float) for fn in RULES.values()])
    return hits.mean(axis=0) + 1e-4 * np.log1p(df["amount"].to_numpy())   # tiny amount tie-break


def isflagged_baseline(df: pd.DataFrame) -> np.ndarray:
    """PaySim's naive business rule (transfer > 200,000) for comparison: catches nothing here."""
    return (df["amount"].to_numpy() > 200_000).astype(float)


def logistic(X: pd.DataFrame, y: np.ndarray, seed=42):
    m = make_pipeline(SimpleImputer(strategy="median"), StandardScaler(),
                      LogisticRegression(C=0.5, class_weight="balanced", max_iter=3000, random_state=seed))
    m.fit(X, y)
    return m
