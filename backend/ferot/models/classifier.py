"""M4 case classifier (LightGBM, 5 classes) with per-case reasons from TreeSHAP contributions."""

from __future__ import annotations

import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier

from ferot.features.evidence import FEATURE_LABELS, FEATURES

CLASSES = ["genuine_wrong_send", "scam_victim", "double_recovery", "false_claim", "technical_failure"]
CLASS_LABELS = {
    "genuine_wrong_send": "Genuine wrong-send",
    "scam_victim": "Scam victim",
    "double_recovery": "Double-recovery claim",
    "false_claim": "False claim",
    "technical_failure": "Technical failure",
}


def make_model(seed: int = 42) -> LGBMClassifier:
    return LGBMClassifier(
        n_estimators=600, learning_rate=0.04, num_leaves=15, min_child_samples=8, subsample=0.9,
        subsample_freq=1, colsample_bytree=0.9, class_weight="balanced", random_state=seed, verbose=-1)


class CaseClassifier:
    def __init__(self, model: LGBMClassifier, features: list[str] | None = None):
        self.model = model
        self.features = features or FEATURES

    def frame(self, rows: list[dict]) -> pd.DataFrame:
        return pd.DataFrame(rows)[self.features].astype(float)

    def predict_proba(self, rows: list[dict]) -> np.ndarray:
        proba = self.model.predict_proba(self.frame(rows))
        order = [list(self.model.classes_).index(c) for c in CLASSES]
        return proba[:, order]

    def explain(self, row: dict, top: int = 3) -> tuple[dict, list[dict]]:
        x = self.frame([row])
        proba = self.predict_proba([row])[0]
        best = int(np.argmax(proba))
        cls_pos = list(self.model.classes_).index(CLASSES[best])
        contrib = self.model.predict(x, pred_contrib=True)
        n = len(self.features) + 1
        values = np.asarray(contrib)[0][cls_pos * n:(cls_pos + 1) * n - 1]
        order = np.argsort(-values)
        reasons = []
        for k in order[:top]:
            if values[k] <= 0:
                break
            name = self.features[k]
            reasons.append({"feature": name, "label": FEATURE_LABELS.get(name, name),
                            "value": _fmt(row.get(name)), "weight": round(float(values[k]), 3)})
        probs = {c: round(float(p), 4) for c, p in zip(CLASSES, proba)}
        return probs, reasons


def _fmt(v):
    if isinstance(v, float):
        return round(v, 2)
    return v


def keyword_baseline(row: dict) -> str:
    """What a simple keyword triage would say, from the text alone."""
    if row.get("cue_failed"):
        return "technical_failure"
    if row.get("cue_returned") or row.get("cue_prize") or row.get("cue_job") or row.get("cue_officer") or (
            row.get("cue_call") and row.get("cue_sms")):
        return "scam_victim"
    return "genuine_wrong_send"
