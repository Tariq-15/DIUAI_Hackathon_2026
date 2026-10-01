"""Queue simulation: how much money is still holdable when an agent gets to each case?

Uses the held-out test cases and the real synthetic ledger: for each case, the money that can be held
at the moment an agent acts is read from the recipient's actual balance at that time. Policies
handle the same arrivals with the same agents:
  fcfs        first come, first served (today's default)
  largest     largest disputed amount first (a strong simple baseline)
  ferot       Ferot's priority: expected taka lost if the case waits, from the M5 curve, at decision time
  ferot_fast  Ferot's priority plus shorter handling from the pre-built case file (ASSUMPTION: 50% shorter)
  oracle      knows each recipient's future balance: the ceiling for any ordering policy

Agents work Sunday to Thursday, 09:00-17:00 (Bangladesh working week), so cases that arrive at night
or on Friday/Saturday queue up, which is when ordering matters. Assumptions live in this file's
SIM dict and are reported alongside the results.
"""

from __future__ import annotations

import heapq
import json

import numpy as np
import pandas as pd

from ferot import config
from ferot.features.ledger import load_ledger
from ferot.models.train import load_models

SIM = {"agents": 2, "service_minutes_median": 30, "service_sigma": 0.4, "shift": [9, 17], "seeds": 30,
       "workdays": [6, 0, 1, 2, 3],  # Python weekday numbers: Sunday=6, Monday=0 ... Thursday=3
       "priority_wait_minutes": 1440, "ferot_fast_service_factor": 0.5}
POLICIES = ["fcfs", "largest", "ferot", "ferot_fast", "oracle"]


def _prepare() -> pd.DataFrame:
    s = config.settings()
    table = pd.read_parquet(s.artifact_dir / "feature_table.parquet")
    cases = load_ledger().world.cases.set_index("case_id")
    test = table[(table["split"] == "test") & (table["golden"] == "")].copy()
    test["complaint_minute"] = test["case_id"].map(cases["complaint_minute"]).astype(int)
    test["recipient"] = test["case_id"].map(cases["recipient"])
    test["disputed_trx_id"] = test["case_id"].map(cases["disputed_trx_id"])
    test = test.sort_values("complaint_minute").reset_index(drop=True)
    rec = load_models()["recoverability"]
    test["curve"] = [rec.curve(r, r["recoverable_now"]) for r in test.to_dict("records")]
    return test


def _next_shift_minute(start: pd.Timestamp, minute: int) -> int:
    """Earliest minute >= `minute` inside a working shift."""
    lo, hi = SIM["shift"]
    m = minute
    for _ in range(14 * 24):
        t = start + pd.Timedelta(minutes=m)
        if t.weekday() in SIM["workdays"] and lo <= t.hour < hi:
            return m
        m = int((m // 60 + 1) * 60)
    return m


def _holdable(ledger, row, minute: int) -> float:
    if row["case_type"] not in ("genuine_wrong_send", "scam_victim") or row["tech_failure"]:
        return 0.0
    return float(min(row["amount"], max(ledger.balance_at(row["recipient"], minute), 0.0)))


def _run(test: pd.DataFrame, policy: str, seed: int) -> dict:
    ledger = load_ledger()
    rng = np.random.default_rng(seed)
    start = ledger.start
    arrivals = test["complaint_minute"].to_numpy() + rng.integers(0, 30, len(test))
    service = np.exp(rng.normal(np.log(SIM["service_minutes_median"]), SIM["service_sigma"], len(test)))
    if policy == "ferot_fast":
        service = service * SIM["ferot_fast_service_factor"]
    W = SIM["priority_wait_minutes"]
    xs = [[p["minutes"] for p in c] for c in test["curve"]]
    ys = [[p["expected"] for p in c] for c in test["curve"]]
    rows = [test.iloc[i] for i in range(len(test))]

    def score(i: int, t: int) -> float:
        if policy == "largest":
            return float(rows[i]["amount"])
        if policy == "oracle":
            return _holdable(ledger, rows[i], t) - _holdable(ledger, rows[i], t + W)
        e = t - arrivals[i]  # Ferot re-scores at decision time: the money still at risk now
        return float(np.interp(e, xs[i], ys[i]) - np.interp(e + W, xs[i], ys[i]))
    free_at = [0] * SIM["agents"]
    heapq.heapify(free_at)
    waiting: list[int] = []
    nxt = 0
    order = np.argsort(arrivals, kind="stable")
    recovered, delays = np.zeros(len(test)), np.zeros(len(test))
    handled = 0
    while handled < len(test):
        agent_free = heapq.heappop(free_at)
        t = _next_shift_minute(start, agent_free)
        while nxt < len(order) and arrivals[order[nxt]] <= t:
            waiting.append(int(order[nxt]))
            nxt += 1
        if not waiting:
            t = _next_shift_minute(start, int(arrivals[order[nxt]]))
            while nxt < len(order) and arrivals[order[nxt]] <= t:
                waiting.append(int(order[nxt]))
                nxt += 1
        if policy == "fcfs":
            pick = min(waiting, key=lambda i: arrivals[i])
        else:
            pick = max(waiting, key=lambda i: score(i, t))
        waiting.remove(pick)
        done = t + int(service[pick])
        recovered[pick] = _holdable(ledger, rows[pick], done)
        delays[pick] = done - arrivals[pick]
        heapq.heappush(free_at, done)
        handled += 1
    return {"recovered": float(recovered.sum()), "median_minutes_to_action": float(np.median(delays)),
            "p90_minutes_to_action": float(np.percentile(delays, 90))}


def run_and_save() -> dict:
    test = _prepare()
    eligible = test[test["case_type"].isin(["genuine_wrong_send", "scam_victim"]) & (test["tech_failure"] == 0)]
    results = {p: [] for p in POLICIES}
    for seed in range(SIM["seeds"]):
        for p in POLICIES:
            if p == "oracle" and seed >= 10:
                continue  # the oracle is slow; 10 seeds are enough for a ceiling
            results[p].append(_run(test, p, seed))
    summary = {}
    for p in POLICIES:
        rec = np.array([r["recovered"] for r in results[p]])
        summary[p] = {"recovered_mean": round(float(rec.mean()), 0),
                      "median_minutes_to_action": round(float(np.mean([r["median_minutes_to_action"] for r in results[p]])), 0),
                      "p90_minutes_to_action": round(float(np.mean([r["p90_minutes_to_action"] for r in results[p]])), 0)}
    fcfs = np.array([r["recovered"] for r in results["fcfs"]])
    for p in ("largest", "ferot", "ferot_fast", "oracle"):
        diff = np.array([r["recovered"] for r in results[p]]) - fcfs[:len(results[p])]
        half = 1.96 * diff.std(ddof=1) / np.sqrt(len(diff))
        summary[p]["gain_vs_fcfs"] = round(float(diff.mean()), 0)
        summary[p]["gain_vs_fcfs_ci95"] = [round(float(diff.mean() - half), 0), round(float(diff.mean() + half), 0)]
        summary[p]["gain_vs_fcfs_pct"] = round(float(diff.mean() / fcfs.mean() * 100), 1)
    out = {"summary": summary, "assumptions": SIM, "cases": int(len(test)),
           "eligible_cases": int(len(eligible)), "disputed_taka_eligible": round(float(eligible["amount"].sum()), 0),
           "note": "Synthetic ledger, held-out test window. Service times and staffing are assumptions."}
    reports = config.ROOT / "reports"
    reports.mkdir(exist_ok=True)
    (reports / "simulation.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    return out
