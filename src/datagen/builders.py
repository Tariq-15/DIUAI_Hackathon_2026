"""
src/datagen/builders.py
========================
Module 2 – build_customers(), build_agents(), build_profiles()

Generates the two static reference tables (customers.csv, agents.csv)
and a per-customer behaviour profile dict used by the transaction simulator.
No randomness outside of numpy/random seeded by cfg.seed.
"""
from __future__ import annotations

import hashlib
import random
import numpy as np
import pandas as pd
from datetime import timedelta
from types import SimpleNamespace
from typing import Dict, List


# ── helpers ──────────────────────────────────────────────────────────────────

def _weighted_choice(rng: np.random.Generator, choices: dict) -> str:
    keys = list(choices.keys())
    weights = [choices[k] for k in keys]
    return rng.choice(keys, p=np.array(weights) / sum(weights))


def _fake_phone_hash(rng: np.random.Generator, uid: str) -> str:
    """Deterministic SHA-256 of a synthetic 11-digit number (not real)."""
    fake_num = f"017{rng.integers(10_000_000, 99_999_999):08d}"
    return hashlib.sha256((uid + fake_num).encode()).hexdigest()[:16]


def _random_date(rng: np.random.Generator, start: pd.Timestamp, end: pd.Timestamp) -> pd.Timestamp:
    delta_days = (end - start).days
    return start + timedelta(days=int(rng.integers(0, max(delta_days, 1))))


# ── Module 2a: build_customers ───────────────────────────────────────────────

FIRST_NAMES_M = [
    "Rahim", "Karim", "Imran", "Hasan", "Jakir", "Rafiq", "Selim",
    "Jahangir", "Mamun", "Tarek", "Faruk", "Nizam", "Badrul", "Sohel",
    "Rubel", "Riyad", "Shahin", "Minhaj", "Arif", "Habib",
]
FIRST_NAMES_F = [
    "Salma", "Nusrat", "Rokeya", "Fatema", "Nasrin", "Rima", "Sumaiya",
    "Mitu", "Layla", "Piya", "Sonia", "Shirin", "Mohona", "Lovely",
    "Shukla", "Rekha", "Mina", "Jahanara", "Dolly", "Meher",
]
LAST_NAMES = [
    "Hossain", "Begum", "Islam", "Rahman", "Khatun", "Ahmed", "Akter",
    "Molla", "Sheikh", "Bepari", "Sarkar", "Biswas", "Das", "Roy",
    "Mondal", "Alam", "Chowdhury", "Talukder", "Dey", "Paul",
]


def build_customers(cfg: SimpleNamespace, rng: np.random.Generator) -> pd.DataFrame:
    """Return customers DataFrame (10,000 rows) per spec 3.1."""
    n = cfg.n_customers
    window_start = cfg.sim_start_dt - timedelta(days=730)   # up to 2 years pre-window
    window_end   = cfg.sim_start_dt - timedelta(days=1)
    new_wallet_start = cfg.sim_start_dt                      # 5% register during window

    # KYC mix
    kyc_choices   = [1, 2, 3]
    kyc_mix_vals  = [cfg.kyc_level_mix[str(k)] for k in kyc_choices]

    div_names   = list(cfg.divisions.__dict__.keys())
    div_weights = list(cfg.divisions.__dict__.values())

    occ_list = list(cfg.occupations)    # already a list

    rows = []
    for i in range(n):
        cid = f"C{i+1:06d}"
        gender = _weighted_choice(rng, cfg.gender_mix.__dict__)
        first_name = rng.choice(FIRST_NAMES_M if gender == "M" else FIRST_NAMES_F)
        last_name  = rng.choice(LAST_NAMES)
        name = f"{first_name} {last_name}"

        age = int(rng.integers(16, 76))
        occupation = occ_list[int(rng.integers(0, len(occ_list)))]
        # shop owners get mid income band
        if occupation == "shop owner":
            income_band = "mid"
        else:
            income_band = _weighted_choice(rng, cfg.income_band_mix.__dict__)

        division  = rng.choice(div_names, p=np.array(div_weights) / sum(div_weights))
        area_type = _weighted_choice(rng, cfg.area_type_mix.__dict__)
        kyc_level = int(rng.choice(kyc_choices, p=np.array(kyc_mix_vals) / sum(kyc_mix_vals)))

        # Sylhet has slightly higher fraud exposure → bias literacy toward low
        if division == "Sylhet":
            dig_lit = _weighted_choice(rng, {"low": 0.50, "medium": 0.35, "high": 0.15})
        else:
            dig_lit = _weighted_choice(rng, cfg.digital_literacy_mix.__dict__)

        dev_type = _weighted_choice(rng, cfg.device_type_mix.__dict__)

        # 5 % register during the window
        if rng.random() < cfg.new_wallet_fraction:
            reg_date = _random_date(rng, pd.Timestamp(new_wallet_start),
                                    pd.Timestamp(cfg.sim_end_dt))
        else:
            reg_date = _random_date(rng, pd.Timestamp(window_start),
                                    pd.Timestamp(window_end))

        phone_hash = _fake_phone_hash(rng, cid)

        rows.append(dict(
            customer_id    = cid,
            name           = name,
            phone_hash     = phone_hash,
            age            = age,
            gender         = gender,
            occupation     = occupation,
            division       = division,
            area_type      = area_type,
            kyc_level      = kyc_level,
            registration_date = str(reg_date.date()),
            device_type    = dev_type,
            digital_literacy = dig_lit,
            income_band    = income_band,
            home_agent_id  = None,   # filled in after agents are built
        ))

    df = pd.DataFrame(rows)
    return df


# ── Module 2b: build_agents ──────────────────────────────────────────────────

def build_agents(cfg: SimpleNamespace, rng: np.random.Generator,
                 customers: pd.DataFrame) -> pd.DataFrame:
    """Return agents DataFrame (300 rows) per spec 3.2."""
    n = cfg.n_agents
    div_names   = list(cfg.divisions.__dict__.keys())
    div_weights = list(cfg.divisions.__dict__.values())

    window_start = cfg.sim_start_dt - timedelta(days=730)
    window_end   = cfg.sim_start_dt - timedelta(days=1)

    peer_counter: Dict[str, int] = {}
    rows = []
    for i in range(n):
        aid = f"A{i+1:04d}"
        division  = rng.choice(div_names, p=np.array(div_weights) / sum(div_weights))
        area_type = _weighted_choice(rng, cfg.area_type_mix.__dict__)

        # Peer group id  e.g.  PG-DHK-U-03
        div_code  = division[:3].upper()
        area_code = area_type[0].upper()
        pg_key    = f"{div_code}-{area_code}"
        peer_counter[pg_key] = peer_counter.get(pg_key, 0) + 1
        pg_num    = (peer_counter[pg_key] - 1) // 10 + 1
        peer_group_id = f"PG-{pg_key}-{pg_num:02d}"

        cap_range = cfg.agent_capacity.__dict__[area_type]
        daily_cap = int(rng.integers(cap_range.min, cap_range.max + 1))

        # Typical daily cash-outs: peer mean ~46 with ±25% variation
        peer_mean = int(rng.integers(35, 60))
        typical   = max(5, int(peer_mean * rng.uniform(0.75, 1.25)))

        reg_date = _random_date(rng, pd.Timestamp(window_start), pd.Timestamp(window_end))

        rows.append(dict(
            agent_id                  = aid,
            division                  = division,
            area_type                 = area_type,
            peer_group_id             = peer_group_id,
            daily_cashout_capacity_tk = daily_cap,
            typical_daily_cashouts    = typical,
            registration_date         = str(reg_date.date()),
        ))

    df = pd.DataFrame(rows)

    # Assign home_agent_id to each customer by matching division/area_type
    def _pick_agent(row):
        matches = df[(df.division == row.division) & (df.area_type == row.area_type)]
        if len(matches) == 0:
            matches = df
        return matches.sample(1, random_state=int(rng.integers(1e6))).iloc[0]["agent_id"]

    customers["home_agent_id"] = customers.apply(_pick_agent, axis=1)
    return df


# ── Module 2c: build_profiles ────────────────────────────────────────────────

def build_profiles(cfg: SimpleNamespace, rng: np.random.Generator,
                   customers: pd.DataFrame,
                   all_customer_ids: List[str]) -> Dict[str, dict]:
    """
    Return a dict  customer_id → profile, used by the simulator to
    draw realistic transaction amounts and timing.
    """
    profiles: Dict[str, dict] = {}
    id_arr = np.array(all_customer_ids)

    # Pre-compute lognormal params per income band
    ln_params = {k: (v.mu, v.sigma)
                 for k, v in cfg.income_band_lognormal.__dict__.items()}
    spw_params = cfg.sends_per_week.__dict__

    # hour weights  (24 floats, normalised)
    hw = np.array(cfg.hour_weights)
    hw = hw / hw.sum()

    for _, row in customers.iterrows():
        cid = row["customer_id"]
        band = row["income_band"]
        mu, sigma = ln_params[band]

        # Median send amount (lognormal draw)
        median_send = float(np.exp(rng.normal(mu, sigma)))
        median_send = max(50.0, median_send)

        # Sends per week
        spw_key = "shop_owner" if row["occupation"] == "shop owner" else band
        lam = spw_params.get(spw_key, spw_params[band])
        sends_per_week = max(0.5, float(rng.poisson(lam)))

        # Regular contacts (3-8 other customer ids, excluding self)
        n_contacts = int(rng.integers(
            cfg.regular_contacts_range[0],
            cfg.regular_contacts_range[1] + 1
        ))
        pool = id_arr[id_arr != cid]
        contacts = list(rng.choice(pool, size=min(n_contacts, len(pool)), replace=False))

        # Active hours: pick two peak centres from the normal-hour distribution
        # and build a personalised weight vector
        peak1 = int(rng.choice(np.arange(8, 11), p=[0.35, 0.35, 0.30]))
        peak2 = int(rng.choice(np.arange(19, 23), p=[0.25, 0.35, 0.25, 0.15]))

        personal_hw = hw.copy()
        personal_hw[peak1]   *= 3.0
        personal_hw[peak2]   *= 3.0
        personal_hw[peak1-1] *= 1.5
        personal_hw[peak2-1] *= 1.5
        # suppress night (00-04)
        for h in range(5):
            personal_hw[h] *= 0.2
        personal_hw = personal_hw / personal_hw.sum()

        # Initial balance (lognormal, capped at KYC balance limit)
        kyc = cfg.kyc_caps[str(row["kyc_level"])]
        init_bal_mu, init_bal_sigma = getattr(cfg.initial_balance_by_income, band).mu, \
                                       getattr(cfg.initial_balance_by_income, band).sigma
        init_balance = min(
            float(np.exp(rng.normal(init_bal_mu, init_bal_sigma))),
            float(kyc.max_balance)
        )
        init_balance = max(100.0, init_balance)

        profiles[cid] = dict(
            customer_id    = cid,
            income_band    = band,
            kyc_level      = int(row["kyc_level"]),
            occupation     = row["occupation"],
            digital_literacy = row["digital_literacy"],
            device_type    = row["device_type"],
            division       = row["division"],
            area_type      = row["area_type"],
            home_agent_id  = row["home_agent_id"],
            registration_date = pd.Timestamp(row["registration_date"]),
            median_send_tk = median_send,
            sends_per_week = sends_per_week,
            regular_contacts = contacts,
            active_hour_weights = personal_hw,
            balance        = init_balance,
            daily_sent_tk  = 0.0,
            current_day    = None,
            device_id      = f"D-{cid}-1",
        )

    return profiles
