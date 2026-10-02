"""Amount habits at serving time: how much does this customer usually send or recharge, and is this one far from it?

The phone's side of src/fl/amounts.py. Each customer's last 30 Send Money amounts and last 30 mobile recharges
(from the synthetic log, then whatever they do in this demo session) give the usual amount, the usual range and the
usual total on an active day. The thresholds for "unusual" were learned across phones with federated analytics
(artifacts/portable/amount_habits.json). A plain rule turns an unusual amount into a one-tap check (NUDGE): the
customer sees their own usual next to this amount and decides. It never blocks money on its own.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from src.models.explain import bn as bn_num

DAY = 86_400
KEEP, MIN_TXNS, MIN_DAYS = 30, 5, 3
FLOORS = {"send": dict(amount=2000.0, day=5000.0), "recharge": dict(amount=200.0, day=500.0)}
KIND_OF = {"SEND_MONEY": "send", "MOBILE_RECHARGE": "recharge"}


def habit(prev: list[tuple[int, float]], now: int) -> dict:
    """What the phone knows before a new transfer: usual amount, usual range, usual active-day total, last 24 h."""
    if not prev:
        return dict(n=0, n_days=0, median=None, low=None, high=None, day_usual=None, last24=0.0, per_week=0.0, max=None)
    amts = np.fromiter((a for _, a in prev), float, len(prev))
    today = now // DAY
    days: dict[int, float] = {}
    for t, a in prev:
        if t // DAY != today:
            days[t // DAY] = days.get(t // DAY, 0.0) + a
    span = max((now - prev[0][0]) / DAY, 1.0)
    return dict(n=len(prev), n_days=len(days), median=float(np.median(amts)), low=float(np.percentile(amts, 25)),
                high=float(np.percentile(amts, 75)), max=float(amts.max()),
                day_usual=float(np.median(list(days.values()))) if len(days) >= MIN_DAYS else None,
                last24=float(sum(a for t, a in prev if now - t < DAY)), per_week=round(7 * len(prev) / span, 1))


def ratios(h: dict, amount: float) -> tuple[float | None, float | None]:
    r_amt = amount / h["median"] if h["n"] >= MIN_TXNS and h["median"] else None
    r_day = (h["last24"] + amount) / h["day_usual"] if h["n"] >= MIN_TXNS and h["day_usual"] else None
    return r_amt, r_day


def is_unusual(kind: str, h: dict, amount: float, thr: dict) -> tuple[bool, list[str]]:
    r_amt, r_day = ratios(h, amount)
    why = []
    if r_amt is not None and r_amt >= thr["amount_ratio"] and amount >= FLOORS[kind]["amount"]:
        why.append("amount")
    if r_day is not None and r_day >= thr["day_ratio"] and h["last24"] + amount >= FLOORS[kind]["day"]:
        why.append("day_total")
    return bool(why), why


def _tk(v: float) -> str:
    return f"Tk {v:,.0f}"


def _tkbn(v: float) -> str:
    return "৳" + bn_num(f"{v:,.0f}")


def _x(v: float) -> str:
    return f"{v:.0f}" if v >= 10 else f"{v:.1f}"


class Habits:
    """Last-30 histories per customer and type, plus this session's own transfers on top."""

    def __init__(self, folder: str | Path | None):
        self.ok = False
        self.extra: dict[tuple[str, str], list[tuple[int, float]]] = {}
        if folder is None:
            return
        folder = Path(folder)
        for d in (folder, folder / "portable"):
            if (d / "amount_profiles.npz").exists() and (d / "amount_habits.json").exists():
                cfg = json.loads((d / "amount_habits.json").read_text(encoding="utf-8"))
                z = np.load(d / "amount_profiles.npz")
                self.thr, self.source = cfg["thresholds"], cfg.get("source", "")
                self._idx = {str(w): i for i, w in enumerate(z["wallets"].tolist())}
                self._arr = {k: (z[f"{k}_offsets"], z[f"{k}_ts"], z[f"{k}_amount"]) for k in FLOORS}
                self.ok = True
                return

    def reset(self, extra: dict | None = None):
        self.extra = {k: list(v) for k, v in (extra or {}).items()}

    def history(self, wallet: str, kind: str) -> list[tuple[int, float]]:
        base = []
        i = self._idx.get(wallet) if self.ok else None
        if i is not None:
            off, ts, am = self._arr[kind]
            base = list(zip(ts[off[i]:off[i + 1]].tolist(), am[off[i]:off[i + 1]].astype(float).tolist()))
        return (base + self.extra.get((wallet, kind), []))[-KEEP:]

    def add(self, wallet: str, kind: str, amount: float, t: int):
        self.extra.setdefault((wallet, kind), []).append((int(t), float(amount)))

    def check(self, wallet: str, kind: str, amount: float, now: int) -> dict | None:
        """The habit next to this amount, and whether the learned thresholds call it unusual."""
        if not self.ok:
            return None
        prev = self.history(wallet, kind)
        h = habit(prev, now)
        r_amt, r_day = ratios(h, amount)
        flag, why = is_unusual(kind, h, amount, self.thr[kind])
        rnd = lambda v: None if v is None else round(v, 2)          # noqa: E731
        return dict(kind=kind, amount=float(amount), n=h["n"], enough=h["n"] >= MIN_TXNS, usual=rnd(h["median"]),
                    low=rnd(h["low"]), high=rnd(h["high"]), max=rnd(h["max"]), per_week=h["per_week"],
                    day_usual=rnd(h["day_usual"]), last24=rnd(h["last24"]), day_total=rnd(h["last24"] + amount),
                    ratio=rnd(r_amt), day_ratio=rnd(r_day), threshold=self.thr[kind]["amount_ratio"],
                    day_threshold=self.thr[kind]["day_ratio"], floor=FLOORS[kind]["amount"], day_floor=FLOORS[kind]["day"],
                    unusual=flag, why=why, history=[a for _, a in prev], source=self.source)

    def summary(self, wallet: str, now: int) -> dict:
        """What the app shows before the customer types an amount: 'you usually send ...'."""
        out = {}
        for kind in FLOORS:
            c = self.check(wallet, kind, 0.0, now)
            if c:
                out[kind] = {k: c[k] for k in ("n", "enough", "usual", "low", "high", "max", "per_week", "day_usual", "last24",
                                                "threshold", "day_threshold", "floor", "day_floor")}
        return out

    @staticmethod
    def reason(c: dict) -> dict:
        """The customer-facing sentence, with the customer's own numbers."""
        verb_en, verb_bn = ("send", "পাঠান") if c["kind"] == "send" else ("recharge", "রিচার্জ করেন")
        if "amount" in c["why"]:
            en = (f"Unusual amount for you: you usually {verb_en} about {_tk(c['usual'])} "
                  f"({_tk(c['low'])} to {_tk(c['high'])} in your last {c['n']}); {_tk(c['amount'])} is {_x(c['ratio'])} times that")
            bn = (f"আপনার জন্য অস্বাভাবিক পরিমাণ: সাধারণত আপনি প্রায় {_tkbn(c['usual'])} {verb_bn} (শেষ {bn_num(c['n'])}টিতে "
                  f"{_tkbn(c['low'])} থেকে {_tkbn(c['high'])}); {_tkbn(c['amount'])} তার {bn_num(_x(c['ratio']))} গুণ")
        else:
            en = (f"Unusual total for one day: with this, {_tk(c['day_total'])} in 24 hours; on a day you use upay you usually "
                  f"{verb_en} about {_tk(c['day_usual'])}")
            bn = (f"এক দিনের জন্য অস্বাভাবিক মোট: এটিসহ ২৪ ঘণ্টায় {_tkbn(c['day_total'])}; যেদিন upay ব্যবহার করেন, "
                  f"সাধারণত প্রায় {_tkbn(c['day_usual'])} {verb_bn}")
        return dict(code="unusual_amount", feature="amount_habit", shap=None, en=en, bn=bn)
