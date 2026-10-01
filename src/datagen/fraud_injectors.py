"""
src/datagen/fraud_injectors.py
================================
Module 4 – inject_s1() … inject_s7()

Each function injects one fraud class following the Part 5 recipes.
Returns (txn_rows, label_rows) for that class.
All randomness uses the shared rng; timers use datetime arithmetic.

Label schema (labels.csv):
  txn_id, is_fraud, fraud_class, fraud_role, case_id, scenario_id,
  is_benign_lookalike, expected_band
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


def _label(txn_id: str, is_fraud: int, fraud_class: str, role: str,
           case_id: str, scenario_id: str = "", is_benign: int = 0,
           expected_band: str = "") -> dict:
    return dict(
        txn_id=txn_id,
        is_fraud=is_fraud,
        fraud_class=fraud_class if is_fraud else None,
        fraud_role=role if is_fraud else None,
        case_id=case_id if (is_fraud or is_benign) else None,
        scenario_id=scenario_id if scenario_id else None,
        is_benign_lookalike=is_benign,
        expected_band=expected_band,
    )


def _random_ts(rng: np.random.Generator,
               base: datetime, delta_h_min: float = 0,
               delta_h_max: float = 48) -> datetime:
    """Random timestamp within [base + delta_h_min, base + delta_h_max] hours."""
    delta_s = rng.uniform(delta_h_min * 3600, delta_h_max * 3600)
    return base + timedelta(seconds=float(delta_s))


def _get_kyc(cfg: SimpleNamespace, kyc: int, key: str) -> float:
    return float(getattr(cfg.kyc_caps[str(kyc)], key))


# ── Fresh wallet factory ──────────────────────────────────────────────────────

def _new_fraud_wallet(
    cfg: SimpleNamespace, rng: np.random.Generator,
    first_inbound_ts: datetime, age_h_range: Tuple[float, float]
) -> dict:
    """Return a minimal fraud-wallet profile (not in customers.csv)."""
    age_h = rng.uniform(*age_h_range)
    reg_ts = first_inbound_ts - timedelta(hours=float(age_h))
    wid = f"W-{rng.integers(10000, 99999):05d}"
    return dict(
        wallet_id   = wid,
        balance     = 0.0,
        kyc_level   = 1,
        reg_ts      = reg_ts,
        age_h       = age_h,
        device_id   = f"D-{wid}-1",
    )


# ── S1: OTP/PIN takeover ──────────────────────────────────────────────────────

def inject_s1(
    cfg: SimpleNamespace, rng: np.random.Generator,
    customers: pd.DataFrame, profiles: Dict[str, dict],
    counter: itertools.count,
    sim_start: datetime, sim_end: datetime,
) -> Tuple[List[dict], List[dict]]:
    """
    S1: Fake customer-care call, victim gives PIN/OTP, account drained.
    Recipe: victim low/med literacy, 60% event 22:00-04:00, new device,
    50% location changed, amount 70-98% balance, 1-3 sends in 15 min,
    recipient wallet 2-72 h old.
    """
    txns: List[dict] = []
    labels: List[dict] = []

    n_victims = cfg.fraud.s1_victim_count
    # Low / medium literacy customers only (victim pool)
    victims_pool = customers[
        customers["digital_literacy"].isin(["low", "medium"])
    ]["customer_id"].tolist()
    rng.shuffle(victims_pool)
    victims = victims_pool[:min(n_victims, len(victims_pool))]

    case_counter = 0
    for victim_id in victims:
        case_counter += 1
        case_id = f"CASE-S1-{case_counter:04d}"
        prof = profiles[victim_id]

        # Event timestamp
        day_offset = int(rng.integers(0, cfg.sim_days))
        base_day   = sim_start + timedelta(days=day_offset)

        # 60 % night (22-04)
        if rng.random() < cfg.fraud.s1_night_fraction:
            hour = int(rng.choice([22, 23, 0, 1, 2, 3]))
            if hour in (22, 23):
                event_ts = base_day.replace(hour=hour) + timedelta(minutes=int(rng.integers(0, 60)))
            else:
                event_ts = (base_day + timedelta(days=1)).replace(hour=hour) + \
                           timedelta(minutes=int(rng.integers(0, 60)))
        else:
            hour = int(rng.integers(6, 22))
            event_ts = base_day.replace(hour=hour) + timedelta(minutes=int(rng.integers(0, 60)))

        if event_ts > sim_end:
            event_ts = sim_end - timedelta(hours=1)

        # Ensure victim has enough balance (inject CASH_IN if needed)
        target_bal_min, target_bal_max = cfg.fraud.s1_balance_range
        target_bal = float(rng.uniform(target_bal_min, target_bal_max))
        if prof["balance"] < target_bal * 0.5:
            # Give victim a realistic starting balance
            prof["balance"] = float(rng.uniform(target_bal * 0.8, target_bal))

        drain = float(rng.uniform(*cfg.fraud.s1_drain_ratio_range))
        amount = round(prof["balance"] * drain / 10) * 10
        amount = max(amount, 100.0)
        amount = min(amount, _get_kyc(cfg, prof["kyc_level"], "per_txn_send_max"))

        # Fresh recipient wallet
        fw = _new_fraud_wallet(cfg, rng, event_ts,
                               tuple(cfg.fraud.s1_recipient_age_h_range))

        new_device = f"D-{victim_id}-FRAUD"
        loc_changed = int(rng.random() < 0.5)

        n_sends = int(rng.integers(*cfg.fraud.s1_sends_in_15min))

        for s_idx in range(n_sends):
            send_ts = event_ts + timedelta(minutes=s_idx * int(rng.uniform(2, 5)))
            txn_amount = amount if s_idx == 0 else max(100.0, prof["balance"] * 0.5)
            txn_amount = min(txn_amount, prof["balance"])
            txn_amount = round(txn_amount / 10) * 10
            if txn_amount < 10:
                break

            fee = _fee(cfg, "P2P_SEND", txn_amount)
            total_out = txn_amount + fee

            if prof["balance"] < total_out:
                break

            bal_b_s = prof["balance"]
            prof["balance"] -= total_out
            bal_a_s = prof["balance"]

            fw["balance"] += txn_amount

            # Weak/ambiguous case: ~20% of cases are daytime, normal device
            is_weak = case_counter % int(1 / cfg.fraud.weak_case_fraction) == 0
            session_secs = int(rng.uniform(150, 400)) if s_idx == 0 else int(rng.uniform(5, 60))

            tid = _make_txn_id(counter)
            txns.append(dict(
                txn_id=tid,
                timestamp=send_ts,
                sender_id=victim_id,
                recipient_id=fw["wallet_id"],
                txn_type="P2P_SEND",
                amount_tk=txn_amount,
                fee_tk=fee,
                sender_balance_before=round(bal_b_s, 2),
                sender_balance_after=round(bal_a_s, 2),
                recipient_balance_before=round(fw["balance"] - txn_amount, 2),
                recipient_balance_after=round(fw["balance"], 2),
                channel="APP" if not is_weak else "USSD",
                agent_id=None,
                device_id=new_device if not is_weak else prof["device_id"],
                device_changed=1 if not is_weak else 0,
                location_changed=loc_changed if not is_weak else 0,
                session_seconds=session_secs,
                pin_attempts=1,
                counterparty_first_time=1,
            ))
            labels.append(_label(tid, 1, "S1", "takeover_send", case_id,
                                 expected_band="HIGH" if not is_weak else "WARN"))

        # Recipient cash-out within 30 min
        if fw["balance"] > 500:
            cashout_ts = event_ts + timedelta(minutes=int(rng.integers(5, cfg.fraud.s1_cashout_delay_min)))
            cashout_amount = min(fw["balance"], float(cfg.agent_cashout_max_txn))
            cashout_amount = round(cashout_amount / 10) * 10
            fee_co = _fee(cfg, "CASH_OUT_AGENT", cashout_amount)

            tid = _make_txn_id(counter)
            txns.append(dict(
                txn_id=tid,
                timestamp=cashout_ts,
                sender_id=fw["wallet_id"],
                recipient_id=None,
                txn_type="CASH_OUT_AGENT",
                amount_tk=cashout_amount,
                fee_tk=fee_co,
                sender_balance_before=round(fw["balance"], 2),
                sender_balance_after=round(fw["balance"] - cashout_amount - fee_co, 2),
                recipient_balance_before=None,
                recipient_balance_after=None,
                channel="AGENT_ASSISTED",
                agent_id="A0001",   # placeholder; overwritten in plant_scenarios
                device_id=fw["device_id"],
                device_changed=1,
                location_changed=1,
                session_seconds=int(rng.uniform(15, 60)),
                pin_attempts=1,
                counterparty_first_time=0,
            ))
            fw["balance"] -= (cashout_amount + fee_co)
            labels.append(_label(tid, 1, "S1", "cashout", case_id,
                                 expected_band="HIGH"))

    return txns, labels


# ── S2: Prize / lottery / fake-job fee ────────────────────────────────────────

def inject_s2(
    cfg: SimpleNamespace, rng: np.random.Generator,
    customers: pd.DataFrame, profiles: Dict[str, dict],
    counter: itertools.count,
    sim_start: datetime, sim_end: datetime,
) -> Tuple[List[dict], List[dict]]:
    txns: List[dict] = []
    labels: List[dict] = []

    n_collectors = cfg.fraud.s2_collector_count
    all_cids     = customers["customer_id"].tolist()

    for col_idx in range(n_collectors):
        # Collector wallet (fraud-controlled, not in customers.csv)
        day_offset = int(rng.integers(5, cfg.sim_days - 5))
        first_ts   = sim_start + timedelta(days=day_offset,
                                           hours=int(rng.integers(8, 20)))
        col_age_d  = float(rng.uniform(*cfg.fraud.s2_collector_age_d_range))
        col_wallet = dict(
            wallet_id = f"W-{rng.integers(10000, 99999):05d}",
            balance   = 0.0,
            device_id = f"D-COL-{col_idx:03d}-1",
            reg_ts    = first_ts - timedelta(days=col_age_d),
        )
        case_id    = f"CASE-S2-{col_idx+1:03d}"
        n_victims  = int(rng.integers(*cfg.fraud.s2_victims_per_collector))
        victim_ids = rng.choice(all_cids, size=min(n_victims, len(all_cids)), replace=False)

        inflow_total = 0.0
        victim_ts = first_ts

        for v_idx, vid in enumerate(victim_ids):
            prof = profiles[str(vid)]
            amount = float(rng.uniform(*cfg.fraud.s2_victim_amount_range))
            amount = round(amount / 10) * 10
            amount = min(amount, prof["balance"], _get_kyc(cfg, prof["kyc_level"], "per_txn_send_max"))
            if amount < 50:
                continue

            victim_ts += timedelta(minutes=float(rng.uniform(10, 90)))
            if victim_ts > sim_end:
                break

            first_time = int(rng.random() < cfg.fraud.s2_first_time_fraction)
            fee = _fee(cfg, "P2P_SEND", amount)
            bal_b = prof["balance"]
            prof["balance"] -= (amount + fee)
            bal_a = prof["balance"]
            col_wallet["balance"] += amount
            inflow_total += amount

            tid = _make_txn_id(counter)
            txns.append(dict(
                txn_id=tid, timestamp=victim_ts,
                sender_id=str(vid), recipient_id=col_wallet["wallet_id"],
                txn_type="P2P_SEND", amount_tk=amount, fee_tk=fee,
                sender_balance_before=round(bal_b, 2),
                sender_balance_after=round(bal_a, 2),
                recipient_balance_before=round(col_wallet["balance"] - amount, 2),
                recipient_balance_after=round(col_wallet["balance"], 2),
                channel="USSD", agent_id=None,
                device_id=prof["device_id"], device_changed=0,
                location_changed=0, session_seconds=int(rng.uniform(20, 80)),
                pin_attempts=1, counterparty_first_time=first_time,
            ))
            labels.append(_label(tid, 1, "S2", "victim_send", case_id,
                                 expected_band="WARN"))

        # Collector cash-outs (80-95 % within 1-3 h)
        cashout_ratio = float(rng.uniform(*cfg.fraud.s2_cashout_ratio_range))
        co_amount = col_wallet["balance"] * cashout_ratio
        co_delay_h = float(rng.uniform(*cfg.fraud.s2_cashout_delay_h))
        co_ts = victim_ts + timedelta(hours=co_delay_h)

        remaining = co_amount
        while remaining > 500 and co_ts <= sim_end:
            chunk = min(remaining, float(cfg.agent_cashout_max_txn))
            chunk = round(chunk / 10) * 10
            fee_co = _fee(cfg, "CASH_OUT_AGENT", chunk)

            tid = _make_txn_id(counter)
            txns.append(dict(
                txn_id=tid, timestamp=co_ts,
                sender_id=col_wallet["wallet_id"], recipient_id=None,
                txn_type="CASH_OUT_AGENT", amount_tk=chunk, fee_tk=fee_co,
                sender_balance_before=round(col_wallet["balance"], 2),
                sender_balance_after=round(col_wallet["balance"] - chunk - fee_co, 2),
                recipient_balance_before=None, recipient_balance_after=None,
                channel="AGENT_ASSISTED", agent_id="A0001",
                device_id=col_wallet["device_id"], device_changed=0,
                location_changed=0, session_seconds=int(rng.uniform(10, 30)),
                pin_attempts=1, counterparty_first_time=0,
            ))
            labels.append(_label(tid, 1, "S2", "cashout", case_id,
                                 expected_band="HIGH"))
            col_wallet["balance"] -= (chunk + fee_co)
            remaining -= chunk
            co_ts += timedelta(minutes=float(rng.uniform(5, 20)))

    return txns, labels


# ── S3: Money-mule chain / collector funnel ────────────────────────────────────

def inject_s3(
    cfg: SimpleNamespace, rng: np.random.Generator,
    customers: pd.DataFrame, profiles: Dict[str, dict],
    counter: itertools.count,
    sim_start: datetime, sim_end: datetime,
) -> Tuple[List[dict], List[dict]]:
    txns: List[dict] = []
    labels: List[dict] = []

    n_chains = cfg.fraud.s3_chain_count
    all_cids = customers["customer_id"].tolist()

    for chain_idx in range(n_chains):
        case_id    = f"CASE-S3-{chain_idx+1:03d}"
        day_offset = int(rng.integers(1, cfg.sim_days - 2))
        chain_start = sim_start + timedelta(
            days=day_offset, hours=int(rng.integers(8, 22))
        )

        n_hops   = int(rng.integers(*cfg.fraud.s3_hops_range))
        # First hop: from a victim (customer)
        victim_id = str(rng.choice(all_cids))
        victim_prof = profiles[victim_id]
        start_amount = float(rng.uniform(5000, 25000))
        start_amount = min(start_amount, victim_prof["balance"])
        start_amount = round(start_amount / 100) * 100

        # Source → first mule wallet
        mule_wallets = []
        for h in range(n_hops):
            age_d = float(rng.uniform(*cfg.fraud.s3_wallet_age_d_range))
            mw = dict(
                wallet_id=f"W-{rng.integers(10000, 99999):05d}",
                balance=0.0,
                device_id=f"D-MUL-{chain_idx:02d}-{h:02d}",
                reg_ts=chain_start - timedelta(days=age_d),
            )
            mule_wallets.append(mw)

        current_sender = victim_id
        current_amount = start_amount
        current_ts     = chain_start

        for h, mule in enumerate(mule_wallets):
            forward_ratio = float(rng.uniform(*cfg.fraud.s3_forward_ratio_range))
            hop_delay_min = float(rng.uniform(*cfg.fraud.s3_hop_delay_min))

            fee = _fee(cfg, "P2P_SEND", current_amount)

            if h == 0:
                # victim send
                prof = profiles[victim_id]
                if prof["balance"] < current_amount + fee:
                    current_amount = max(0, prof["balance"] - fee - 10)
                if current_amount < 100:
                    break
                bal_b = prof["balance"]
                prof["balance"] -= (current_amount + fee)
                bal_a = prof["balance"]
                mule["balance"] += current_amount

                tid = _make_txn_id(counter)
                txns.append(dict(
                    txn_id=tid, timestamp=current_ts,
                    sender_id=victim_id, recipient_id=mule["wallet_id"],
                    txn_type="P2P_SEND", amount_tk=current_amount, fee_tk=fee,
                    sender_balance_before=round(bal_b, 2),
                    sender_balance_after=round(bal_a, 2),
                    recipient_balance_before=0.0,
                    recipient_balance_after=round(mule["balance"], 2),
                    channel="APP", agent_id=None,
                    device_id=prof["device_id"], device_changed=1,
                    location_changed=1, session_seconds=int(rng.uniform(10, 40)),
                    pin_attempts=1, counterparty_first_time=1,
                ))
                labels.append(_label(tid, 1, "S3", "victim_send", case_id,
                                     expected_band="HIGH"))
            else:
                # mule hop
                prev_mule = mule_wallets[h - 1]
                hop_amount = round(prev_mule["balance"] * forward_ratio / 10) * 10
                if hop_amount < 100:
                    break

                fee = _fee(cfg, "P2P_SEND", hop_amount)
                bal_b_p = prev_mule["balance"]
                prev_mule["balance"] -= (hop_amount + fee)
                mule["balance"] += hop_amount

                tid = _make_txn_id(counter)
                txns.append(dict(
                    txn_id=tid, timestamp=current_ts,
                    sender_id=prev_mule["wallet_id"], recipient_id=mule["wallet_id"],
                    txn_type="P2P_SEND", amount_tk=hop_amount, fee_tk=fee,
                    sender_balance_before=round(bal_b_p, 2),
                    sender_balance_after=round(prev_mule["balance"], 2),
                    recipient_balance_before=round(mule["balance"] - hop_amount, 2),
                    recipient_balance_after=round(mule["balance"], 2),
                    channel="APP", agent_id=None,
                    device_id=mule["device_id"], device_changed=0,
                    location_changed=0, session_seconds=int(rng.uniform(5, 20)),
                    pin_attempts=1, counterparty_first_time=1,
                ))
                labels.append(_label(tid, 1, "S3", "mule_hop", case_id,
                                     expected_band="HIGH"))
                current_amount = hop_amount

            current_ts += timedelta(minutes=hop_delay_min)
            if current_ts > sim_end:
                break

        # Final cash-out from last mule
        last_mule = mule_wallets[-1]
        if last_mule["balance"] > 500:
            co_amount = min(last_mule["balance"], float(cfg.agent_cashout_max_txn))
            co_amount = round(co_amount / 10) * 10
            fee_co    = _fee(cfg, "CASH_OUT_AGENT", co_amount)
            tid = _make_txn_id(counter)
            txns.append(dict(
                txn_id=tid, timestamp=current_ts,
                sender_id=last_mule["wallet_id"], recipient_id=None,
                txn_type="CASH_OUT_AGENT", amount_tk=co_amount, fee_tk=fee_co,
                sender_balance_before=round(last_mule["balance"], 2),
                sender_balance_after=round(last_mule["balance"] - co_amount - fee_co, 2),
                recipient_balance_before=None, recipient_balance_after=None,
                channel="AGENT_ASSISTED", agent_id="A0391",  # shared rogue agent
                device_id=last_mule["device_id"], device_changed=0,
                location_changed=0, session_seconds=int(rng.uniform(10, 30)),
                pin_attempts=1, counterparty_first_time=0,
            ))
            labels.append(_label(tid, 1, "S3", "cashout", case_id,
                                 expected_band="HIGH"))

    return txns, labels


# ── S4: Fake seller ──────────────────────────────────────────────────────────

def inject_s4(
    cfg: SimpleNamespace, rng: np.random.Generator,
    customers: pd.DataFrame, profiles: Dict[str, dict],
    counter: itertools.count,
    sim_start: datetime, sim_end: datetime,
) -> Tuple[List[dict], List[dict]]:
    txns: List[dict] = []
    labels: List[dict] = []

    n_sellers = cfg.fraud.s4_seller_count
    all_cids  = customers["customer_id"].tolist()

    for sel_idx in range(n_sellers):
        case_id   = f"CASE-S4-{sel_idx+1:03d}"
        day_off   = int(rng.integers(3, cfg.sim_days - 5))
        first_ts  = sim_start + timedelta(days=day_off, hours=int(rng.integers(9, 18)))
        age_d     = float(rng.uniform(*cfg.fraud.s4_seller_age_d_range))

        seller = dict(
            wallet_id=f"W-{rng.integers(10000, 99999):05d}",
            balance=0.0,
            device_id=f"D-SEL-{sel_idx:03d}-1",
            reg_ts=first_ts - timedelta(days=age_d),
        )

        n_buyers = int(rng.integers(*cfg.fraud.s4_buyers_per_seller))
        buyer_ids = rng.choice(all_cids, size=min(n_buyers, len(all_cids)), replace=False)
        buyer_ts  = first_ts

        for bid in buyer_ids:
            prof   = profiles[str(bid)]
            amount = float(rng.uniform(*cfg.fraud.s4_buyer_amount_range))
            amount = round(amount / 10) * 10
            amount = min(amount, prof["balance"],
                         _get_kyc(cfg, prof["kyc_level"], "per_txn_send_max"))
            if amount < 100:
                continue

            fee = _fee(cfg, "P2P_SEND", amount)
            bal_b = prof["balance"]
            prof["balance"] -= (amount + fee)
            seller["balance"] += amount

            buyer_ts += timedelta(hours=float(rng.uniform(0.5, 6)))
            if buyer_ts > sim_end:
                break

            tid = _make_txn_id(counter)
            txns.append(dict(
                txn_id=tid, timestamp=buyer_ts,
                sender_id=str(bid), recipient_id=seller["wallet_id"],
                txn_type="P2P_SEND", amount_tk=amount, fee_tk=fee,
                sender_balance_before=round(bal_b, 2),
                sender_balance_after=round(prof["balance"], 2),
                recipient_balance_before=round(seller["balance"] - amount, 2),
                recipient_balance_after=round(seller["balance"], 2),
                channel="APP", agent_id=None,
                device_id=prof["device_id"], device_changed=0,
                location_changed=0, session_seconds=int(rng.uniform(15, 60)),
                pin_attempts=1, counterparty_first_time=1,
            ))
            labels.append(_label(tid, 1, "S4", "victim_send", case_id,
                                 expected_band="WARN"))

        # Cash-out in the evening (1-2 agents, NO supplier outflows)
        co_ts = buyer_ts + timedelta(hours=float(rng.uniform(2, 8)))
        remaining = seller["balance"]
        for co_i in range(2):
            if remaining < 500 or co_ts > sim_end:
                break
            chunk = min(remaining, float(cfg.agent_cashout_max_txn))
            chunk = round(chunk / 10) * 10
            fee_co = _fee(cfg, "CASH_OUT_AGENT", chunk)
            tid = _make_txn_id(counter)
            txns.append(dict(
                txn_id=tid, timestamp=co_ts,
                sender_id=seller["wallet_id"], recipient_id=None,
                txn_type="CASH_OUT_AGENT", amount_tk=chunk, fee_tk=fee_co,
                sender_balance_before=round(remaining, 2),
                sender_balance_after=round(remaining - chunk - fee_co, 2),
                recipient_balance_before=None, recipient_balance_after=None,
                channel="AGENT_ASSISTED", agent_id="A0001",
                device_id=seller["device_id"], device_changed=0,
                location_changed=0, session_seconds=int(rng.uniform(10, 30)),
                pin_attempts=1, counterparty_first_time=0,
            ))
            labels.append(_label(tid, 1, "S4", "cashout", case_id,
                                 expected_band="WARN"))
            remaining -= (chunk + fee_co)
            co_ts += timedelta(minutes=float(rng.uniform(10, 30)))

    return txns, labels


# ── S5: Rogue agent ───────────────────────────────────────────────────────────

def inject_s5(
    cfg: SimpleNamespace, rng: np.random.Generator,
    customers: pd.DataFrame, agents: pd.DataFrame,
    profiles: Dict[str, dict],
    counter: itertools.count,
    sim_start: datetime, sim_end: datetime,
    s1_s4_fraud_wallet_ids: List[str],
) -> Tuple[List[dict], List[dict]]:
    txns: List[dict] = []
    labels: List[dict] = []

    rogue_agents = agents.sample(
        n=min(cfg.fraud.s5_rogue_agent_count, len(agents)),
        random_state=42
    )

    all_cids = customers["customer_id"].tolist()
    flagged_wallets = s1_s4_fraud_wallet_ids or []

    for _, ragent in rogue_agents.iterrows():
        aid       = ragent["agent_id"]
        case_id   = f"CASE-S5-{aid}"
        peer_mean = ragent["typical_daily_cashouts"]
        multiplier = float(rng.uniform(*cfg.fraud.s5_cashout_multiplier))
        n_excess   = int(peer_mean * multiplier)
        n_days     = int(rng.integers(*cfg.fraud.s5_days_active))
        day_offset = int(rng.integers(5, cfg.sim_days - n_days - 1))

        for d in range(n_days):
            day = sim_start + timedelta(days=day_offset + d)
            flagged_share = float(rng.uniform(*cfg.fraud.s5_flagged_wallet_share))
            n_flagged  = int(n_excess * flagged_share)
            n_normal   = n_excess - n_flagged

            # Excess cash-outs from flagged wallets
            fw_sample = (rng.choice(flagged_wallets, size=min(n_flagged, len(flagged_wallets)), replace=True)
                         if flagged_wallets else [])
            for fw_id in fw_sample:
                amount = float(rng.choice(
                    [29000, 29500, 29800, 28000, 27000],
                ))
                fee_co = _fee(cfg, "CASH_OUT_AGENT", amount)
                hour   = int(rng.integers(8, 20))
                ts     = day.replace(hour=hour) + timedelta(minutes=int(rng.integers(0, 60)))
                if ts > sim_end:
                    continue

                tid = _make_txn_id(counter)
                txns.append(dict(
                    txn_id=tid, timestamp=ts,
                    sender_id=fw_id, recipient_id=None,
                    txn_type="CASH_OUT_AGENT", amount_tk=amount, fee_tk=fee_co,
                    sender_balance_before=amount + fee_co,
                    sender_balance_after=0.0,
                    recipient_balance_before=None, recipient_balance_after=None,
                    channel="AGENT_ASSISTED", agent_id=aid,
                    device_id=f"D-{fw_id}-1", device_changed=0,
                    location_changed=0, session_seconds=int(rng.uniform(10, 30)),
                    pin_attempts=1, counterparty_first_time=0,
                ))
                labels.append(_label(tid, 1, "S5", "rogue_agent_cashout", case_id,
                                     expected_band="HIGH"))

            # Normal-looking excess from real customers
            normal_sample = rng.choice(all_cids, size=min(n_normal, len(all_cids)), replace=True)
            for cid in normal_sample:
                prof   = profiles[str(cid)]
                amount = float(rng.uniform(500, cfg.agent_cashout_max_txn))
                amount = min(amount, prof["balance"])
                amount = round(amount / 10) * 10
                if amount < 100:
                    continue
                fee_co = _fee(cfg, "CASH_OUT_AGENT", amount)
                hour   = int(rng.integers(8, 20))
                ts     = day.replace(hour=hour) + timedelta(minutes=int(rng.integers(0, 60)))
                if ts > sim_end:
                    continue
                bal_b = prof["balance"]
                prof["balance"] = max(0.0, prof["balance"] - amount - fee_co)

                tid = _make_txn_id(counter)
                txns.append(dict(
                    txn_id=tid, timestamp=ts,
                    sender_id=str(cid), recipient_id=None,
                    txn_type="CASH_OUT_AGENT", amount_tk=amount, fee_tk=fee_co,
                    sender_balance_before=round(bal_b, 2),
                    sender_balance_after=round(prof["balance"], 2),
                    recipient_balance_before=None, recipient_balance_after=None,
                    channel="AGENT_ASSISTED", agent_id=aid,
                    device_id=prof["device_id"], device_changed=0,
                    location_changed=0, session_seconds=int(rng.uniform(10, 30)),
                    pin_attempts=1, counterparty_first_time=0,
                ))
                # NOT fraud label (agent-side, customer is legitimate)
                labels.append(_label(tid, 0, "", "", "", expected_band="ALLOW"))

    return txns, labels


# ── S6: SIM-swap takeover ─────────────────────────────────────────────────────

def inject_s6(
    cfg: SimpleNamespace, rng: np.random.Generator,
    customers: pd.DataFrame, profiles: Dict[str, dict],
    counter: itertools.count,
    sim_start: datetime, sim_end: datetime,
) -> Tuple[List[dict], List[dict]]:
    txns: List[dict] = []
    labels: List[dict] = []

    victims_pool = customers[
        (customers["device_type"] == "smartphone") &
        (pd.to_datetime(customers["registration_date"]) < pd.Timestamp(sim_start) - timedelta(days=30))
    ]["customer_id"].tolist()
    n_victims = min(cfg.fraud.s6_victim_count, len(victims_pool))
    victims   = rng.choice(victims_pool, size=n_victims, replace=False)

    for v_idx, victim_id in enumerate(victims):
        prof    = profiles[str(victim_id)]
        case_id = f"CASE-S6-{v_idx+1:04d}"

        day_off  = int(rng.integers(cfg.fraud.s6_silence_h // 24 + 1, cfg.sim_days - 1))
        base_day = sim_start + timedelta(days=day_off)
        hour     = int(rng.uniform(*cfg.fraud.s6_hour_range))
        event_ts = base_day.replace(hour=hour) + timedelta(minutes=int(rng.integers(0, 60)))
        if event_ts > sim_end:
            continue

        drain    = float(rng.uniform(*cfg.fraud.s6_drain_ratio_range))
        if prof["balance"] < 500:
            prof["balance"] = float(rng.uniform(5000, 20000))
        amount   = round(prof["balance"] * drain / 10) * 10
        amount   = min(amount, _get_kyc(cfg, prof["kyc_level"], "per_txn_send_max"))
        if amount < 100:
            continue

        fw = _new_fraud_wallet(cfg, rng, event_ts, (1, float(cfg.fraud.s6_recipient_age_h)))
        fee = _fee(cfg, "P2P_SEND", amount)
        bal_b = prof["balance"]
        prof["balance"] -= (amount + fee)

        tid = _make_txn_id(counter)
        txns.append(dict(
            txn_id=tid, timestamp=event_ts,
            sender_id=str(victim_id), recipient_id=fw["wallet_id"],
            txn_type="P2P_SEND", amount_tk=amount, fee_tk=fee,
            sender_balance_before=round(bal_b, 2),
            sender_balance_after=round(prof["balance"], 2),
            recipient_balance_before=0.0,
            recipient_balance_after=round(amount, 2),
            channel="APP", agent_id=None,
            device_id=f"D-{victim_id}-SWAP",  # new device_id
            device_changed=1, location_changed=0,
            session_seconds=int(rng.uniform(20, 80)),
            pin_attempts=1, counterparty_first_time=1,
        ))
        # S6 intentionally borderline: score 55-75 → WARN (not HIGH)
        labels.append(_label(tid, 1, "S6", "takeover_send", case_id,
                             expected_band="WARN"))

    return txns, labels


# ── S7: Guided victim ─────────────────────────────────────────────────────────

def inject_s7(
    cfg: SimpleNamespace, rng: np.random.Generator,
    customers: pd.DataFrame, profiles: Dict[str, dict],
    counter: itertools.count,
    sim_start: datetime, sim_end: datetime,
) -> Tuple[List[dict], List[dict]]:
    """S7 is a behavioural variant injected as part of S1/S2 rows."""
    txns: List[dict] = []
    labels: List[dict] = []

    # Target elderly / first-time users with low literacy
    victims_pool = customers[
        (customers["digital_literacy"] == "low") &
        (customers["age"] >= 50)
    ]["customer_id"].tolist()
    if not victims_pool:
        victims_pool = customers[
            customers["digital_literacy"] == "low"
        ]["customer_id"].tolist()

    n_s7 = max(30, int(cfg.fraud.s2_collector_count * 2))
    n_victims = min(n_s7, len(victims_pool))
    victims = rng.choice(victims_pool, size=n_victims, replace=False)

    for v_idx, victim_id in enumerate(victims):
        prof    = profiles[str(victim_id)]
        case_id = f"CASE-S7-{v_idx+1:03d}"

        day_off  = int(rng.integers(1, cfg.sim_days - 1))
        base_day = sim_start + timedelta(days=day_off)
        hour     = int(rng.integers(10, 20))
        event_ts = base_day.replace(hour=hour) + timedelta(minutes=int(rng.integers(0, 60)))
        if event_ts > sim_end:
            continue

        # Fresh recipient
        fw = _new_fraud_wallet(cfg, rng, event_ts,
                               (1, float(cfg.fraud.s7_recipient_age_h)))

        median = prof["median_send_tk"]
        multiplier = float(rng.uniform(*cfg.fraud.s7_amount_multiplier))
        amount = round(median * multiplier / 10) * 10
        amount = min(amount, prof["balance"],
                     _get_kyc(cfg, prof["kyc_level"], "per_txn_send_max"))
        if amount < 100:
            continue

        session_s  = int(rng.uniform(*cfg.fraud.s7_session_range_s))
        pin_att    = int(rng.integers(*cfg.fraud.s7_pin_attempts_range))
        fee        = _fee(cfg, "P2P_SEND", amount)
        bal_b      = prof["balance"]
        prof["balance"] -= (amount + fee)
        fw["balance"]   += amount

        tid = _make_txn_id(counter)
        txns.append(dict(
            txn_id=tid, timestamp=event_ts,
            sender_id=str(victim_id), recipient_id=fw["wallet_id"],
            txn_type="P2P_SEND", amount_tk=amount, fee_tk=fee,
            sender_balance_before=round(bal_b, 2),
            sender_balance_after=round(prof["balance"], 2),
            recipient_balance_before=0.0,
            recipient_balance_after=round(fw["balance"], 2),
            channel="USSD", agent_id=None,
            device_id=prof["device_id"], device_changed=0,
            location_changed=0, session_seconds=session_s,
            pin_attempts=pin_att, counterparty_first_time=1,
        ))
        labels.append(_label(tid, 1, "S7", "victim_send", case_id,
                             expected_band="WARN"))

        # Follow-up cash-out at agent
        co_ts = event_ts + timedelta(minutes=float(rng.uniform(5, 30)))
        if co_ts <= sim_end and fw["balance"] > 200:
            co_amt = min(fw["balance"], float(cfg.agent_cashout_max_txn))
            co_amt = round(co_amt / 10) * 10
            fee_co = _fee(cfg, "CASH_OUT_AGENT", co_amt)
            tid    = _make_txn_id(counter)
            txns.append(dict(
                txn_id=tid, timestamp=co_ts,
                sender_id=fw["wallet_id"], recipient_id=None,
                txn_type="CASH_OUT_AGENT", amount_tk=co_amt, fee_tk=fee_co,
                sender_balance_before=round(fw["balance"], 2),
                sender_balance_after=round(fw["balance"] - co_amt - fee_co, 2),
                recipient_balance_before=None, recipient_balance_after=None,
                channel="AGENT_ASSISTED", agent_id="A0001",
                device_id=fw["device_id"], device_changed=0,
                location_changed=0, session_seconds=int(rng.uniform(10, 30)),
                pin_attempts=1, counterparty_first_time=0,
            ))
            labels.append(_label(tid, 1, "S7", "cashout", case_id,
                                 expected_band="WARN"))
            fw["balance"] -= (co_amt + fee_co)

    return txns, labels
