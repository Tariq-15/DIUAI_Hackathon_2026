"""Build the whole synthetic world.

    python -m src.datagen.generate                 # full: ~10k customers, ~600k transactions
    python -m src.datagen.generate --scale 0.1     # quick: ~1k customers (tests / laptops)
    python -m src.datagen.generate --csv           # also write CSVs next to the Parquet files

Outputs (data/generated/): customers, agents, merchants, billers, transactions, labels,
account_events, complaints, cases, wallet_truth, agent_truth (+ planted_scenarios.json,
generation_report.json). A ~20k-row sample goes to data/sample/ (small enough for git).
"""
from __future__ import annotations

import argparse
import time

import numpy as np
import pandas as pd

from src.common.config import DAY, load_config, resolve, save_json, split_of_day
from .engine import FAIL_NAMES, Sim
from .fraud import FraudPlanner
from .normal import generate_normal
from .planted import Planter
from .world import ACCT_EVENTS, AGE_BANDS, CHANNELS, TXN_TYPES, World

VICTIM_ROLES = {"takeover_drain", "victim_payment", "buyer_payment", "coerced_send", "card_add_money"}
COMPLAINT_P = {"S1": 0.6, "S2": 0.35, "S5": 0.65, "S6": 0.9, "S7": 0.5, "S8": 0.95}
COMPLAINT_DELAY_H = {"S1": (2, 72), "S2": (3, 96), "S5": (24, 120), "S6": (2, 12), "S7": (2, 72), "S8": (24, 96)}


def build(cfg: dict, verbose: bool = True) -> dict:
    t_start = time.time()
    log = (lambda *a: print(*a, flush=True)) if verbose else (lambda *a: None)
    rng = np.random.default_rng(cfg["seed"])
    world = World(cfg, rng)
    log(f"[world] {world.n_cust:,} customers ({world.n_base:,} base + {world.n_cust - world.n_base:,} new legit), "
        f"{len(world.agents)} agents, {len(world.merchants)} merchants, {world.n_areas} areas")
    normal = generate_normal(world, cfg, rng)
    log(f"[normal] {len(normal['ts']):,} candidate events")
    sim = Sim(world, cfg, rng)
    planner = FraudPlanner(sim, cfg, rng)
    planner.setup_rings()
    planter = Planter(planner)
    planter.prepare_rogue()
    planter.plant_all()                      # reserve demo wallets before random cases are drawn
    planner.plan_cases()
    log(f"[fraud] {len(planner.cases)} cases planned, {world.n_cust - world.n_normal_customers} fraud wallets created")
    t0 = time.time()
    sim.run(normal)
    log(f"[ledger] {len(sim.cols['ts']):,} transactions written in {time.time() - t0:.1f}s")
    out = assemble(world, sim, planner, planter, cfg, rng)
    out["report"]["seconds_total"] = round(time.time() - t_start, 1)
    return out


def assemble(world: World, sim: Sim, planner: FraudPlanner, planter: Planter, cfg: dict, rng) -> dict:
    w = world
    c = sim.cols
    n = len(c["ts"])
    ids = np.array(w.ids, dtype=object)
    kind = np.array(w.kind, dtype=object)
    start = np.datetime64(cfg["world"]["start_date"], "s")
    ts = np.array(c["ts"], dtype=np.int64)
    txn_ids = np.array([f"T{i:08d}" for i in range(n)], dtype=object)
    area_names = np.array(w.area_name + [""], dtype=object)
    src = np.array(c["src"])
    dst = np.array(c["dst"])
    dev = np.array(c["dev"])
    area = np.array(c["area"])
    tx = pd.DataFrame({
        "txn_id": txn_ids,
        "ts": start + ts.astype("timedelta64[s]"),
        "txn_type": np.array(TXN_TYPES, dtype=object)[np.array(c["typ"])],
        "sender_id": ids[src], "sender_type": kind[src],
        "receiver_id": ids[dst], "receiver_type": kind[dst],
        "amount": np.round(np.array(c["amt"]), 2), "fee": np.array(c["fee"]),
        "status": np.where(np.array(c["fail"]) == 0, "SUCCESS", "FAILED"),
        "fail_reason": np.array(FAIL_NAMES, dtype=object)[np.array(c["fail"])],
        "sender_bal_before": np.round(np.array(c["sb0"], dtype=float), 2),
        "sender_bal_after": np.round(np.array(c["sb1"], dtype=float), 2),
        "receiver_bal_before": np.round(np.array(c["rb0"], dtype=float), 2),
        "receiver_bal_after": np.round(np.array(c["rb1"], dtype=float), 2),
        "device_id": [w.device_name(d) for d in dev],
        "channel": np.array(CHANNELS, dtype=object)[np.array(c["chan"])],
        "area_id": area_names[area],
    })
    # ---------------------------------------------------------------- labels
    lab = np.array(c["label"])
    labels_list = sim.labels
    scen = np.full(n, "NONE", dtype=object)
    case = np.full(n, "", dtype=object)
    role = np.full(n, "", dtype=object)
    has = lab >= 0
    if has.any():
        L = np.array(labels_list, dtype=object)
        scen[has] = L[lab[has], 0]
        case[has] = L[lab[has], 1]
        role[has] = L[lab[has], 2]
    labels = pd.DataFrame({"txn_id": txn_ids, "is_fraud": has.astype(np.int8), "scenario": scen,
                           "case_id": case, "fraud_role": role,
                           "split": [split_of_day(cfg, d) for d in (ts // DAY)]})
    # ---------------------------------------------------------------- account events
    ae = sorted(sim.acct_events, key=lambda r: r[0])
    ae_ts = np.array([r[0] for r in ae], dtype=np.int64)
    ae_lab = np.array([r[6] for r in ae])
    events = pd.DataFrame({
        "event_id": [f"E{i:07d}" for i in range(len(ae))],
        "ts": start + ae_ts.astype("timedelta64[s]"),
        "wallet_id": ids[np.array([r[1] for r in ae], dtype=np.int64)],
        "event_type": [ACCT_EVENTS[r[2] - 100] for r in ae],
        "device_id": [w.device_name(r[3]) for r in ae],
        "area_id": area_names[np.array([r[4] for r in ae], dtype=np.int64)],
        "channel": np.array(CHANNELS, dtype=object)[np.array([r[5] for r in ae], dtype=np.int64)],
        "case_id": [labels_list[i][1] if i >= 0 else "" for i in ae_lab],
    })
    # ---------------------------------------------------------------- complaints (16268 helpline)
    complaints = make_complaints(tx, labels, ts, cfg, rng, w, planter)
    # ---------------------------------------------------------------- entity tables
    nC = w.n_cust
    cust = pd.DataFrame({
        "wallet_id": ids[w.C0:w.C0 + nC], "msisdn": w.c_msisdn,
        "signup_ts": start + np.array(w.c_signup_ts, dtype=np.int64).astype("timedelta64[s]"),
        "kyc_level": ["KYC2" if k == 2 else "KYC1" for k in w.c_kyc],
        "channel": np.array(CHANNELS, dtype=object)[np.array(w.c_chan)],
        "segment": w.c_seg, "gender": w.c_gender,
        "age_band": np.array(AGE_BANDS, dtype=object)[np.array(w.c_ageb)],
        "division": [w.divisions[w.area_div[a]] for a in w.c_area],
        "area_id": area_names[np.array(w.c_area)],
        "urban_rural": np.where(w.area_urban[np.array(w.c_area)], "urban", "rural"),
        "home_agent_id": [w.ids[h[0]] for h in w.c_home_agents],
    })
    na = len(w.agents)
    agents = pd.DataFrame({
        "agent_id": [w.ids[a] for a in w.agents],
        "area_id": area_names[w.agent_area],
        "division": [w.divisions[w.area_div[a]] for a in w.agent_area],
        "urban_rural": np.where(w.area_urban[w.agent_area], "urban", "rural"),
        "onboard_ts": start + w.agent_onboard_ts.astype("timedelta64[s]"),
        "terminal_device_id": [w.device_name(i) for i in range(na)],
    })
    merchants = pd.DataFrame({
        "merchant_id": [w.ids[m] for m in w.merchants], "category": w.merchant_cat,
        "area_id": area_names[w.merchant_area],
        "onboard_ts": start + w.merchant_onboard_ts.astype("timedelta64[s]"),
    })
    from .world import BILLERS
    billers = pd.DataFrame({"biller_id": [b[0] for b in BILLERS], "name": [b[1] for b in BILLERS],
                            "kind": [b[2] for b in BILLERS]})
    # ---------------------------------------------------------------- ground truth (never used as features)
    cases = pd.DataFrame(planner.case_table(sim))
    cases["t0"] = start + cases["t0"].astype(np.int64).values.astype("timedelta64[s]")
    fr_counts = labels[labels.is_fraud == 1].groupby("case_id").size()
    cases["n_fraud_txns"] = cases["case_id"].map(fr_counts).fillna(0).astype(int)
    truth_rows = []
    for acct, roles in planner.roles.items():
        truth_rows.append(dict(wallet_id=w.ids[acct], roles=";".join(sorted(roles)),
                               ring_id=planner.wallet_ring.get(acct),
                               case_ids=";".join(sorted(planner.wallet_cases.get(acct, ())))))
    wallet_truth = pd.DataFrame(truth_rows)
    agent_truth = pd.DataFrame([dict(agent_id=w.ids[a], is_rogue=int(v["rogue"]), is_register_harvested=int(v["harvested"]),
                                     ring_id=v["ring"], episodes=";".join(f"{s}-{e}" for s, e in v["episodes"]))
                                for a, v in planner.agent_truth.items()])
    planted = planter.table(txn_ids)
    report = dict(
        seed=cfg["seed"], scale=cfg.get("_scale", 1.0), n_transactions=int(n),
        n_customers=int(nC), n_fraud_wallets=int(nC - w.n_normal_customers),
        fraud_rows=int(has.sum()), fraud_share=round(float(has.mean()), 5),
        fraud_rows_by_scenario=labels[labels.is_fraud == 1].scenario.value_counts().to_dict(),
        cases_by_scenario=cases.scenario.value_counts().to_dict(),
        status=tx.status.value_counts().to_dict(),
        txn_type_mix=tx.txn_type.value_counts().to_dict(),
        n_account_events=int(len(events)), n_complaints=int(len(complaints)),
    )
    return dict(customers=cust, agents=agents, merchants=merchants, billers=billers, transactions=tx, labels=labels,
                account_events=events, complaints=complaints, cases=cases, wallet_truth=wallet_truth,
                agent_truth=agent_truth, planted=planted, report=report)


def make_complaints(tx, labels, ts, cfg, rng, w, planter=None):
    end = cfg["world"]["n_days"] * DAY
    start = np.datetime64(cfg["world"]["start_date"], "s")
    rows = []
    fr = labels.index[(labels.is_fraud == 1).values & labels.fraud_role.isin(VICTIM_ROLES).values]
    first = {}
    for i in fr:
        key = (labels.case_id.iat[i], tx.sender_id.iat[i])
        if key not in first and tx.status.iat[i] == "SUCCESS":
            first[key] = i
    for (cid, victim), i in first.items():
        if cid.startswith(("SC-", "SB-")):              # planted demos get only their scripted complaints
            continue
        sc = labels.scenario.iat[i]
        if rng.random() > COMPLAINT_P.get(sc, 0.5):
            continue
        lo, hi = COMPLAINT_DELAY_H.get(sc, (2, 96))
        t = int(ts[i] + rng.uniform(lo, hi) * 3600)
        if t >= end:
            continue
        reported = tx.receiver_id.iat[i]
        if sc == "S8":
            victim, reported = "X_CARD", tx.receiver_id.iat[i]
        rows.append((t, victim, reported, "FRAUD", tx.txn_id.iat[i]))
    # noise: genuine wrong-send disputes against innocent wallets
    p2p = np.flatnonzero((tx.txn_type.values == "SEND_MONEY") & (labels.is_fraud.values == 0) &
                         (tx.receiver_type.values == "C"))
    k = int(len(p2p) * 0.0006)
    for i in rng.choice(p2p, k, replace=False) if k else []:
        t = int(ts[i] + rng.uniform(0.2, 48) * 3600)
        if t < end:
            rows.append((t, tx.sender_id.iat[i], tx.receiver_id.iat[i], "WRONG_SEND", tx.txn_id.iat[i]))
    for t, complainant, reported, key in (planter.complaints if planter else []):
        row = planter.captured.get(key)
        rows.append((int(t), w.ids[complainant], w.ids[reported], "FRAUD", tx.txn_id.iat[row] if row is not None else ""))
    rows.sort()
    return pd.DataFrame({
        "complaint_id": [f"CP{i:06d}" for i in range(len(rows))],
        "ts": start + np.array([r[0] for r in rows], dtype=np.int64).astype("timedelta64[s]"),
        "complainant_id": [r[1] for r in rows], "reported_wallet_id": [r[2] for r in rows],
        "category": [r[3] for r in rows], "related_txn_id": [r[4] for r in rows],
    })


TABLES = ["customers", "agents", "merchants", "billers", "transactions", "labels", "account_events", "complaints",
          "cases", "wallet_truth", "agent_truth"]


def write(out: dict, cfg: dict, csv: bool = False, sample: bool = True):
    d = resolve(cfg, "data_dir")
    for t in TABLES:
        out[t].to_parquet(d / f"{t}.parquet", index=False)
        if csv:
            out[t].to_csv(d / f"{t}.csv", index=False)
    save_json(out["planted"], d / "planted_scenarios.json")
    save_json(out["report"], d / "generation_report.json")
    if sample:
        write_sample(out, cfg)
    return d


def write_sample(out: dict, cfg: dict, days=(56, 57)):
    """Two consecutive test days (~20k rows at full scale) + all entity tables, as CSV."""
    sd = resolve(cfg, "sample_dir")
    start = pd.Timestamp(cfg["world"]["start_date"])
    lo, hi = start + pd.Timedelta(days=days[0] - 1), start + pd.Timedelta(days=days[1])
    tx = out["transactions"]
    m = (tx.ts >= lo) & (tx.ts < hi)
    tx[m].to_csv(sd / "transactions_sample.csv", index=False)
    out["labels"][m.values].to_csv(sd / "labels_sample.csv", index=False)
    ev = out["account_events"]
    ev[(ev.ts >= lo) & (ev.ts < hi)].to_csv(sd / "account_events_sample.csv", index=False)
    for t in ("customers", "agents", "merchants", "billers"):
        out[t].to_csv(sd / f"{t}.csv", index=False)
    save_json(out["planted"], sd / "planted_scenarios.json")


def load(cfg: dict) -> dict:
    d = resolve(cfg, "data_dir")
    out = {t: pd.read_parquet(d / f"{t}.parquet") for t in TABLES}
    import json
    with open(d / "planted_scenarios.json", encoding="utf-8") as f:
        out["planted"] = json.load(f)
    with open(d / "generation_report.json", encoding="utf-8") as f:
        out["report"] = json.load(f)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=None)
    ap.add_argument("--scale", type=float, default=None)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--out", default=None, help="override paths.data_dir")
    ap.add_argument("--csv", action="store_true")
    ap.add_argument("--no-sample", action="store_true")
    a = ap.parse_args()
    cfg = load_config(a.config, scale=a.scale, data_dir=a.out, seed=a.seed)
    out = build(cfg)
    d = write(out, cfg, csv=a.csv, sample=not a.no_sample)
    r = out["report"]
    print(f"[done] {r['n_transactions']:,} txns, fraud {r['fraud_rows']:,} ({100 * r['fraud_share']:.2f}%), "
          f"{r['seconds_total']}s -> {d}")
    print("        fraud rows by scenario:", r["fraud_rows_by_scenario"])


if __name__ == "__main__":
    main()
