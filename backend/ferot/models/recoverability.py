"""M5 recoverability: the chance at least half the disputed money is still holdable after 1, 6 and 24 hours.

Trained as one LightGBM classifier per horizon. The expected recoverable taka at each horizon is the
amount holdable now times that probability, which gives the decay curve shown to the agent.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier

HORIZONS_MIN = [60, 360, 1440]
REC_FEATURES = [
    "recoverable_share_now", "recipient_outflow_share_since", "minutes_to_first_outflow",
    "recipient_passthrough_30d", "recipient_inbound_30d", "recipient_distinct_senders_7d",
    "prior_complainants_on_recipient", "log_minutes_to_complaint", "complaint_hour", "remaining_cashout_limit",
    "log_amount", "return_flow", "first_ever", "intended_found", "recipient_age_days",
]


def make_model(seed: int = 42) -> LGBMClassifier:
    return LGBMClassifier(n_estimators=300, learning_rate=0.05, num_leaves=15, min_child_samples=10,
                          random_state=seed, verbose=-1)


class Recoverability:
    def __init__(self, models: dict[int, LGBMClassifier]):
        self.models = models

    def curve(self, row: dict, recoverable_now: float) -> list[dict]:
        if recoverable_now <= 0:
            return [{"minutes": 0, "expected": 0.0, "p_hold": 0.0}] + [
                {"minutes": h, "expected": 0.0, "p_hold": 0.0} for h in HORIZONS_MIN]
        x = pd.DataFrame([row])[REC_FEATURES].astype(float)
        points = [{"minutes": 0, "expected": round(recoverable_now, 2), "p_hold": 1.0}]
        prev = 1.0
        for h in HORIZONS_MIN:
            m = self.models.get(h)
            p = float(m.predict_proba(x)[0, 1]) if m is not None else prev
            p = min(p, prev)  # holding can only get less likely as time passes
            prev = p
            points.append({"minutes": h, "expected": round(recoverable_now * p, 2), "p_hold": round(p, 3)})
        return points


def expected_at(curve: list[dict], minutes: float) -> float:
    xs = [p["minutes"] for p in curve]
    ys = [p["expected"] for p in curve]
    return float(np.interp(minutes, xs, ys))
