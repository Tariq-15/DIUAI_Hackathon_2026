"""Amount habits: how much does this customer usually send, and recharge? Learned where the data lives.

    python -m src.fl.amounts     # -> artifacts/portable/amount_habits.json + amount_profiles.npz,
                                 #    reports/federated_amounts.json

On the phone (it never leaves): the customer's last 30 Send Money amounts and last 30 mobile recharges, with their
times. From them the phone knows the usual amount (median and middle half), how often, and the usual total on a
day the customer uses the app.

Across phones (federated analytics): how far from the usual amount is UNUSUAL? Each phone turns its own history
into two histograms: how far each transfer was from its own usual amount (log2 of amount / median of the earlier
ones), and how far each 24-hour total was from its usual day. The phone normalises them (every phone weighs the
same, so one phone changes the release by at most a fixed amount), adds its share of Gaussian noise and sends them
through secure aggregation (src/fl/ondevice.secure_sum); the server sees only the noisy sum over a group of phones.
From the population histogram it sets each threshold where under 1 in 100 transfers would be above it.
No phone sends an amount, a recipient or a date; labels are never used (a phone does not know which of its own
transfers were fraud).

Evaluated on the held-out test window: the share of honest transfers that would get a check (friction) and the
share of fraud transfers that would, per fraud role and scenario. The live rule only adds a one-tap check (NUDGE)
on top of the model; it never blocks money on its own.

The real dataset is used here: every wallet in the 683k-row synthetic log is one phone.
"""
from __future__ import annotations

import json
import math
from collections import deque

import numpy as np
import pandas as pd

from src.common.config import ROOT, load_config
from src.fl.ondevice import epsilon, secure_sum
from src.serve.habits import FLOORS, KEEP, MIN_DAYS, MIN_TXNS, habit, ratios    # the same arithmetic as on the phone

TYPES = {"send": "SEND_MONEY", "recharge": "MOBILE_RECHARGE"}
EDGES = np.round(np.concatenate([[-6.0], np.arange(-2.0, 5.0001, 0.25), [5.5, 6.0, 7.0, 8.0]]), 2)   # log2 ratio bins;
# fine where thresholds fall, wide in the empty tail (fewer cells = less noise in the tail sums); the ends are open
TARGETS = {"send": 0.0075, "recharge": 0.004}   # share of all transfers above each threshold; recharges are stricter
# because the data has no recharge fraud to catch, so a recharge check is almost always friction
VICTIM_ROLES = ("victim_payment", "coerced_send", "buyer_payment", "takeover_drain")


def _bin(x: float) -> int:
    return int(np.clip(np.searchsorted(EDGES, x, side="right") - 1, 0, len(EDGES) - 2))


# ---------------------------------------------------------------- replay each phone's own history
def replay(tx: pd.DataFrame, kind: str):
    """Walk every wallet's transfers of one type in time order. Yields per row: the two log2 ratios against the
    phone's own earlier habit (NaN when there is too little history), plus the final last-30 profiles."""
    d = tx[tx.txn_type == TYPES[kind]].sort_values(["sender_id", "tsec"], kind="stable")
    w, t, a = d.sender_id.to_numpy(), d.tsec.to_numpy(), d.amount.to_numpy(float)
    r_amt = np.full(len(d), np.nan)
    r_day = np.full(len(d), np.nan)
    day_ok = np.zeros(len(d), bool)                # the 24-hour total (with this one) reaches the day floor
    profiles = {}
    i = 0
    while i < len(d):
        j = i
        while j < len(d) and w[j] == w[i]:
            j += 1
        prev: deque = deque(maxlen=KEEP)
        for k in range(i, j):
            h = habit(list(prev), int(t[k]))
            ra, rd = ratios(h, a[k])
            if ra is not None:
                r_amt[k] = math.log2(max(ra, 1e-6))
            if rd is not None:
                r_day[k] = math.log2(max(rd, 1e-6))
            day_ok[k] = h["last24"] + a[k] >= FLOORS[kind]["day"]
            prev.append((int(t[k]), float(a[k])))
        profiles[w[i]] = list(prev)
        i = j
    return d.assign(r_amt=r_amt, r_day=r_day, day_ok=day_ok), profiles


def phone_histograms(rows: pd.DataFrame, col: str, kind: str) -> tuple[np.ndarray, np.ndarray]:
    """One normalised histogram per phone (rows of the returned matrix), from that phone's own transfers. The last
    cell counts the transfers that can never be checked (too little history yet, or below the public floor), so
    the server learns what share of ALL transfers sits above each ratio."""
    if col == "r_amt":
        ok = rows[col].notna() & (rows.amount >= FLOORS[kind]["amount"])
    else:
        ok = rows[col].notna() & rows.day_ok
    owners, idx = np.unique(rows.sender_id.to_numpy(), return_inverse=True)
    vals = rows[col].to_numpy()
    nb = len(EDGES) - 1
    bins = np.where(ok.to_numpy(), [_bin(x) if x == x else 0 for x in vals], nb)
    h = np.zeros((len(owners), nb + 1))
    np.add.at(h, (idx, bins), 1.0)
    return h / h.sum(axis=1, keepdims=True), owners


def threshold_from(hist: np.ndarray, target: float) -> float:
    """Smallest bin edge with at most `target` of all transfers above it, as a ratio (2 ** edge). The noisy sums are
    used as they are (no clipping at zero, which would bias the tail upwards); the noise averages out in the tail."""
    p = hist / max(hist.sum(), 1e-12)
    tail = np.cumsum(p[:-1][::-1])[::-1]               # share of all transfers at or above each ratio bin
    k = int(np.argmax(tail <= target)) if (tail <= target).any() else len(tail) - 1
    return float(2 ** EDGES[k])


def federate(hists: list[np.ndarray], sigma: float, group: int, rng) -> list[np.ndarray]:
    """Each phone adds its 1/group share of the noise and its report goes through masked secure aggregation;
    the server adds up the group sums it receives. Returns the noisy population histograms."""
    out = []
    for h in hists:
        share = sigma / math.sqrt(group)
        rep = h + rng.normal(0, share, size=h.shape)
        tot = np.zeros(h.shape[1])
        for g in range(0, len(rep), group):
            part, _ = secure_sum(rep[g:g + group], rng)
            tot += part
        out.append(tot)
    return out


# ---------------------------------------------------------------- run
def run(cfg=None, sigma: float = 6.0, group: int = 12_000, seed: int = 11, verbose: bool = True) -> dict:
    cfg = cfg or load_config()
    from src.common.config import resolve
    d = resolve(cfg, "data_dir")
    start = pd.Timestamp(cfg["world"]["start_date"])
    tx = pd.read_parquet(d / "transactions.parquet", columns=["txn_id", "ts", "txn_type", "sender_id", "sender_type",
                                                                "amount", "status"])
    tx = tx[(tx.status == "SUCCESS") & (tx.sender_type == "C") & tx.txn_type.isin(TYPES.values())]
    lab = pd.read_parquet(d / "labels.parquet", columns=["txn_id", "is_fraud", "scenario", "fraud_role", "split"])
    tx = tx.merge(lab, on="txn_id", how="left")
    tx["tsec"] = ((tx.ts - start).dt.total_seconds()).astype(np.int64)
    rng = np.random.default_rng(seed)
    out, profiles, learn = {}, {}, {}
    for kind in TYPES:
        rows, prof = replay(tx, kind)
        profiles[kind] = prof
        learn[kind] = rows[rows.split.isin(["train", "val"])]
        out[kind] = rows
    # phones release four normalised histograms; one phone moves the concatenated release by at most 2 in L2
    releases, phones = [], {}
    for kind in TYPES:
        for col in ("r_amt", "r_day"):
            h, owners = phone_histograms(learn[kind], col, kind)
            releases.append((kind, col, h))
            phones[(kind, col)] = len(owners)
    noisy = federate([h for *_, h in releases], sigma, group, rng)
    sens = math.sqrt(len(releases))                   # each release has L2 norm <= 1 per phone
    eps = epsilon(1, sens, sigma)
    thr, hist = {k: {} for k in TYPES}, {k: {} for k in TYPES}
    for (kind, col, h), nz in zip(releases, noisy):
        key = "amount_ratio" if col == "r_amt" else "day_ratio"
        central = threshold_from(h.sum(axis=0), TARGETS[kind])
        fed = threshold_from(nz, TARGETS[kind])
        lr = learn[kind]
        ok = (lr.amount >= FLOORS[kind]["amount"]) if col == "r_amt" else lr.day_ok
        pooled = np.where(ok & lr[col].notna(), lr[col].fillna(-99), -99.0)     # transaction-weighted, same floors
        txn_q = float(2 ** np.quantile(pooled, 1 - TARGETS[kind])) if (pooled > -99).mean() > TARGETS[kind] else None
        thr[kind][key] = round(fed, 3)
        hist[kind][key] = dict(phones=phones[(kind, col)], federated_threshold=round(fed, 3),
                               central_threshold=round(central, 3), pooled_transaction_quantile=round(txn_q, 3) if txn_q else None,
                               federated=[round(float(x), 2) for x in nz[:-1]], central=[round(float(x), 2) for x in h.sum(axis=0)[:-1]],
                               never_checked_share=round(float(h.sum(axis=0)[-1] / h.sum()), 3))
    # held-out test window: who would get a check?
    evaluation = {}
    for kind in TYPES:
        r = out[kind][out[kind].split == "test"].copy()
        t = thr[kind]
        fa = (r.r_amt >= math.log2(t["amount_ratio"])) & (r.amount >= FLOORS[kind]["amount"])
        fd = (r.r_day >= math.log2(t["day_ratio"])) & r.day_ok
        r["flag"] = (fa | fd).fillna(False)
        legit, fraud = r[r.is_fraud == 0], r[r.is_fraud == 1]
        ev = dict(rows=int(len(r)), honest_rows=int(len(legit)), honest_checked_share=round(float(legit.flag.mean()), 4),
                  honest_with_habit_share=round(float(legit.r_amt.notna().mean()), 3), fraud_rows=int(len(fraud)))
        if len(fraud):
            ev["fraud_checked_share"] = round(float(fraud.flag.mean()), 3)
            vic = fraud[fraud.fraud_role.isin(VICTIM_ROLES)]
            ev["victim_side_rows"] = int(len(vic))
            ev["victim_side_checked_share"] = round(float(vic.flag.mean()), 3) if len(vic) else None
            ev["by_role"] = {k: dict(rows=int(len(g)), checked=round(float(g.flag.mean()), 3))
                             for k, g in fraud.groupby("fraud_role")}
            ev["by_scenario"] = {k: dict(rows=int(len(g)), checked=round(float(g.flag.mean()), 3))
                                 for k, g in fraud.groupby("scenario")}
        evaluation[kind] = ev
    result = dict(
        method="federated analytics: per-phone normalised histograms of log2(amount / own usual amount) and "
               "log2(24-hour total / own usual active-day total); distributed Gaussian noise + secure aggregation "
               "(ring masks, mod 2^64); each threshold is set where 0.75% (Send Money) or 0.4% (recharge) of all transfers are above it",
        simulated_protocol=True, real_dataset=True, phones=int(tx.sender_id.nunique()), group_size=group, noise_sigma=sigma,
        l2_sensitivity=round(sens, 3), epsilon_total=round(eps, 2), delta=1e-5, target_share=TARGETS, keep=KEEP,
        min_history=dict(transfers=MIN_TXNS, days=MIN_DAYS), floors=FLOORS, edges=EDGES.tolist(), thresholds=thr,
        histograms=hist, evaluation=evaluation,
        on_phone=["the last 30 amounts of each type and their times", "the usual amount, range and active-day total"],
        leaves_phone=[f"one noisy, masked vector of 4 x {len(EDGES)} numbers (normalised histograms), once"],
        never_leaves=["amounts", "recipients", "numbers recharged", "dates and times"],
        limits=["The protocol is simulated; the histograms come from the real 683k-row synthetic log.",
                "Recharge amounts in the synthetic data do not depend on the customer, so the recharge habit is weaker "
                "than the Send Money habit; the test window numbers show it.",
                "Thresholds target 0.75% (Send Money) and 0.4% (recharge) of all transfers per check, weighting every phone the same; the test window shows the real per-transfer rate. The public floors keep small amounts from ever being checked."],
    )
    if verbose:
        for kind in TYPES:
            e, h = evaluation[kind], hist[kind]
            print(f"[amount habits] {kind}: unusual = amount >= {thr[kind]['amount_ratio']}x own usual "
                  f"(central {h['amount_ratio']['central_threshold']}x) or 24 h total >= {thr[kind]['day_ratio']}x usual day "
                  f"(central {h['day_ratio']['central_threshold']}x); test window: {100 * e['honest_checked_share']:.2f}% of "
                  f"honest transfers checked" + (f", {100 * e['fraud_checked_share']:.1f}% of fraud, "
                                                  f"{100 * (e['victim_side_checked_share'] or 0):.1f}% victim-side"
                                                  if e.get('fraud_rows') else ""))
        print(f"[amount habits] {result['phones']:,} phones, epsilon {result['epsilon_total']} (delta 1e-5), groups of {group}")
    return dict(result=result, profiles=profiles)


def save_profiles(profiles: dict, path) -> None:
    """The phones' last-30 histories, as the live demo world needs them (one array per type, wallet offsets)."""
    wallets = sorted(set().union(*[p.keys() for p in profiles.values()]))
    arr = {"wallets": np.array(wallets)}
    for kind, prof in profiles.items():
        off, ts, am = [0], [], []
        for w in wallets:
            rows = prof.get(w, [])
            ts += [t for t, _ in rows]
            am += [a for _, a in rows]
            off.append(len(ts))
        arr[f"{kind}_offsets"] = np.asarray(off, np.int64)
        arr[f"{kind}_ts"] = np.asarray(ts, np.int64)
        arr[f"{kind}_amount"] = np.asarray(am, np.float32)
    np.savez_compressed(path, **arr)


def main():
    out = run()
    r = out["result"]
    art = ROOT / "artifacts" / "portable"
    art.mkdir(parents=True, exist_ok=True)
    save_profiles(out["profiles"], art / "amount_profiles.npz")
    live = dict(thresholds=r["thresholds"], floors=r["floors"], keep=r["keep"], min_history=r["min_history"],
                source=f"federated analytics over {r['phones']:,} phones, secure aggregation, epsilon {r['epsilon_total']} "
                       f"(delta 1e-5)")
    (art / "amount_habits.json").write_text(json.dumps(live), encoding="utf-8")
    (ROOT / "reports" / "federated_amounts.json").write_text(json.dumps(r, indent=1), encoding="utf-8")
    from .summary import write
    write()


if __name__ == "__main__":
    main()
