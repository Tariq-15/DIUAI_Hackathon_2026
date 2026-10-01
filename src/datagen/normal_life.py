"""
src/datagen/normal_life.py
===========================
Module 3 – simulate_normal_life()

Generates ~597,000 legitimate transaction rows following Part 4 rules:
  • Lognormal amounts per income band
  • 80/20 regular/new contact split
  • Friday / salary-day / Eid / bill-day calendar effects
  • Realistic hour distribution (peaks 08-10, 12-14, 19-22; <2% night)
  • Channel by device type
  • Merchants, remittance, G2P disbursements
  • Stateful balance tracking per wallet (no negative balances)

Returns a list of raw transaction dicts (no labels).
"""
from __future__ import annotations

import itertools
import uuid
from datetime import datetime, timedelta, timezone as tz
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
from types import SimpleNamespace


# ── internal helpers ──────────────────────────────────────────────────────────

def _make_txn_id(counter: itertools.count) -> str:
    return f"T{next(counter):08d}"


def _fee(cfg: SimpleNamespace, txn_type: str, amount: float) -> float:
    fee_rate = cfg.fees.__dict__.get(txn_type, 0.0)
    return round(amount * fee_rate, 2)


def _draw_amount(rng: np.random.Generator, median: float,
                 kyc_max: float, multiplier: float = 1.0) -> float:
    """Draw from lognormal centred on *median*, capped at *kyc_max*."""
    mu    = np.log(median * multiplier)
    sigma = 0.6
    raw   = float(np.exp(rng.normal(mu, sigma)))
    # cap, round to nearest 10 Tk
    raw   = min(raw, kyc_max)
    raw   = max(10.0, raw)
    return round(raw / 10) * 10


def _pick_hour(rng: np.random.Generator, weights: np.ndarray) -> int:
    return int(rng.choice(24, p=weights))


def _random_second(rng: np.random.Generator) -> int:
    return int(rng.integers(0, 3600))


def _channel_for_device(rng: np.random.Generator, device_type: str) -> str:
    if device_type == "USSD-only":
        return "USSD"
    elif device_type == "feature_phone":
        return rng.choice(["USSD", "AGENT_ASSISTED"], p=[0.70, 0.30])
    else:
        return rng.choice(["APP", "USSD", "AGENT_ASSISTED"], p=[0.60, 0.25, 0.15])


def _is_in_window(ts: datetime, cfg: SimpleNamespace) -> bool:
    return cfg.sim_start_dt <= ts <= cfg.sim_end_dt + timedelta(hours=23, minutes=59)


# ── day-level volume multiplier ───────────────────────────────────────────────

def _day_multiplier(dt: datetime, cfg: SimpleNamespace) -> float:
    mult = 1.0
    dom  = dt.day
    dow  = dt.weekday()   # 0=Mon … 6=Sun; Friday=4

    if dow == 4:           # Friday
        mult *= cfg.friday_uplift

    if dom in cfg.salary_days:
        # Salary cash-in uplift handled per type; here lift overall by 1.2
        mult *= 1.20

    bill_days_list = list(cfg.bill_days)
    if dom in bill_days_list:
        mult *= 1.10

    if cfg.eid_start_dt <= dt <= cfg.eid_end_dt + timedelta(days=1):
        mult *= cfg.eid_volume_multiplier

    return mult


# ── Main function ─────────────────────────────────────────────────────────────

def simulate_normal_life(
    cfg: SimpleNamespace,
    rng: np.random.Generator,
    customers: pd.DataFrame,
    agents: pd.DataFrame,
    profiles: Dict[str, dict],
    counter: itertools.count,
    target_normal_rows: int,
) -> List[dict]:
    """
    Returns list of transaction dicts for legitimate rows.
    Also mutates profiles[cid]['balance'] in place (stateful ledger).
    """

    txn_rows: List[dict] = []

    # Index for fast lookup
    cust_index = customers.set_index("customer_id")
    agent_ids  = agents["agent_id"].tolist()

    # Build merchant wallet ids (M0001..M0300)
    merchant_ids = [f"M{i+1:04d}" for i in range(cfg.n_merchants)]
    merchant_balances: Dict[str, float] = {m: 5000.0 for m in merchant_ids}

    # Remittance / G2P sources (trusted, non-customer ids)
    remit_sources = [f"REMIT-{i+1:02d}" for i in range(5)]
    g2p_sources   = [f"G2P-{i+1:02d}"  for i in range(3)]

    # Build list of active customers per day (those registered before that day)
    sim_start = cfg.sim_start_dt
    sim_end   = cfg.sim_end_dt + timedelta(hours=23, minutes=59)

    # Target txns per day (base)
    base_per_day = target_normal_rows / cfg.sim_days

    # Pre-build day sequence
    days = [sim_start + timedelta(days=d) for d in range(cfg.sim_days)]

    # All customer IDs as numpy array for fast random choice
    all_cids  = np.array(customers["customer_id"].tolist())
    all_cids_set = set(all_cids)

    # Per-customer daily tracking dict  (reset on new day)
    daily_sent: Dict[str, float] = {cid: 0.0 for cid in all_cids}
    current_day_str = ""

    # KYC caps helper
    def get_kyc_daily_cap(kyc: int) -> float:
        return float(cfg.kyc_caps[str(kyc)].daily_send_limit)

    def get_kyc_per_txn_cap(kyc: int) -> float:
        return float(cfg.kyc_caps[str(kyc)].per_txn_send_max)

    # Sender-recipient first-time tracking
    seen_pairs: set = set()

    for day in days:
        day_str = day.strftime("%Y-%m-%d")

        # Reset daily limits
        daily_sent = {cid: 0.0 for cid in all_cids}

        # Active customers = registered on or before this day
        active_mask = pd.to_datetime(customers["registration_date"]) <= pd.Timestamp(day)
        active_cids = customers.loc[active_mask, "customer_id"].tolist()
        if not active_cids:
            continue

        # Day multiplier
        dm = _day_multiplier(day, cfg)
        dom = day.day
        is_eid = cfg.eid_start_dt <= day <= cfg.eid_end_dt + timedelta(days=1)
        is_salary = dom in list(cfg.salary_days)
        is_bill   = dom in list(cfg.bill_days)

        n_today = int(base_per_day * dm)
        n_today = max(n_today, len(active_cids) // 4)

        day_txns: List[dict] = []

        for _ in range(n_today):
            sender_id = str(rng.choice(active_cids))
            prof      = profiles[sender_id]
            cust_row  = cust_index.loc[sender_id]
            kyc       = prof["kyc_level"]
            daily_cap = get_kyc_daily_cap(kyc)
            per_txn_cap = get_kyc_per_txn_cap(kyc)

            # Skip if daily cap exhausted
            if daily_sent.get(sender_id, 0.0) >= daily_cap * 0.95:
                continue

            # Pick transaction type
            type_keys = list(cfg.txn_type_mix.__dict__.keys())
            type_probs = np.array([cfg.txn_type_mix.__dict__[k] for k in type_keys])
            type_probs = type_probs / type_probs.sum()

            # Up-weight CASH_IN on salary days for garment workers / service holders
            if is_salary and prof["occupation"] in ("garment worker", "service holder"):
                ci_idx = type_keys.index("CASH_IN")
                type_probs[ci_idx] *= cfg.salary_cashin_uplift
                type_probs = type_probs / type_probs.sum()

            # Up-weight BILL_PAY on bill days
            if is_bill:
                bp_idx = type_keys.index("BILL_PAY")
                type_probs[bp_idx] *= cfg.bill_uplift
                type_probs = type_probs / type_probs.sum()

            txn_type = str(rng.choice(type_keys, p=type_probs))

            # Pick hour
            hour = _pick_hour(rng, prof["active_hour_weights"])
            sec  = _random_second(rng)
            ts   = day.replace(hour=hour, minute=0, second=0, microsecond=0) + timedelta(seconds=sec)

            # Eid amount multiplier (for 40% of customers)
            eid_mult = 1.0
            if is_eid and (hash(sender_id) % 10) < int(cfg.eid_customer_fraction * 10):
                eid_mult = float(rng.uniform(
                    cfg.eid_amount_multiplier - 0.5,
                    cfg.eid_amount_multiplier + 0.5
                ))

            # ── Build transaction based on type ──────────────────────────────
            if txn_type == "P2P_SEND":
                # 80 % to regular contact, 20 % to random / new
                contacts = prof["regular_contacts"]
                if contacts and rng.random() < cfg.regular_contact_p2p_share:
                    recipient_id = str(rng.choice(contacts))
                else:
                    recipient_id = str(rng.choice(all_cids))
                    while recipient_id == sender_id:
                        recipient_id = str(rng.choice(all_cids))

                amount = _draw_amount(
                    rng,
                    prof["median_send_tk"] * eid_mult,
                    min(per_txn_cap, cfg.global_p2p_max_txn, daily_cap - daily_sent.get(sender_id, 0.0))
                )
                if amount <= 0:
                    continue

                fee = _fee(cfg, txn_type, amount)
                total_out = amount + fee

                if prof["balance"] < total_out or total_out < 1:
                    continue

                # Update balances
                bal_before_s = prof["balance"]
                prof["balance"] -= total_out
                bal_after_s = prof["balance"]

                rcp_prof = profiles.get(recipient_id)
                if rcp_prof:
                    bal_before_r = rcp_prof["balance"]
                    rcp_prof["balance"] += amount
                    bal_after_r = rcp_prof["balance"]
                else:
                    bal_before_r = bal_after_r = None

                daily_sent[sender_id] = daily_sent.get(sender_id, 0.0) + amount
                pair = (sender_id, recipient_id)
                first_time = int(pair not in seen_pairs)
                seen_pairs.add(pair)

                channel = _channel_for_device(rng, prof["device_type"])
                session_seconds = max(10, int(rng.normal(42, 20)))
                pin_attempts    = 1

                day_txns.append(dict(
                    txn_id=_make_txn_id(counter),
                    timestamp=ts,
                    sender_id=sender_id,
                    recipient_id=recipient_id,
                    txn_type=txn_type,
                    amount_tk=amount,
                    fee_tk=fee,
                    sender_balance_before=round(bal_before_s, 2),
                    sender_balance_after=round(bal_after_s, 2),
                    recipient_balance_before=round(bal_before_r, 2) if bal_before_r is not None else None,
                    recipient_balance_after=round(bal_after_r, 2) if bal_after_r is not None else None,
                    channel=channel,
                    agent_id=None,
                    device_id=prof["device_id"],
                    device_changed=0,
                    location_changed=0,
                    session_seconds=session_seconds,
                    pin_attempts=pin_attempts,
                    counterparty_first_time=first_time,
                ))

            elif txn_type in ("CASH_OUT_AGENT", "CASH_OUT_ATM"):
                max_per_txn = (cfg.agent_cashout_max_txn
                               if txn_type == "CASH_OUT_AGENT"
                               else cfg.atm_cashout_max_txn)
                amount = _draw_amount(
                    rng,
                    prof["median_send_tk"] * 0.8 * eid_mult,
                    min(max_per_txn, daily_cap - daily_sent.get(sender_id, 0.0))
                )
                if amount <= 0:
                    continue

                fee = _fee(cfg, txn_type, amount)
                total_out = amount + fee

                if prof["balance"] < total_out:
                    continue

                bal_before_s = prof["balance"]
                prof["balance"] -= total_out
                bal_after_s  = prof["balance"]
                daily_sent[sender_id] = daily_sent.get(sender_id, 0.0) + amount

                agent_id_used = str(prof["home_agent_id"]) if txn_type == "CASH_OUT_AGENT" else None
                channel = "AGENT_ASSISTED" if txn_type == "CASH_OUT_AGENT" else "APP"

                day_txns.append(dict(
                    txn_id=_make_txn_id(counter),
                    timestamp=ts,
                    sender_id=sender_id,
                    recipient_id=None,
                    txn_type=txn_type,
                    amount_tk=amount,
                    fee_tk=fee,
                    sender_balance_before=round(bal_before_s, 2),
                    sender_balance_after=round(bal_after_s, 2),
                    recipient_balance_before=None,
                    recipient_balance_after=None,
                    channel=channel,
                    agent_id=agent_id_used,
                    device_id=prof["device_id"],
                    device_changed=0,
                    location_changed=0,
                    session_seconds=max(10, int(rng.normal(30, 10))),
                    pin_attempts=1,
                    counterparty_first_time=0,
                ))

            elif txn_type == "CASH_IN":
                # Cash-in from agent (money added to wallet)
                amount = _draw_amount(
                    rng,
                    prof["median_send_tk"] * 1.5,
                    min(cfg.kyc_caps[str(kyc)].daily_receive_limit,
                        float(cfg.kyc_caps[str(kyc)].max_balance) - prof["balance"])
                )
                if amount <= 10:
                    continue

                agent_id_used = str(prof["home_agent_id"])
                bal_before_s  = prof["balance"]
                prof["balance"] = min(prof["balance"] + amount,
                                      float(cfg.kyc_caps[str(kyc)].max_balance))
                bal_after_s   = prof["balance"]

                day_txns.append(dict(
                    txn_id=_make_txn_id(counter),
                    timestamp=ts,
                    sender_id=agent_id_used,
                    recipient_id=sender_id,
                    txn_type=txn_type,
                    amount_tk=amount,
                    fee_tk=0.0,
                    sender_balance_before=None,
                    sender_balance_after=None,
                    recipient_balance_before=round(bal_before_s, 2),
                    recipient_balance_after=round(bal_after_s, 2),
                    channel="AGENT_ASSISTED",
                    agent_id=agent_id_used,
                    device_id=prof["device_id"],
                    device_changed=0,
                    location_changed=0,
                    session_seconds=max(10, int(rng.normal(25, 8))),
                    pin_attempts=1,
                    counterparty_first_time=0,
                ))

            elif txn_type in ("AIRTIME", "BILL_PAY", "ADD_MONEY", "MERCHANT_PAY"):
                amount = _draw_amount(
                    rng,
                    prof["median_send_tk"] * 0.5,
                    min(per_txn_cap, daily_cap - daily_sent.get(sender_id, 0.0))
                )
                if amount <= 0:
                    continue
                if prof["balance"] < amount:
                    continue

                if txn_type == "MERCHANT_PAY":
                    recipient_id = str(rng.choice(merchant_ids))
                    merchant_balances[recipient_id] = merchant_balances.get(recipient_id, 0) + amount
                    bal_before_r  = merchant_balances[recipient_id] - amount
                    bal_after_r   = merchant_balances[recipient_id]
                else:
                    recipient_id = None
                    bal_before_r  = None
                    bal_after_r   = None

                bal_before_s  = prof["balance"]
                prof["balance"] -= amount
                bal_after_s   = prof["balance"]
                daily_sent[sender_id] = daily_sent.get(sender_id, 0.0) + amount

                day_txns.append(dict(
                    txn_id=_make_txn_id(counter),
                    timestamp=ts,
                    sender_id=sender_id,
                    recipient_id=recipient_id,
                    txn_type=txn_type,
                    amount_tk=amount,
                    fee_tk=0.0,
                    sender_balance_before=round(bal_before_s, 2),
                    sender_balance_after=round(bal_after_s, 2),
                    recipient_balance_before=round(bal_before_r, 2) if bal_before_r is not None else None,
                    recipient_balance_after=round(bal_after_r, 2) if bal_after_r is not None else None,
                    channel=_channel_for_device(rng, prof["device_type"]),
                    agent_id=None,
                    device_id=prof["device_id"],
                    device_changed=0,
                    location_changed=0,
                    session_seconds=max(5, int(rng.normal(20, 5))),
                    pin_attempts=1,
                    counterparty_first_time=0,
                ))

            elif txn_type == "REMITTANCE_IN":
                # Remittance to a random active customer from an external source
                recipient_id  = str(rng.choice(active_cids))
                rcp_prof      = profiles[recipient_id]
                rcp_kyc       = rcp_prof["kyc_level"]
                amount        = float(rng.uniform(5000, 30000))
                amount        = round(amount / 100) * 100

                source_id     = str(rng.choice(remit_sources))
                bal_before_r  = rcp_prof["balance"]
                rcp_prof["balance"] = min(
                    rcp_prof["balance"] + amount,
                    float(cfg.kyc_caps[str(rcp_kyc)].max_balance)
                )
                bal_after_r   = rcp_prof["balance"]
                added         = bal_after_r - bal_before_r

                day_txns.append(dict(
                    txn_id=_make_txn_id(counter),
                    timestamp=ts,
                    sender_id=source_id,
                    recipient_id=recipient_id,
                    txn_type=txn_type,
                    amount_tk=added,
                    fee_tk=0.0,
                    sender_balance_before=None,
                    sender_balance_after=None,
                    recipient_balance_before=round(bal_before_r, 2),
                    recipient_balance_after=round(bal_after_r, 2),
                    channel="APP",
                    agent_id=None,
                    device_id=rcp_prof["device_id"],
                    device_changed=0,
                    location_changed=0,
                    session_seconds=0,
                    pin_attempts=0,
                    counterparty_first_time=0,
                ))

            elif txn_type == "G2P_ALLOWANCE":
                # G2P: one trusted source disburses to many recipients
                # Pick a batch of up to 300 recipients and add them as separate rows
                n_batch = min(int(rng.integers(50, 150)), len(active_cids))
                g2p_src = str(rng.choice(g2p_sources))
                recipients_g2p = rng.choice(active_cids, size=n_batch, replace=False)
                for rid in recipients_g2p:
                    rcp_prof  = profiles[str(rid)]
                    rcp_kyc   = rcp_prof["kyc_level"]
                    g2p_amt   = float(rng.choice([500, 1000, 1500, 2000, 2500]))
                    h2        = _pick_hour(rng, prof["active_hour_weights"])
                    s2        = _random_second(rng)
                    ts2       = day.replace(hour=h2, minute=0, second=0) + timedelta(seconds=s2)

                    bal_b = rcp_prof["balance"]
                    rcp_prof["balance"] = min(
                        rcp_prof["balance"] + g2p_amt,
                        float(cfg.kyc_caps[str(rcp_kyc)].max_balance)
                    )
                    bal_a = rcp_prof["balance"]

                    day_txns.append(dict(
                        txn_id=_make_txn_id(counter),
                        timestamp=ts2,
                        sender_id=g2p_src,
                        recipient_id=str(rid),
                        txn_type="G2P_ALLOWANCE",
                        amount_tk=g2p_amt,
                        fee_tk=0.0,
                        sender_balance_before=None,
                        sender_balance_after=None,
                        recipient_balance_before=round(bal_b, 2),
                        recipient_balance_after=round(bal_a, 2),
                        channel="APP",
                        agent_id=None,
                        device_id=rcp_prof["device_id"],
                        device_changed=0,
                        location_changed=0,
                        session_seconds=0,
                        pin_attempts=0,
                        counterparty_first_time=0,
                    ))
                # G2P batch done; continue drawing other transactions for this day


        txn_rows.extend(day_txns)

    return txn_rows
