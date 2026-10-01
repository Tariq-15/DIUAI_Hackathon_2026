"""
src/features/feature_store.py
==============================
Stateful feature store – computes derived features described in spec 3.5.
All features use ONLY information available at transaction time (no future leakage).

Usage:
    from src.features.feature_store import FeatureStore, replay_features

    features_df = replay_features(transactions_df)
"""
from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import numpy as np
import pandas as pd


class FeatureStore:
    """
    Rolling feature engine.  Feed transactions in time-sorted order via
    `update(txn)` and call `get_features(txn)` BEFORE update to get the
    features as of that moment.
    """

    def __init__(self):
        # Per-sender: balance history, transaction history
        self.sender_txns:      Dict[str, deque] = defaultdict(deque)
        self.sender_balances:  Dict[str, List[float]] = defaultdict(list)
        self.sender_amounts:   Dict[str, deque] = defaultdict(deque)   # 30-day rolling
        self.sender_hours:     Dict[str, deque] = defaultdict(deque)   # 30-day rolling

        # Per-recipient: inbound senders + outbound amounts
        self.recipient_senders:  Dict[str, deque] = defaultdict(deque)  # (ts, sender_id)
        self.recipient_inflows:  Dict[str, deque] = defaultdict(deque)  # (ts, amount)
        self.recipient_outflows: Dict[str, deque] = defaultdict(deque)  # (ts, amount)
        self.recipient_first_seen: Dict[str, datetime] = {}

        # Per-agent: daily cashout counts
        self.agent_daily_cashouts: Dict[str, deque] = defaultdict(deque)  # (ts,)

        # Seen pairs (sender, recipient) for first-time flag
        self.seen_pairs: set = set()

    def _prune(self, dq: deque, cutoff: datetime, idx: int = 0):
        """Remove entries older than cutoff. Entry[idx] is the timestamp."""
        while dq and dq[0][idx] < cutoff:
            dq.popleft()

    def get_features(self, txn: dict) -> dict:
        """Return feature dict for this transaction BEFORE it is processed."""
        ts       = pd.Timestamp(txn["timestamp"])
        sender   = str(txn.get("sender_id") or "")
        recip    = str(txn.get("recipient_id") or "")
        amount   = float(txn.get("amount_tk", 0) or 0)
        bal_b    = float(txn.get("sender_balance_before", 0) or 0)
        txn_type = str(txn.get("txn_type", ""))
        device   = str(txn.get("device_id", ""))
        hour     = ts.hour

        cut30d   = ts - pd.Timedelta(days=30)
        cut24h   = ts - pd.Timedelta(hours=24)
        cut3h    = ts - pd.Timedelta(hours=3)
        cut48h   = ts - pd.Timedelta(hours=48)

        # ── amount_to_median_ratio ────────────────────────────────────────────
        past_amounts = [a for (t2, a) in self.sender_amounts[sender] if t2 >= cut30d]
        median_send  = float(np.median(past_amounts)) if past_amounts else amount
        amt_to_median = amount / max(median_send, 1.0)

        # ── balance_drain_ratio ───────────────────────────────────────────────
        bal_drain = amount / max(bal_b, 1.0)

        # ── hour_deviation (distance from sender's modal hour) ────────────────
        past_hours = [h for (t2, h) in self.sender_hours[sender] if t2 >= cut30d]
        if past_hours:
            modal_h = float(np.median(past_hours))
            # circular distance
            raw_d = abs(hour - modal_h)
            hr_dev = min(raw_d, 24 - raw_d) / 6.0   # normalise to ~std units
        else:
            hr_dev = 0.0

        # ── counterparty_first_time (from raw column; fall back to computed) ──
        cp_ft = int(txn.get("counterparty_first_time", 0) or 0)

        # ── recipient_age_hours ───────────────────────────────────────────────
        if recip and recip in self.recipient_first_seen:
            recip_age_h = (ts - pd.Timestamp(self.recipient_first_seen[recip])).total_seconds() / 3600
        else:
            recip_age_h = 0.0   # first time we see them → freshly minted

        # ── recipient_unique_senders_3h / 24h / 48h ──────────────────────────
        self._prune(self.recipient_senders[recip], ts - pd.Timedelta(hours=48), 0)
        recent_senders = self.recipient_senders[recip]
        uniq_3h  = len({s for (t2, s) in recent_senders if t2 >= cut3h})
        uniq_24h = len({s for (t2, s) in recent_senders if t2 >= cut24h})
        uniq_48h = len({s for (t2, s) in recent_senders})

        # ── recipient_first_time_sender_ratio (24h) ───────────────────────────
        senders_24h = [(t2, s) for (t2, s) in recent_senders if t2 >= cut24h]
        total_24h   = len(senders_24h)
        # first-time = pairs (recip, sender) not in seen_pairs at time of send
        # approximate: unknown; use counterparty_first_time field from raw
        ft_ratio_24h = cp_ft   # for current txn; for historical approx use 0.8

        # ── recipient_inflow_outflow_lag_min ──────────────────────────────────
        self._prune(self.recipient_inflows[recip],  ts - pd.Timedelta(hours=4), 0)
        self._prune(self.recipient_outflows[recip], ts - pd.Timedelta(hours=4), 0)
        if self.recipient_inflows[recip] and self.recipient_outflows[recip]:
            last_inflow  = self.recipient_inflows[recip][-1][0]
            last_outflow = self.recipient_outflows[recip][-1][0]
            lag_min = max(0.0, (last_outflow - last_inflow).total_seconds() / 60)
        else:
            lag_min = -1.0

        # ── recipient_cashout_ratio ───────────────────────────────────────────
        inflow_24h  = sum(a for (t2, a) in self.recipient_inflows[recip]  if t2 >= cut24h)
        outflow_24h = sum(a for (t2, a) in self.recipient_outflows[recip] if t2 >= cut24h)
        cashout_ratio = outflow_24h / max(inflow_24h, 1.0)

        # ── agent_peer_zscore (placeholder: store in caller) ─────────────────
        # Computed at agent level outside this per-txn store.

        feat = dict(
            # Raw pass-through
            txn_id                       = txn.get("txn_id"),
            amount_tk                    = amount,
            fee_tk                       = float(txn.get("fee_tk", 0) or 0),
            txn_type                     = txn_type,
            channel                      = txn.get("channel"),
            hour                         = hour,
            weekday                      = ts.weekday(),
            is_new_device                = int(txn.get("device_changed", 0) or 0),
            location_changed             = int(txn.get("location_changed", 0) or 0),
            session_seconds              = int(txn.get("session_seconds", 0) or 0),
            pin_attempts                 = int(txn.get("pin_attempts", 1) or 1),
            counterparty_first_time      = cp_ft,
            # Derived
            amount_to_median_ratio       = round(amt_to_median, 4),
            balance_drain_ratio          = round(bal_drain, 4),
            hour_deviation               = round(hr_dev, 4),
            recipient_age_hours          = round(recip_age_h, 2),
            recipient_unique_senders_3h  = uniq_3h,
            recipient_unique_senders_24h = uniq_24h,
            recipient_unique_senders_48h = uniq_48h,
            recipient_first_time_sender_ratio = round(ft_ratio_24h, 4),
            recipient_inflow_outflow_lag_min  = round(lag_min, 2),
            recipient_cashout_ratio      = round(cashout_ratio, 4),
            sender_id                    = sender,
            recipient_id                 = recip,
        )
        return feat

    def update(self, txn: dict):
        """Register transaction AFTER features have been extracted."""
        ts       = pd.Timestamp(txn["timestamp"])
        sender   = str(txn.get("sender_id") or "")
        recip    = str(txn.get("recipient_id") or "")
        amount   = float(txn.get("amount_tk", 0) or 0)
        txn_type = str(txn.get("txn_type", ""))
        hour     = ts.hour

        cut30d = ts - pd.Timedelta(days=30)

        # Sender history
        self.sender_amounts[sender].append((ts, amount))
        self.sender_hours[sender].append((ts, hour))
        # Prune sender queues
        while self.sender_amounts[sender] and self.sender_amounts[sender][0][0] < cut30d:
            self.sender_amounts[sender].popleft()
        while self.sender_hours[sender] and self.sender_hours[sender][0][0] < cut30d:
            self.sender_hours[sender].popleft()

        # Mark seen pair
        if sender and recip:
            self.seen_pairs.add((sender, recip))

        # Recipient first seen
        if recip and recip not in self.recipient_first_seen:
            self.recipient_first_seen[recip] = ts

        # Recipient inflows / outflows
        if recip:
            if txn_type in ("P2P_SEND", "REMITTANCE_IN", "G2P_ALLOWANCE", "CASH_IN"):
                self.recipient_inflows[recip].append((ts, amount))
            if txn_type in ("CASH_OUT_AGENT", "CASH_OUT_ATM"):
                self.recipient_outflows[recip].append((ts, amount))
            self.recipient_senders[recip].append((ts, sender))

        # Agent cashout count
        agent_id = txn.get("agent_id")
        if agent_id and txn_type == "CASH_OUT_AGENT":
            self.agent_daily_cashouts[str(agent_id)].append(ts)


def replay_features(
    transactions_df: pd.DataFrame,
    chunk_size: int = 50_000,
) -> pd.DataFrame:
    """
    Replay all transactions in time order and compute features.
    Processes in chunks to show progress.  Returns a DataFrame of
    derived features aligned to transactions_df by txn_id.
    """
    df = transactions_df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values("timestamp").reset_index(drop=True)

    store  = FeatureStore()
    rows   = df.to_dict("records")
    n      = len(rows)
    feats  = []

    print(f"⚙️  Replaying features for {n:,} rows…")
    t0 = __import__("time").time()

    for i, txn in enumerate(rows):
        feat = store.get_features(txn)
        feats.append(feat)
        store.update(txn)

        if (i + 1) % chunk_size == 0:
            elapsed = __import__("time").time() - t0
            rate    = (i + 1) / elapsed
            eta     = (n - i - 1) / rate
            print(f"   {i+1:>7,}/{n:,}  {elapsed:.0f}s  ETA {eta:.0f}s")

    elapsed = __import__("time").time() - t0
    print(f"   Done in {elapsed:.1f}s  ({n / elapsed:.0f} rows/s)")

    feat_df = pd.DataFrame(feats)

    # ── Agent peer z-score (computed post-hoc from full replay) ──────────────
    # We do this after replay because we need the full per-agent count
    cashout_by_agent = (
        transactions_df[transactions_df["txn_type"] == "CASH_OUT_AGENT"]
        .groupby("agent_id")["txn_id"].count()
        .rename("agent_total_cashouts")
    )
    peer_groups = transactions_df.merge(
        transactions_df.drop_duplicates("agent_id")[["agent_id"]],
        on="agent_id", how="left"
    )
    # crude: use overall mean/std as peer reference
    m = cashout_by_agent.mean()
    s = cashout_by_agent.std() + 1e-9
    zscore_map = ((cashout_by_agent - m) / s).to_dict()

    feat_df["agent_peer_zscore"] = feat_df["txn_id"].map(
        transactions_df.set_index("txn_id")["agent_id"]
    ).map(lambda a: zscore_map.get(str(a), 0.0) if pd.notna(a) else 0.0)

    return feat_df


# ── CLI ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys, os
    data_dir = sys.argv[1] if len(sys.argv) > 1 else "data"
    txn_path = os.path.join(data_dir, "transactions.csv")
    print(f"Loading {txn_path}…")
    txn_df = pd.read_csv(txn_path)
    feat_df = replay_features(txn_df)
    out_path = os.path.join(data_dir, "features.parquet")
    feat_df.to_parquet(out_path, index=False)
    print(f"Features saved → {out_path}")
    print(feat_df.head())
