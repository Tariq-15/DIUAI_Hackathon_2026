"""Ferot Guard: score a transfer at the moment the customer presses "Send" (prevention before recovery).

Three signals, fused by a documented formula and mapped to bands by business settings (config/guard.yaml):
  * P(scam)     LightGBM on recipient and relationship features (who is this number, as of now?)
  * anomaly     Isolation Forest on the sender's own behaviour (is this unusual for *this* customer?)
  * typo check  M3 intended-number matcher ("Did you mean ...?")
The customer always decides: Guard warns and, at the highest band, pauses for 30 seconds and alerts an
analyst. It never blocks or moves money (rule R6, "no harmful automation").
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier
from sklearn.ensemble import IsolationForest

from ferot import config
from ferot.features.evidence import CaseHistory
from ferot.features.ledger import Ledger
from ferot.models.intended import intended_number

GUARD_FEATURES = [
    "first_ever", "n_prior_to_recipient", "intended_found", "intended_distance", "recipient_age_days",
    "recipient_distinct_senders_7d", "recipient_new_sender_share_7d", "recipient_passthrough_30d",
    "recipient_inbound_30d", "prior_complainants_on_recipient", "log_amount_ratio", "hour",
]
ANOMALY_FEATURES = ["log_amount_ratio", "hour_deviation", "first_ever", "log_amount"]


def guard_features(ledger: Ledger, history: CaseHistory, sender: str, recipient: str, amount: float,
                   minute: int) -> dict:
    prior = ledger.outgoing(sender, minute - 180 * 1440, minute - 1)
    sends = prior[ledger.type[prior] == "send_money"]
    n_prior = int(np.sum(ledger.receiver[sends] == recipient))
    intended = intended_number(ledger, sender, recipient, minute)
    amounts = ledger.amount[sends]
    median_amount = float(np.median(amounts)) if len(amounts) else max(amount, 1.0)
    hours = (ledger.minute[sends] % 1440) // 60
    usual_hour = float(np.median(hours)) if len(hours) else 14.0
    hour = minute % 1440 // 60

    inbound_7d = ledger.incoming(recipient, minute - 7 * 1440, minute - 1)
    inbound_7d = inbound_7d[ledger.type[inbound_7d] == "send_money"]
    senders = set(ledger.sender[inbound_7d])
    new_share = 0.0
    if senders:
        known = set(ledger.sender[ledger.incoming(recipient, minute - 120 * 1440, minute - 7 * 1440)])
        new_share = sum(1 for s in senders if s not in known) / len(senders)
    in_30 = ledger.incoming(recipient, minute - 30 * 1440, minute - 1)
    out_30 = ledger.outgoing(recipient, minute - 30 * 1440, minute - 1)
    cash_30 = out_30[ledger.type[out_30] == "cash_out"]
    passthrough = float(ledger.amount[cash_30].sum()) / max(float(ledger.amount[in_30].sum()), 1.0)
    on_recipient, _ = history.counts(sender, recipient, minute)
    info = ledger.wallet_info(recipient)
    return {
        "first_ever": int(n_prior == 0),
        "n_prior_to_recipient": n_prior,
        "intended_found": int(intended["found"]),
        "intended_distance": intended["distance"] if intended["distance"] is not None else 9.0,
        "recipient_age_days": (minute - info.get("opened_minute", minute)) / 1440,
        "recipient_distinct_senders_7d": len(senders),
        "recipient_new_sender_share_7d": round(new_share, 3),
        "recipient_passthrough_30d": round(min(passthrough, 3.0), 3),
        "recipient_inbound_30d": int(len(in_30)),
        "prior_complainants_on_recipient": on_recipient,
        "log_amount_ratio": math.log(max(amount, 1.0) / max(median_amount, 1.0)),
        "hour": hour,
        "hour_deviation": min(abs(hour - usual_hour), 24 - abs(hour - usual_hour)),
        "log_amount": math.log1p(amount),
        "_intended": intended,
        "_amount_ratio": amount / max(median_amount, 1.0),
    }


class Guard:
    def __init__(self, model: LGBMClassifier, anomaly: IsolationForest, anomaly_scale: tuple[float, float],
                 weights: tuple[float, float] | None = None, cuts: tuple[float, float] | None = None):
        self.model = model
        self.anomaly = anomaly
        self.anomaly_scale = anomaly_scale
        self.weights = weights  # (w_model, w_anomaly) chosen on the validation window
        # fused scores where the warn and review bands start, chosen on the validation window so that about
        # 1 in 100 innocent transfers is warned and 1 in 1,000 is paused (see train_guard)
        self.cuts = cuts

    def anomaly_norm(self, rows: list[dict]) -> np.ndarray:
        raw = -self.anomaly.score_samples(pd.DataFrame(rows)[ANOMALY_FEATURES].astype(float))
        lo, hi = self.anomaly_scale
        return np.clip((raw - lo) / max(hi - lo, 1e-9), 0, 1)

    def p_scam(self, rows: list[dict]) -> np.ndarray:
        return self.model.predict_proba(pd.DataFrame(rows)[GUARD_FEATURES].astype(float))[:, 1]

    def fused(self, rows: list[dict]) -> np.ndarray:
        if self.weights:
            wm, wa = self.weights
        else:
            w = config.load_yaml("guard.yaml")["fusion"]
            wm, wa = w["w_model"], w["w_anomaly"]
        return np.clip(wm * self.p_scam(rows) + wa * self.anomaly_norm(rows), 1e-6, 1.0)

    def risk(self, rows: list[dict]) -> np.ndarray:
        """0-100 risk: piecewise-linear in log(score), so the band edges sit at the validated cut points."""
        s = np.log(self.fused(rows))
        if not self.cuts:
            return np.clip(100 * np.exp(s), 0, 100)
        b = config.load_yaml("guard.yaml")["bands"]
        lo, warn, review, hi = np.log(1e-6), np.log(self.cuts[0]), np.log(self.cuts[1]), 0.0
        return np.clip(np.interp(s, [lo, warn, review, hi], [0, b["warn_at"], b["review_at"], 100]), 0, 100)


def band_for(risk: float, typo: bool) -> str:
    b = config.load_yaml("guard.yaml")["bands"]
    if risk >= b["review_at"]:
        return "review"
    if risk >= b["warn_at"] or typo:
        return "warn"
    return "allow"


def reasons_for(f: dict, typo: dict | None) -> list[dict]:
    """Plain reasons, each built only from a feature value (grounded, like the case drafts)."""
    out = []
    if typo:
        out.append({"key": "typo",
                    "en": f"Did you mean {typo['candidate']}? You have sent money there {typo['count']} times.",
                    "bn": f"আপনি কি {typo['candidate']} নম্বরে পাঠাতে চেয়েছিলেন? সেখানে আপনি আগে {typo['count']} বার টাকা পাঠিয়েছেন।"})
    age = int(f["recipient_age_days"])
    if age <= 45:
        out.append({"key": "new_wallet", "en": f"This number's wallet was opened only {age} days ago.",
                    "bn": f"এই নম্বরের অ্যাকাউন্ট মাত্র {age} দিন আগে খোলা হয়েছে।"})
    if f["prior_complainants_on_recipient"] >= 1:
        n = f["prior_complainants_on_recipient"]
        out.append({"key": "complaints", "en": f"{n} other customers have reported this number.",
                    "bn": f"আরও {n} জন গ্রাহক এই নম্বর নিয়ে অভিযোগ করেছেন।"})
    if f["recipient_distinct_senders_7d"] >= 4 and f["recipient_new_sender_share_7d"] >= 0.6:
        n = f["recipient_distinct_senders_7d"]
        out.append({"key": "many_senders", "en": f"{n} different people sent money to it in the last 7 days.",
                    "bn": f"গত ৭ দিনে {n} জন ভিন্ন মানুষ এই নম্বরে টাকা পাঠিয়েছেন।"})
    if f["recipient_passthrough_30d"] >= 0.8 and f["recipient_inbound_30d"] >= 3:
        out.append({"key": "cash_out_fast", "en": "Money sent to this number is usually cashed out soon after.",
                    "bn": "এই নম্বরে আসা টাকা সাধারণত দ্রুত ক্যাশ আউট করা হয়।"})
    if f["first_ever"] and not typo:
        out.append({"key": "first_time", "en": "You have never sent money to this number before.",
                    "bn": "আপনি আগে কখনো এই নম্বরে টাকা পাঠাননি।"})
    ratio = f["_amount_ratio"]
    if ratio >= 3:
        out.append({"key": "large_amount", "en": f"This is about {ratio:.0f} times your usual amount.",
                    "bn": f"এটি আপনার সাধারণ লেনদেনের প্রায় {ratio:.0f} গুণ।"})
    return out


ADVICE = {
    "en": "If someone called asking you to return money, or promised a prize or a job, do not send. upay never asks for your PIN or OTP.",
    "bn": "কেউ ফোন করে টাকা ফেরত চাইলে বা পুরস্কার কিংবা চাকরির কথা বললে টাকা পাঠাবেন না। উপায় কখনো আপনার পিন বা ওটিপি চায় না।",
}


def check(guard: Guard, ledger: Ledger, history: CaseHistory, sender: str, recipient: str, amount: float,
          minute: int) -> dict:
    cfg = config.load_yaml("guard.yaml")["typo"]
    f = guard_features(ledger, history, sender, recipient, amount, minute)
    intended = f["_intended"]
    typo = None
    if (f["first_ever"] and intended["found"] and intended["distance"] is not None
            and intended["distance"] <= cfg["max_distance"] and intended["count"] >= cfg["min_earlier_sends"]):
        typo = {"candidate": intended["candidate"], "count": intended["count"], "positions": intended["positions"]}
    model_row = {k: v for k, v in f.items() if not k.startswith("_")}
    p = float(guard.p_scam([model_row])[0])
    anomaly = float(guard.anomaly_norm([model_row])[0])
    risk = float(guard.risk([model_row])[0])
    band = band_for(risk, typo is not None)
    reasons = reasons_for(f, typo) if band != "allow" else []
    return {
        "risk": round(risk), "band": band, "p_scam": round(p, 4), "anomaly": round(anomaly, 3),
        "typo": typo, "reasons": reasons, "advice": ADVICE if band != "allow" else None,
        "features": {k: (round(v, 3) if isinstance(v, float) else v) for k, v in model_row.items()},
    }


def make_model(seed: int = 42) -> LGBMClassifier:
    return LGBMClassifier(n_estimators=400, learning_rate=0.05, num_leaves=15, min_child_samples=10,
                          scale_pos_weight=20.0, random_state=seed, verbose=-1)
