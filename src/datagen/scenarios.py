"""
src/datagen/scenarios.py
=========================
Module 5 – plant_scenarios()

Hand-plants all showcase cases SC-01..SC-10 and SB-01..SB-08 with
the exact numbers from the spec so they are reproducible from the CSV.

Each scenario sets scenario_id and expected_band in labels.csv.
SC scenarios have is_fraud=1; SB scenarios have is_benign_lookalike=1.
"""
from __future__ import annotations

import itertools
from datetime import datetime, timedelta
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
from types import SimpleNamespace


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_txn_id(counter: itertools.count) -> str:
    return f"T{next(counter):08d}"


def _fee(cfg: SimpleNamespace, txn_type: str, amount: float) -> float:
    return round(amount * cfg.fees.__dict__.get(txn_type, 0.0), 2)


def _label_row(txn_id: str, is_fraud: int, fraud_class: str, role: str,
               case_id: str, scenario_id: str, is_benign: int,
               expected_band: str) -> dict:
    return dict(
        txn_id=txn_id,
        is_fraud=is_fraud,
        fraud_class=fraud_class if is_fraud else None,
        fraud_role=role if (is_fraud or is_benign) else None,
        case_id=case_id,
        scenario_id=scenario_id,
        is_benign_lookalike=is_benign,
        expected_band=expected_band,
    )


# ── SC-01: Normal user → collector wallet (10× amount) ───────────────────────

def plant_sc01(cfg, counter, profiles, sim_start) -> Tuple[List[dict], List[dict]]:
    """
    Rahim (C004211) sends 20,000 Tk (10× median) to W-77310 (age 68 h).
    W-77310 has 29 unique senders, 24 first-time; cashes out 3 times.
    Event: Fri 21:14 (sim_start + 4 days to land on a Friday).
    """
    txns, labels = [], []
    cid = "C004211"
    prof = profiles.get(cid)
    if prof is None:
        return txns, labels

    # Force profile facts
    prof["median_send_tk"] = 2000.0
    prof["balance"] = max(prof["balance"], 23400.0)

    # Find the first Friday in the window
    event_day = sim_start
    for d in range(7):
        if (sim_start + timedelta(days=d)).weekday() == 4:   # Friday
            event_day = sim_start + timedelta(days=d)
            break
    event_ts = event_day.replace(hour=21, minute=14, second=7)

    # W-77310: 68 h old at event time
    w77310 = "W-77310"
    w77310_reg = event_ts - timedelta(hours=68)
    w77310_bal = 0.0

    # 29 victim senders → inbound 31 transfers, 24 first-time
    unique_senders = [f"C{i+1:06d}" for i in range(29) if f"C{i+1:06d}" != cid][:29]
    inbound_ts = w77310_reg + timedelta(hours=2)

    for i, sid in enumerate(unique_senders):
        amt = round(np.random.default_rng(42 + i).uniform(1000, 3000) / 10) * 10
        w77310_bal += amt
        sp = profiles.get(sid)
        bb = sp["balance"] if sp else 5000.0
        ba = bb - amt if sp else 5000.0 - amt
        if sp:
            sp["balance"] = max(0, ba)

        inbound_ts += timedelta(minutes=int(np.random.default_rng(42 + i).integers(5, 30)))
        tid = _make_txn_id(counter)
        txns.append(dict(
            txn_id=tid, timestamp=inbound_ts,
            sender_id=sid, recipient_id=w77310,
            txn_type="P2P_SEND", amount_tk=amt, fee_tk=0.0,
            sender_balance_before=round(bb, 2),
            sender_balance_after=round(ba, 2),
            recipient_balance_before=round(w77310_bal - amt, 2),
            recipient_balance_after=round(w77310_bal, 2),
            channel="USSD", agent_id=None,
            device_id=f"D-{sid}-1", device_changed=0, location_changed=0,
            session_seconds=30, pin_attempts=1,
            counterparty_first_time=int(i < 24),   # 24 first-time
        ))
        labels.append(_label_row(tid, 1, "S2", "collector_inbound",
                                 "CASE-SC01-SETUP", "SC-01", 0, "HIGH"))

    # Rahim's send (the actual SC-01 event)
    amount = 20000.0
    fee    = 0.0
    bal_b  = 23400.0
    bal_a  = bal_b - amount
    prof["balance"] = bal_a
    w77310_bal += amount

    tid = _make_txn_id(counter)
    txns.append(dict(
        txn_id=tid, timestamp=event_ts,
        sender_id=cid, recipient_id=w77310,
        txn_type="P2P_SEND", amount_tk=amount, fee_tk=fee,
        sender_balance_before=round(bal_b, 2),
        sender_balance_after=round(bal_a, 2),
        recipient_balance_before=round(w77310_bal - amount, 2),
        recipient_balance_after=round(w77310_bal, 2),
        channel="APP", agent_id=None,
        device_id=prof["device_id"], device_changed=0, location_changed=0,
        session_seconds=38, pin_attempts=1, counterparty_first_time=1,
    ))
    labels.append(_label_row(tid, 1, "S2", "victim_send",
                             "CASE-SC01", "SC-01", 0, "HIGH"))

    # 3 cash-outs from W-77310 (29k + 29k + 2.4k at two agents)
    co_specs = [
        (29000, "A0457", event_ts + timedelta(minutes=3)),
        (29000, "A0458", event_ts + timedelta(minutes=9)),
        (2400,  "A0457", event_ts + timedelta(minutes=12)),
    ]
    for co_amt, co_agent, co_ts in co_specs:
        fee_co = _fee(cfg, "CASH_OUT_AGENT", co_amt)
        bal_b_w = w77310_bal
        w77310_bal -= (co_amt + fee_co)
        w77310_bal = max(0.0, w77310_bal)
        tid = _make_txn_id(counter)
        txns.append(dict(
            txn_id=tid, timestamp=co_ts,
            sender_id=w77310, recipient_id=None,
            txn_type="CASH_OUT_AGENT", amount_tk=co_amt, fee_tk=fee_co,
            sender_balance_before=round(bal_b_w, 2),
            sender_balance_after=round(w77310_bal, 2),
            recipient_balance_before=None, recipient_balance_after=None,
            channel="AGENT_ASSISTED", agent_id=co_agent,
            device_id=f"D-{w77310}-1", device_changed=0, location_changed=0,
            session_seconds=20, pin_attempts=1, counterparty_first_time=0,
        ))
        labels.append(_label_row(tid, 1, "S2", "cashout",
                                 "CASE-SC01", "SC-01", 0, "HIGH"))

    return txns, labels


# ── SC-02: OTP/PIN takeover at night ──────────────────────────────────────────

def plant_sc02(cfg, counter, profiles, sim_start) -> Tuple[List[dict], List[dict]]:
    txns, labels = [], []
    cid = "C002907"
    prof = profiles.get(cid)
    if prof is None:
        return txns, labels

    prof["balance"] = max(prof["balance"], 14200.0)
    prof["median_send_tk"] = 800.0

    event_day = sim_start + timedelta(days=10)
    event_ts  = event_day.replace(hour=2, minute=47, second=0)
    w90022_bal = 0.0

    # Row 1: OTP request (modelled as a short 0-amount probe)
    # Row 2: send 12,500
    amount1 = 12500.0
    fee1    = 0.0
    bal_b   = 14200.0
    prof["balance"] = bal_b - amount1
    w90022_bal += amount1

    tid = _make_txn_id(counter)
    txns.append(dict(
        txn_id=tid, timestamp=event_ts,
        sender_id=cid, recipient_id="W-90022",
        txn_type="P2P_SEND", amount_tk=amount1, fee_tk=fee1,
        sender_balance_before=round(bal_b, 2),
        sender_balance_after=round(prof["balance"], 2),
        recipient_balance_before=0.0,
        recipient_balance_after=round(w90022_bal, 2),
        channel="APP", agent_id=None,
        device_id=f"D-{cid}-FRAUD",
        device_changed=1, location_changed=1,
        session_seconds=240, pin_attempts=1, counterparty_first_time=1,
    ))
    labels.append(_label_row(tid, 1, "S1", "takeover_send",
                             "CASE-SC02", "SC-02", 0, "WARN"))

    # Row 3: second send 1,500 within 4 min
    ts2 = event_ts + timedelta(minutes=4)
    amount2 = 1500.0
    fee2    = 0.0
    bal_b2  = prof["balance"]
    prof["balance"] -= amount2
    w90022_bal += amount2

    tid = _make_txn_id(counter)
    txns.append(dict(
        txn_id=tid, timestamp=ts2,
        sender_id=cid, recipient_id="W-90022",
        txn_type="P2P_SEND", amount_tk=amount2, fee_tk=fee2,
        sender_balance_before=round(bal_b2, 2),
        sender_balance_after=round(prof["balance"], 2),
        recipient_balance_before=round(w90022_bal - amount2, 2),
        recipient_balance_after=round(w90022_bal, 2),
        channel="APP", agent_id=None,
        device_id=f"D-{cid}-FRAUD",
        device_changed=1, location_changed=1,
        session_seconds=30, pin_attempts=1, counterparty_first_time=0,
    ))
    labels.append(_label_row(tid, 1, "S1", "takeover_send",
                             "CASE-SC02", "SC-02", 0, "WARN"))

    return txns, labels


# ── SC-03: Prize / lottery fee scam ───────────────────────────────────────────

def plant_sc03(cfg, counter, profiles, sim_start) -> Tuple[List[dict], List[dict]]:
    txns, labels = [], []
    cid = "C006118"
    prof = profiles.get(cid)
    if prof is None:
        return txns, labels
    prof["median_send_tk"] = 600.0
    prof["balance"] = max(prof["balance"], 2000.0)

    event_ts = (sim_start + timedelta(days=15)).replace(hour=14, minute=22)
    w41277_bal = 0.0

    # 26 victims, Karim is one of them
    for i in range(26):
        if i == 13:
            sender = cid
        else:
            sender = f"C{(i * 300 + 101):06d}"
        amt = round(float(np.random.default_rng(100 + i).uniform(300, 2000)) / 10) * 10
        ts  = (sim_start + timedelta(days=14)).replace(hour=10) + timedelta(hours=i * 1.5)
        sp  = profiles.get(sender)
        bb  = sp["balance"] if sp else 3000.0
        ba  = max(0, bb - amt)
        if sp:
            sp["balance"] = ba
        w41277_bal += amt

        tid = _make_txn_id(counter)
        txns.append(dict(
            txn_id=tid, timestamp=ts,
            sender_id=sender, recipient_id="W-41277",
            txn_type="P2P_SEND", amount_tk=amt, fee_tk=0.0,
            sender_balance_before=round(bb, 2),
            sender_balance_after=round(ba, 2),
            recipient_balance_before=round(w41277_bal - amt, 2),
            recipient_balance_after=round(w41277_bal, 2),
            channel="USSD", agent_id=None,
            device_id=f"D-{sender}-1", device_changed=0, location_changed=0,
            session_seconds=40, pin_attempts=1, counterparty_first_time=1,
        ))
        labels.append(_label_row(tid, 1, "S2", "victim_send",
                                 "CASE-SC03", "SC-03", 0, "WARN"))

    return txns, labels


# ── SC-04: Fake online seller ─────────────────────────────────────────────────

def plant_sc04(cfg, counter, profiles, sim_start) -> Tuple[List[dict], List[dict]]:
    txns, labels = [], []
    cid = "C008830"
    prof = profiles.get(cid)
    if prof is None:
        return txns, labels
    prof["balance"] = max(prof["balance"], 5000.0)
    prof["median_send_tk"] = 900.0

    # W-55102 age 5 days, 18 buyers
    event_ts = (sim_start + timedelta(days=7)).replace(hour=16, minute=30)
    w55102_bal = 0.0

    for i in range(18):
        if i == 9:
            buyer = cid
        else:
            buyer = f"C{(i * 400 + 201):06d}"
        amt = round(float(np.random.default_rng(200 + i).uniform(500, 6000)) / 10) * 10
        if buyer == cid:
            amt = 3500.0
        ts  = (sim_start + timedelta(days=5)).replace(hour=10) + timedelta(hours=i * 4)
        bp  = profiles.get(buyer)
        bb  = bp["balance"] if bp else 6000.0
        ba  = max(0, bb - amt)
        if bp:
            bp["balance"] = ba
        w55102_bal += amt

        tid = _make_txn_id(counter)
        txns.append(dict(
            txn_id=tid, timestamp=ts,
            sender_id=buyer, recipient_id="W-55102",
            txn_type="P2P_SEND", amount_tk=amt, fee_tk=0.0,
            sender_balance_before=round(bb, 2),
            sender_balance_after=round(ba, 2),
            recipient_balance_before=round(w55102_bal - amt, 2),
            recipient_balance_after=round(w55102_bal, 2),
            channel="APP", agent_id=None,
            device_id=f"D-{buyer}-1", device_changed=0, location_changed=0,
            session_seconds=45, pin_attempts=1, counterparty_first_time=1,
        ))
        labels.append(_label_row(tid, 1, "S4", "victim_send",
                                 "CASE-SC04", "SC-04", 0, "WARN"))

    # Cash-outs (NO supplier outflows)
    for co_i, (co_amt, co_agent, co_h) in enumerate(
        [(29000, "A0201", 18), (22000, "A0201", 18)]
    ):
        ts_co = (sim_start + timedelta(days=5)).replace(hour=co_h) + timedelta(minutes=co_i * 15)
        fee_co = _fee(cfg, "CASH_OUT_AGENT", co_amt)
        bal_b_w = w55102_bal
        w55102_bal -= (co_amt + fee_co)
        w55102_bal = max(0.0, w55102_bal)
        tid = _make_txn_id(counter)
        txns.append(dict(
            txn_id=tid, timestamp=ts_co,
            sender_id="W-55102", recipient_id=None,
            txn_type="CASH_OUT_AGENT", amount_tk=co_amt, fee_tk=fee_co,
            sender_balance_before=round(bal_b_w, 2),
            sender_balance_after=round(w55102_bal, 2),
            recipient_balance_before=None, recipient_balance_after=None,
            channel="AGENT_ASSISTED", agent_id=co_agent,
            device_id="D-W-55102-1", device_changed=0, location_changed=0,
            session_seconds=20, pin_attempts=1, counterparty_first_time=0,
        ))
        labels.append(_label_row(tid, 1, "S4", "cashout",
                                 "CASE-SC04", "SC-04", 0, "WARN"))

    return txns, labels


# ── SC-05: Mule chain in 12 minutes ───────────────────────────────────────────

def plant_sc05(cfg, counter, profiles, sim_start) -> Tuple[List[dict], List[dict]]:
    txns, labels = [], []
    victim = "C001275"
    prof = profiles.get(victim)
    if prof is None:
        return txns, labels
    prof["balance"] = max(prof["balance"], 21000.0)

    base_ts = (sim_start + timedelta(days=20)).replace(hour=14, minute=2, second=0)
    chain = [
        ("C001275", "W-A", 19500, 0),
        ("W-A",     "W-B", 19000, 4),
        ("W-B",     "W-C", 18500, 11),
    ]
    balances = {"W-A": 0.0, "W-B": 0.0, "W-C": 0.0}

    for (sender, recip, amount, delay_min) in chain:
        ts  = base_ts + timedelta(minutes=delay_min)
        fee = 0.0

        if sender == victim:
            bb  = prof["balance"]
            prof["balance"] -= (amount + fee)
            ba  = prof["balance"]
        else:
            bb = balances[sender]
            balances[sender] -= (amount + fee)
            ba  = balances[sender]

        if recip in balances:
            balances[recip] += amount
            rbb = balances[recip] - amount
            rba = balances[recip]
        else:
            rbb, rba = None, None

        tid = _make_txn_id(counter)
        txns.append(dict(
            txn_id=tid, timestamp=ts,
            sender_id=sender, recipient_id=recip,
            txn_type="P2P_SEND", amount_tk=amount, fee_tk=fee,
            sender_balance_before=round(bb, 2),
            sender_balance_after=round(ba, 2),
            recipient_balance_before=round(rbb, 2) if rbb is not None else None,
            recipient_balance_after=round(rba, 2) if rba is not None else None,
            channel="APP", agent_id=None,
            device_id=f"D-{sender}-1", device_changed=0, location_changed=0,
            session_seconds=15, pin_attempts=1, counterparty_first_time=1,
        ))
        role = "victim_send" if sender == victim else "mule_hop"
        labels.append(_label_row(tid, 1, "S3", role, "CASE-SC05", "SC-05", 0, "HIGH"))

    # Final cash-out at A0391 (split ≤30k per txn, spec says "29,000 cap split in 2")
    co_specs = [(14600, base_ts + timedelta(minutes=21)), (4200, base_ts + timedelta(minutes=22))]
    co_bal = balances["W-C"]
    for co_amt, co_ts in co_specs:
        fee_co = _fee(cfg, "CASH_OUT_AGENT", co_amt)
        bal_b_w = co_bal
        co_bal -= (co_amt + fee_co)
        tid = _make_txn_id(counter)
        txns.append(dict(
            txn_id=tid, timestamp=co_ts,
            sender_id="W-C", recipient_id=None,
            txn_type="CASH_OUT_AGENT", amount_tk=co_amt, fee_tk=fee_co,
            sender_balance_before=round(bal_b_w, 2),
            sender_balance_after=round(co_bal, 2),
            recipient_balance_before=None, recipient_balance_after=None,
            channel="AGENT_ASSISTED", agent_id="A0391",
            device_id="D-W-C-1", device_changed=0, location_changed=0,
            session_seconds=20, pin_attempts=1, counterparty_first_time=0,
        ))
        labels.append(_label_row(tid, 1, "S3", "cashout", "CASE-SC05", "SC-05", 0, "HIGH"))

    return txns, labels


# ── SC-06: Cash-out alert at agent ────────────────────────────────────────────

def plant_sc06(cfg, counter, profiles, sim_start) -> Tuple[List[dict], List[dict]]:
    """Re-uses W-77310 from SC-01; adds a fresh cash-out event."""
    txns, labels = [], []
    w77310 = "W-77310"
    # The inbound senders were planted in SC-01; we add the held cash-out
    base_ts = (sim_start + timedelta(days=4)).replace(hour=21, minute=20)

    # 4 first-time inbound transfers just before the cash-out
    inbound_total = 0.0
    for i in range(4):
        amt = round(float(np.random.default_rng(300 + i).uniform(6000, 9000)) / 10) * 10
        inbound_total += amt
        tid = _make_txn_id(counter)
        ts  = base_ts - timedelta(minutes=12 - i * 2)
        txns.append(dict(
            txn_id=tid, timestamp=ts,
            sender_id=f"C{(i * 500 + 9001):06d}", recipient_id=w77310,
            txn_type="P2P_SEND", amount_tk=amt, fee_tk=0.0,
            sender_balance_before=amt + 2000,
            sender_balance_after=2000.0,
            recipient_balance_before=round(inbound_total - amt, 2),
            recipient_balance_after=round(inbound_total, 2),
            channel="USSD", agent_id=None,
            device_id=f"D-C{i+9001:06d}-1", device_changed=0, location_changed=0,
            session_seconds=30, pin_attempts=1, counterparty_first_time=1,
        ))
        labels.append(_label_row(tid, 1, "S2", "collector_inbound",
                                 "CASE-SC06", "SC-06", 0, "HIGH"))

    # The held cash-out
    co_amt = 29000.0
    fee_co = _fee(cfg, "CASH_OUT_AGENT", co_amt)
    tid = _make_txn_id(counter)
    txns.append(dict(
        txn_id=tid, timestamp=base_ts,
        sender_id=w77310, recipient_id=None,
        txn_type="CASH_OUT_AGENT", amount_tk=co_amt, fee_tk=fee_co,
        sender_balance_before=round(inbound_total, 2),
        sender_balance_after=round(inbound_total - co_amt - fee_co, 2),
        recipient_balance_before=None, recipient_balance_after=None,
        channel="AGENT_ASSISTED", agent_id="A0457",
        device_id=f"D-{w77310}-1", device_changed=0, location_changed=0,
        session_seconds=15, pin_attempts=1, counterparty_first_time=0,
    ))
    labels.append(_label_row(tid, 1, "S2", "cashout", "CASE-SC06", "SC-06", 0, "HIGH"))

    return txns, labels


# ── SC-07: Rogue agent SC (A0391) ────────────────────────────────────────────

def plant_sc07(cfg, counter, profiles, sim_start) -> Tuple[List[dict], List[dict]]:
    """Plant 7-day run of A0391 operating at 9× peer mean."""
    txns, labels = [], []
    aid = "A0391"
    peer_mean = 46
    n_per_day = int(peer_mean * 9)

    for day_off in range(7):
        day = (sim_start + timedelta(days=25 + day_off)).replace(hour=0)
        for i in range(n_per_day):
            hour = 8 + (i * 12 // n_per_day)
            ts = day.replace(hour=hour) + timedelta(minutes=int(i % 60))
            # 58% from young wallets
            if i < int(n_per_day * 0.58):
                sender = f"W-{80000 + i:05d}"   # fraud wallets
                is_fr  = 1
                role   = "rogue_agent_cashout"
                band   = "HIGH"
            else:
                sender = f"C{(i + 1):06d}"
                is_fr  = 0
                role   = ""
                band   = "ALLOW"

            # Round near-cap amounts (44 % are 29k-30k, as in spec)
            if i % 100 < 44:
                amt = float(np.random.default_rng(400 + i).choice([29000, 29200, 29500, 29800]))
            else:
                amt = round(float(np.random.default_rng(400 + i).uniform(500, 28000)) / 10) * 10
            fee_co = _fee(cfg, "CASH_OUT_AGENT", amt)

            tid = _make_txn_id(counter)
            txns.append(dict(
                txn_id=tid, timestamp=ts,
                sender_id=sender, recipient_id=None,
                txn_type="CASH_OUT_AGENT", amount_tk=amt, fee_tk=fee_co,
                sender_balance_before=amt + fee_co,
                sender_balance_after=0.0,
                recipient_balance_before=None, recipient_balance_after=None,
                channel="AGENT_ASSISTED", agent_id=aid,
                device_id=f"D-{sender}-1", device_changed=0, location_changed=0,
                session_seconds=15, pin_attempts=1, counterparty_first_time=0,
            ))
            labels.append(_label_row(tid, is_fr, "S5" if is_fr else "",
                                     role, "CASE-SC07", "SC-07", 0, band))

    return txns, labels


# ── SC-08: SIM-swap (borderline, NUDGE expected) ──────────────────────────────

def plant_sc08(cfg, counter, profiles, sim_start) -> Tuple[List[dict], List[dict]]:
    txns, labels = [], []
    cid = "C003340"
    prof = profiles.get(cid)
    if prof is None:
        return txns, labels
    prof["balance"] = max(prof["balance"], 15400.0)

    event_ts = (sim_start + timedelta(days=30)).replace(hour=5, minute=10, second=0)
    amount = 12000.0
    fee    = 0.0
    bal_b  = 15400.0
    prof["balance"] -= amount

    tid = _make_txn_id(counter)
    txns.append(dict(
        txn_id=tid, timestamp=event_ts,
        sender_id=cid, recipient_id="W-60877",
        txn_type="P2P_SEND", amount_tk=amount, fee_tk=fee,
        sender_balance_before=round(bal_b, 2),
        sender_balance_after=round(prof["balance"], 2),
        recipient_balance_before=0.0,
        recipient_balance_after=round(amount, 2),
        channel="APP", agent_id=None,
        device_id=f"D-{cid}-SWAP",
        device_changed=1, location_changed=0,
        session_seconds=45, pin_attempts=1, counterparty_first_time=1,
    ))
    # Score 59 → NUDGE (intentionally borderline)
    labels.append(_label_row(tid, 1, "S6", "takeover_send",
                             "CASE-SC08", "SC-08", 0, "NUDGE"))

    return txns, labels


# ── SC-09: Guided victim (coached by caller) ──────────────────────────────────

def plant_sc09(cfg, counter, profiles, sim_start) -> Tuple[List[dict], List[dict]]:
    txns, labels = [], []
    cid = "C005901"
    prof = profiles.get(cid)
    if prof is None:
        return txns, labels
    prof["balance"] = max(prof["balance"], 8000.0)
    prof["median_send_tk"] = 400.0

    event_ts = (sim_start + timedelta(days=12)).replace(hour=14, minute=33, second=0)
    amount   = 6000.0    # 15× median
    fee      = 0.0
    bal_b    = prof["balance"]
    prof["balance"] -= amount

    tid = _make_txn_id(counter)
    txns.append(dict(
        txn_id=tid, timestamp=event_ts,
        sender_id=cid, recipient_id="W-83019",
        txn_type="P2P_SEND", amount_tk=amount, fee_tk=fee,
        sender_balance_before=round(bal_b, 2),
        sender_balance_after=round(prof["balance"], 2),
        recipient_balance_before=0.0,
        recipient_balance_after=amount,
        channel="USSD", agent_id=None,
        device_id=prof["device_id"], device_changed=0, location_changed=0,
        session_seconds=412, pin_attempts=3, counterparty_first_time=1,
    ))
    labels.append(_label_row(tid, 1, "S7", "victim_send",
                             "CASE-SC09", "SC-09", 0, "WARN"))

    # Cash-out at agent
    co_ts  = event_ts + timedelta(minutes=15)
    co_amt = 5800.0
    fee_co = _fee(cfg, "CASH_OUT_AGENT", co_amt)
    tid    = _make_txn_id(counter)
    txns.append(dict(
        txn_id=tid, timestamp=co_ts,
        sender_id="W-83019", recipient_id=None,
        txn_type="CASH_OUT_AGENT", amount_tk=co_amt, fee_tk=fee_co,
        sender_balance_before=amount,
        sender_balance_after=amount - co_amt - fee_co,
        recipient_balance_before=None, recipient_balance_after=None,
        channel="AGENT_ASSISTED", agent_id="A0050",
        device_id="D-W-83019-1", device_changed=0, location_changed=0,
        session_seconds=20, pin_attempts=1, counterparty_first_time=0,
    ))
    labels.append(_label_row(tid, 1, "S7", "cashout", "CASE-SC09", "SC-09", 0, "WARN"))

    return txns, labels


# ── SC-10: Structured amounts / sibling wallets ────────────────────────────────

def plant_sc10(cfg, counter, profiles, sim_start) -> Tuple[List[dict], List[dict]]:
    txns, labels = [], []
    siblings = ["W-31905", "W-31906", "W-31907"]
    sib_bals = {s: 0.0 for s in siblings}

    base_ts = (sim_start + timedelta(days=18)).replace(hour=10, minute=0)
    # 11 inbound near-cap (KYC-1 daily = 10,000 Tk → amounts 4,900-9,900)
    KYC1_CAP = 10000
    for i in range(11):
        amt = round(float(np.random.default_rng(500 + i).uniform(4900, 9900)) / 10) * 10
        sender = f"C{(i * 700 + 3001):06d}"
        ts  = base_ts + timedelta(hours=i * 0.5)
        sp  = profiles.get(sender)
        bb  = sp["balance"] if sp else 15000.0
        ba  = max(0, bb - amt)
        if sp:
            sp["balance"] = ba
        sib_bals["W-31905"] += amt

        tid = _make_txn_id(counter)
        txns.append(dict(
            txn_id=tid, timestamp=ts,
            sender_id=sender, recipient_id="W-31905",
            txn_type="P2P_SEND", amount_tk=amt, fee_tk=0.0,
            sender_balance_before=round(bb, 2),
            sender_balance_after=round(ba, 2),
            recipient_balance_before=round(sib_bals["W-31905"] - amt, 2),
            recipient_balance_after=round(sib_bals["W-31905"], 2),
            channel="APP", agent_id=None,
            device_id=f"D-{sender}-1", device_changed=0, location_changed=0,
            session_seconds=25, pin_attempts=1, counterparty_first_time=1,
        ))
        labels.append(_label_row(tid, 1, "S3", "collector_inbound",
                                 "CASE-SC10", "SC-10", 0, "WARN"))

    # Fan-out: 3 transfers of 9,500 to sibling wallets within 20 min
    fan_ts = base_ts + timedelta(hours=5.5)
    for j, sib in enumerate(["W-31906", "W-31907", "W-31905"]):
        out_ts = fan_ts + timedelta(minutes=j * 7)
        famt   = 9500.0
        fee    = 0.0
        bb     = sib_bals["W-31905"]
        sib_bals["W-31905"] -= (famt + fee)
        sib_bals[sib if sib != "W-31905" else "W-31905"] += famt
        tid = _make_txn_id(counter)
        txns.append(dict(
            txn_id=tid, timestamp=out_ts,
            sender_id="W-31905", recipient_id=sib,
            txn_type="P2P_SEND", amount_tk=famt, fee_tk=fee,
            sender_balance_before=round(bb, 2),
            sender_balance_after=round(sib_bals["W-31905"], 2),
            recipient_balance_before=round(sib_bals[sib] - famt if sib != "W-31905" else 0.0, 2),
            recipient_balance_after=round(sib_bals[sib], 2),
            channel="APP", agent_id=None,
            device_id="D-9917", device_changed=0, location_changed=0,  # shared device
            session_seconds=15, pin_attempts=1, counterparty_first_time=1,
        ))
        labels.append(_label_row(tid, 1, "S3", "mule_hop",
                                 "CASE-SC10", "SC-10", 0, "WARN"))

    return txns, labels


# ── SB-01..SB-08: Benign look-alikes ─────────────────────────────────────────

def plant_sb_cases(
    cfg: SimpleNamespace, counter: itertools.count,
    profiles: Dict[str, dict], sim_start: datetime,
    rng: np.random.Generator,
) -> Tuple[List[dict], List[dict]]:
    """Plant all 8 benign look-alike scenarios."""
    txns: List[dict] = []
    labels: List[dict] = []

    # SB-01: Eid gift to mother – 15,000 Tk to a 40× used contact
    sb01_cid = "C001001"
    p = profiles.get(sb01_cid)
    if p:
        p["balance"] = max(p["balance"], 20000.0)
        ts = (sim_start + timedelta(days=22)).replace(hour=15, minute=0)
        amt = 15000.0
        bb  = p["balance"]
        p["balance"] -= amt
        tid = _make_txn_id(counter)
        txns.append(dict(
            txn_id=tid, timestamp=ts,
            sender_id=sb01_cid, recipient_id="C001100",   # known contact
            txn_type="P2P_SEND", amount_tk=amt, fee_tk=0.0,
            sender_balance_before=round(bb, 2), sender_balance_after=round(p["balance"], 2),
            recipient_balance_before=5000.0, recipient_balance_after=20000.0,
            channel="APP", agent_id=None,
            device_id=p["device_id"], device_changed=0, location_changed=0,
            session_seconds=25, pin_attempts=1, counterparty_first_time=0,
        ))
        labels.append(_label_row(tid, 0, "", "", "CASE-SB01", "SB-01", 1, "ALLOW"))

    # SB-02: Salary day – garment worker cashes in 18,000 then cashes out 12,000
    sb02_cid = "C002002"
    p = profiles.get(sb02_cid)
    if p:
        p["balance"] = max(p["balance"], 1000.0)
        ts_in = (sim_start + timedelta(days=2)).replace(hour=9, minute=0)   # salary day 3
        amt_in = 18000.0
        bb_in  = p["balance"]
        p["balance"] = min(p["balance"] + amt_in, 25000.0)

        tid = _make_txn_id(counter)
        txns.append(dict(
            txn_id=tid, timestamp=ts_in,
            sender_id="A0005", recipient_id=sb02_cid,
            txn_type="CASH_IN", amount_tk=amt_in, fee_tk=0.0,
            sender_balance_before=None, sender_balance_after=None,
            recipient_balance_before=round(bb_in, 2), recipient_balance_after=round(p["balance"], 2),
            channel="AGENT_ASSISTED", agent_id="A0005",
            device_id=p["device_id"], device_changed=0, location_changed=0,
            session_seconds=20, pin_attempts=1, counterparty_first_time=0,
        ))
        labels.append(_label_row(tid, 0, "", "", "CASE-SB02", "SB-02", 1, "ALLOW"))

        # Two cash-outs of 6,000 each
        for co_i, co_amt in enumerate([6000.0, 6000.0]):
            ts_co = ts_in + timedelta(hours=2 + co_i)
            fee_co = _fee(cfg, "CASH_OUT_AGENT", co_amt)
            bb_co  = p["balance"]
            p["balance"] -= (co_amt + fee_co)
            tid = _make_txn_id(counter)
            txns.append(dict(
                txn_id=tid, timestamp=ts_co,
                sender_id=sb02_cid, recipient_id=None,
                txn_type="CASH_OUT_AGENT", amount_tk=co_amt, fee_tk=fee_co,
                sender_balance_before=round(bb_co, 2), sender_balance_after=round(p["balance"], 2),
                recipient_balance_before=None, recipient_balance_after=None,
                channel="AGENT_ASSISTED", agent_id="A0005",
                device_id=p["device_id"], device_changed=0, location_changed=0,
                session_seconds=18, pin_attempts=1, counterparty_first_time=0,
            ))
            labels.append(_label_row(tid, 0, "", "", "CASE-SB02", "SB-02", 1, "ALLOW"))

    # SB-03: Tuition fee to university merchant (new to sender, merchant aged 3 years)
    sb03_cid = "C003003"
    p = profiles.get(sb03_cid)
    if p:
        p["balance"] = max(p["balance"], 25000.0)
        ts = (sim_start + timedelta(days=8)).replace(hour=11, minute=0)
        amt = 22000.0
        bb  = p["balance"]
        p["balance"] -= amt
        tid = _make_txn_id(counter)
        txns.append(dict(
            txn_id=tid, timestamp=ts,
            sender_id=sb03_cid, recipient_id="M0001",   # verified university merchant
            txn_type="MERCHANT_PAY", amount_tk=amt, fee_tk=0.0,
            sender_balance_before=round(bb, 2), sender_balance_after=round(p["balance"], 2),
            recipient_balance_before=50000.0, recipient_balance_after=72000.0,
            channel="APP", agent_id=None,
            device_id=p["device_id"], device_changed=0, location_changed=0,
            session_seconds=30, pin_attempts=1, counterparty_first_time=1,
        ))
        labels.append(_label_row(tid, 0, "", "", "CASE-SB03", "SB-03", 1, "ALLOW"))

    # SB-04: Market-day shop (14 months old merchant receives 45 payments)
    # Represented by merchant M0010; already in normal txns; just plant one summary entry
    sb04_ts = (sim_start + timedelta(days=5)).replace(hour=17, minute=0)
    # We rely on normal_life to generate these; just plant one cash-out by merchant
    amt_co = 25000.0
    fee_co = _fee(cfg, "CASH_OUT_AGENT", amt_co)
    tid = _make_txn_id(counter)
    txns.append(dict(
        txn_id=tid, timestamp=sb04_ts,
        sender_id="M0010", recipient_id=None,
        txn_type="CASH_OUT_AGENT", amount_tk=amt_co, fee_tk=fee_co,
        sender_balance_before=35000.0, sender_balance_after=35000.0 - amt_co - fee_co,
        recipient_balance_before=None, recipient_balance_after=None,
        channel="AGENT_ASSISTED", agent_id="A0020",
        device_id="D-M0010-1", device_changed=0, location_changed=0,
        session_seconds=25, pin_attempts=1, counterparty_first_time=0,
    ))
    labels.append(_label_row(tid, 0, "", "", "CASE-SB04", "SB-04", 1, "ALLOW"))

    # SB-05: Husband sends to wife's NEW wallet (registered yesterday) – lands in NUDGE
    sb05_cid = "C005005"
    p = profiles.get(sb05_cid)
    if p:
        p["balance"] = max(p["balance"], 15000.0)
        ts = (sim_start + timedelta(days=3)).replace(hour=20, minute=0)
        amt = 12000.0
        bb  = p["balance"]
        p["balance"] -= amt
        tid = _make_txn_id(counter)
        txns.append(dict(
            txn_id=tid, timestamp=ts,
            sender_id=sb05_cid, recipient_id="W-WIFE-01",
            txn_type="P2P_SEND", amount_tk=amt, fee_tk=0.0,
            sender_balance_before=round(bb, 2), sender_balance_after=round(p["balance"], 2),
            recipient_balance_before=0.0, recipient_balance_after=amt,
            channel="APP", agent_id=None,
            device_id=p["device_id"], device_changed=0, location_changed=0,
            session_seconds=20, pin_attempts=1, counterparty_first_time=1,
        ))
        # SB-05 deliberately NUDGE (score 26, band ALLOW/NUDGE boundary)
        labels.append(_label_row(tid, 0, "", "", "CASE-SB05", "SB-05", 1, "ALLOW"))

    # SB-06: Rare large send for medical emergency (daytime, usual device)
    sb06_cid = "C006006"
    p = profiles.get(sb06_cid)
    if p:
        p["balance"] = max(p["balance"], 28000.0)
        ts = (sim_start + timedelta(days=14)).replace(hour=11, minute=30)
        amt = 25000.0
        bb  = p["balance"]
        p["balance"] -= amt
        tid = _make_txn_id(counter)
        txns.append(dict(
            txn_id=tid, timestamp=ts,
            sender_id=sb06_cid, recipient_id="C006100",  # known contact
            txn_type="P2P_SEND", amount_tk=amt, fee_tk=0.0,
            sender_balance_before=round(bb, 2), sender_balance_after=round(p["balance"], 2),
            recipient_balance_before=3000.0, recipient_balance_after=28000.0,
            channel="APP", agent_id=None,
            device_id=p["device_id"], device_changed=0, location_changed=0,
            session_seconds=30, pin_attempts=1, counterparty_first_time=0,
        ))
        labels.append(_label_row(tid, 0, "", "", "CASE-SB06", "SB-06", 1, "ALLOW"))

    # SB-07: Remittance then immediate 90% cash-out (rural wallet)
    sb07_cid = "C007007"
    p = profiles.get(sb07_cid)
    if p:
        p["balance"] = max(p["balance"], 500.0)
        ts_in = (sim_start + timedelta(days=18)).replace(hour=14, minute=0)
        remit_amt = 25000.0
        bb_in  = p["balance"]
        p["balance"] = min(p["balance"] + remit_amt, 25000.0)

        tid = _make_txn_id(counter)
        txns.append(dict(
            txn_id=tid, timestamp=ts_in,
            sender_id="REMIT-01", recipient_id=sb07_cid,
            txn_type="REMITTANCE_IN", amount_tk=remit_amt, fee_tk=0.0,
            sender_balance_before=None, sender_balance_after=None,
            recipient_balance_before=round(bb_in, 2), recipient_balance_after=round(p["balance"], 2),
            channel="APP", agent_id=None,
            device_id=p["device_id"], device_changed=0, location_changed=0,
            session_seconds=0, pin_attempts=0, counterparty_first_time=0,
        ))
        labels.append(_label_row(tid, 0, "", "", "CASE-SB07", "SB-07", 1, "ALLOW"))

        # Immediate 90% cash-out
        co_amt = round(remit_amt * 0.9 / 10) * 10
        fee_co = _fee(cfg, "CASH_OUT_AGENT", co_amt)
        ts_co  = ts_in + timedelta(minutes=15)
        bb_co  = p["balance"]
        p["balance"] -= (co_amt + fee_co)
        tid = _make_txn_id(counter)
        txns.append(dict(
            txn_id=tid, timestamp=ts_co,
            sender_id=sb07_cid, recipient_id=None,
            txn_type="CASH_OUT_AGENT", amount_tk=co_amt, fee_tk=fee_co,
            sender_balance_before=round(bb_co, 2), sender_balance_after=round(p["balance"], 2),
            recipient_balance_before=None, recipient_balance_after=None,
            channel="AGENT_ASSISTED", agent_id=p["home_agent_id"],
            device_id=p["device_id"], device_changed=0, location_changed=0,
            session_seconds=20, pin_attempts=1, counterparty_first_time=0,
        ))
        labels.append(_label_row(tid, 0, "", "", "CASE-SB07", "SB-07", 1, "ALLOW"))

    # SB-08: G2P disbursement to 300 wallets from trusted source
    # (Represents one batch disbursement event; detailed rows in normal_life G2P)
    g2p_ts = (sim_start + timedelta(days=10)).replace(hour=9, minute=0)
    g2p_sample_ids = [f"C{(i * 30 + 101):06d}" for i in range(5)]
    for g_cid in g2p_sample_ids:
        gp = profiles.get(g_cid)
        if not gp:
            continue
        g_amt = 2000.0
        bb_g  = gp["balance"]
        gp["balance"] = min(gp["balance"] + g_amt, 25000.0)
        tid = _make_txn_id(counter)
        txns.append(dict(
            txn_id=tid, timestamp=g2p_ts,
            sender_id="G2P-01", recipient_id=g_cid,
            txn_type="G2P_ALLOWANCE", amount_tk=g_amt, fee_tk=0.0,
            sender_balance_before=None, sender_balance_after=None,
            recipient_balance_before=round(bb_g, 2), recipient_balance_after=round(gp["balance"], 2),
            channel="APP", agent_id=None,
            device_id=gp["device_id"], device_changed=0, location_changed=0,
            session_seconds=0, pin_attempts=0, counterparty_first_time=0,
        ))
        labels.append(_label_row(tid, 0, "", "", "CASE-SB08", "SB-08", 1, "ALLOW"))

    return txns, labels


# ── Orchestrator ──────────────────────────────────────────────────────────────

def plant_scenarios(
    cfg: SimpleNamespace,
    counter: itertools.count,
    profiles: Dict[str, dict],
    sim_start: datetime,
    rng: np.random.Generator,
) -> Tuple[List[dict], List[dict]]:
    """Run all scenario planters and return combined (txns, labels)."""
    all_txns: List[dict]   = []
    all_labels: List[dict] = []

    planters = [
        plant_sc01, plant_sc02, plant_sc03, plant_sc04, plant_sc05,
        plant_sc06, plant_sc07, plant_sc08, plant_sc09, plant_sc10,
    ]
    for planter in planters:
        t, l = planter(cfg, counter, profiles, sim_start)
        all_txns.extend(t)
        all_labels.extend(l)

    t, l = plant_sb_cases(cfg, counter, profiles, sim_start, rng)
    all_txns.extend(t)
    all_labels.extend(l)

    return all_txns, all_labels
