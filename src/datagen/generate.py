"""
src/datagen/generate.py
========================
Main orchestrator ? run with:

    python -m src.datagen.generate

or:

    python -m src.datagen.generate --config config.yaml --out data/ --sample 20000

Modules called in order:
  1. config_loader    -> cfg
  2. builders         -> customers, agents, profiles
  3. simulate_normal_life  -> normal transaction rows
  4. inject_s1?s7    -> fraud transaction + label rows
  5. plant_scenarios  -> showcase scenario rows + labels
  6. enforce_balances -> sort + ledger checks + benign look-alike injection
  7. write_files      -> CSVs (transactions.csv, labels.csv, customers.csv, agents.csv)
  8. run_tests        -> T1?T14 acceptance tests
"""
from __future__ import annotations

import argparse
import itertools
import os
import sys
import time
from datetime import datetime

import numpy as np
import pandas as pd

# ?? local imports (works when running as -m src.datagen.generate) ?????????????
HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.datagen.config_loader   import load_config
from src.datagen.builders        import build_customers, build_agents, build_profiles
from src.datagen.normal_life     import simulate_normal_life
from src.datagen.fraud_injectors import (inject_s1, inject_s2, inject_s3,
                                          inject_s4, inject_s5, inject_s6, inject_s7)
from src.datagen.scenarios       import plant_scenarios
from src.datagen.tests           import run_tests


# ?? Argument parsing ??????????????????????????????????????????????????????????

def _parse_args():
    p = argparse.ArgumentParser(description="Prohori synthetic MFS dataset generator")
    p.add_argument("--config", default=os.path.join(PROJECT_ROOT, "config.yaml"),
                   help="Path to config.yaml")
    p.add_argument("--out",    default=os.path.join(PROJECT_ROOT, "data"),
                   help="Output directory for CSVs")
    p.add_argument("--sample", type=int, default=20000,
                   help="Row count for sample CSV (for GitHub)")
    p.add_argument("--no-tests", action="store_true",
                   help="Skip T1-T14 acceptance tests")
    p.add_argument("--parquet", action="store_true",
                   help="Also write Parquet files (requires pyarrow or fastparquet)")
    return p.parse_args()


# ?? Module 6: enforce_balances ????????????????????????????????????????????????

def enforce_balances(
    all_txn_rows: list,
    all_label_rows: list,
    cfg,
    rng: np.random.Generator,
    profiles: dict,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    1. Convert raw lists to DataFrames.
    2. Sort by timestamp.
    3. Deduplicate txn_id.
    4. Inject benign look-alike rows to reach 1.5? fraud count.
    5. Return (transactions_df, labels_df).
    """
    t0 = time.time()
    print("\n[BUILD]  enforce_balances: building DataFrames?")

    txn_df = pd.DataFrame(all_txn_rows)
    lbl_df = pd.DataFrame(all_label_rows)

    # Deduplicate
    txn_df = txn_df.drop_duplicates(subset="txn_id")
    lbl_df = lbl_df.drop_duplicates(subset="txn_id")

    # Sort by timestamp
    txn_df["timestamp"] = pd.to_datetime(txn_df["timestamp"])
    txn_df = txn_df.sort_values("timestamp").reset_index(drop=True)

    # Fill NaN in label defaults
    lbl_df["is_fraud"]          = lbl_df["is_fraud"].fillna(0).astype(int)
    lbl_df["is_benign_lookalike"] = lbl_df.get("is_benign_lookalike", pd.Series(0)).fillna(0).astype(int)

    # ?? Benign look-alike injection ???????????????????????????????????????????
    # Target: 1.5? the number of fraud rows; add as labelled benign cases
    n_fraud_rows   = lbl_df["is_fraud"].sum()
    n_benign_exist = lbl_df["is_benign_lookalike"].sum()
    n_benign_need  = max(0, int(n_fraud_rows * cfg.benign_lookalike_multiplier) - n_benign_exist)

    print(f"   Fraud rows: {n_fraud_rows:,} | Benign look-alikes needed: {n_benign_need:,}")

    if n_benign_need > 0:
        # Pick random normal P2P rows that look like fraud (high amount, first-time)
        normal_ids = set(lbl_df[lbl_df["is_fraud"] == 0]["txn_id"].tolist()) - \
                     set(lbl_df[lbl_df["is_benign_lookalike"] == 1]["txn_id"].tolist())

        # Mark the top n_benign_need by amount ? counterparty_first_time
        normal_txns = txn_df[
            txn_df["txn_id"].isin(normal_ids) &
            (txn_df["txn_type"] == "P2P_SEND") &
            (txn_df["counterparty_first_time"] == 1) &
            (txn_df["amount_tk"] > 3000)
        ].copy()

        if len(normal_txns) > 0:
            sample_n  = min(n_benign_need, len(normal_txns))
            benign_sample = normal_txns.nlargest(sample_n, "amount_tk")

            benign_tids = set(benign_sample["txn_id"].tolist())
            mask = lbl_df["txn_id"].isin(benign_tids)
            lbl_df.loc[mask, "is_benign_lookalike"] = 1
            lbl_df.loc[mask, "expected_band"]       = "ALLOW"

    print(f"   [OK] enforce_balances done in {time.time()-t0:.1f}s")
    return txn_df, lbl_df


# ?? Module 7: write_files ?????????????????????????????????????????????????????

def write_files(
    txn_df: pd.DataFrame,
    lbl_df: pd.DataFrame,
    customers: pd.DataFrame,
    agents: pd.DataFrame,
    out_dir: str,
    sample_n: int = 20000,
    write_parquet: bool = False,
):
    """Write all output files. labels.csv kept separate (no leakage)."""
    os.makedirs(out_dir, exist_ok=True)
    sample_dir = os.path.join(out_dir, "sample")
    os.makedirs(sample_dir, exist_ok=True)

    t0 = time.time()
    print("\n[SAVE] write_files: writing CSVs?")

    # ?? Guard: transactions.csv must NOT contain label columns ????????????????
    label_col_set = {"is_fraud", "fraud_class", "fraud_role", "case_id",
                     "scenario_id", "is_benign_lookalike", "expected_band"}
    for col in label_col_set:
        if col in txn_df.columns:
            txn_df = txn_df.drop(columns=[col])

    # ?? Write full files ??????????????????????????????????????????????????????
    files = {
        "customers.csv":    customers,
        "agents.csv":       agents,
        "transactions.csv": txn_df,
        "labels.csv":       lbl_df,
    }
    for fname, df in files.items():
        path = os.path.join(out_dir, fname)
        df.to_csv(path, index=False)
        mb = os.path.getsize(path) / 1e6
        print(f"   {fname}: {len(df):,} rows  {mb:.1f} MB -> {path}")

    # ?? Write sample (20k rows) ???????????????????????????????????????????????
    # Stratified: keep all fraud + scenario rows, fill rest with normal
    fraud_ids     = set(lbl_df[lbl_df["is_fraud"] == 1]["txn_id"].tolist())
    scenario_ids  = set(lbl_df[lbl_df["scenario_id"].notna()]["txn_id"].tolist())
    special_ids   = fraud_ids | scenario_ids

    special_txns  = txn_df[txn_df["txn_id"].isin(special_ids)]
    normal_txns   = txn_df[~txn_df["txn_id"].isin(special_ids)]
    n_fill = max(0, sample_n - len(special_txns))
    normal_sample = normal_txns.sample(n=min(n_fill, len(normal_txns)), random_state=42)

    sample_txn = pd.concat([special_txns, normal_sample]).sort_values("timestamp")
    sample_lbl = lbl_df[lbl_df["txn_id"].isin(sample_txn["txn_id"])]

    sample_txn.to_csv(os.path.join(sample_dir, "transactions_sample.csv"), index=False)
    sample_lbl.to_csv(os.path.join(sample_dir, "labels_sample.csv"),       index=False)
    customers.to_csv( os.path.join(sample_dir, "customers.csv"),            index=False)
    agents.to_csv(    os.path.join(sample_dir, "agents.csv"),               index=False)
    print(f"   sample/transactions_sample.csv: {len(sample_txn):,} rows")

    # ?? Optional Parquet ??????????????????????????????????????????????????????
    if write_parquet:
        try:
            txn_df.to_parquet(os.path.join(out_dir, "transactions.parquet"), index=False)
            lbl_df.to_parquet(os.path.join(out_dir, "labels.parquet"),       index=False)
            print("   Parquet files written.")
        except Exception as e:
            print(f"   Parquet skipped: {e}")

    print(f"   [OK] write_files done in {time.time()-t0:.1f}s")


# ?? Summary report ????????????????????????????????????????????????????????????

def _print_summary(txn_df: pd.DataFrame, lbl_df: pd.DataFrame, cfg):
    print("\n" + "="*60)
    print("DATASET SUMMARY REPORT")
    print("="*60)
    print(f"Total transactions : {len(txn_df):,}")
    print(f"Fraud rows         : {lbl_df['is_fraud'].sum():,} ({lbl_df['is_fraud'].sum() / len(lbl_df):.3%})")
    print(f"Benign look-alikes : {lbl_df['is_benign_lookalike'].sum():,}")

    print("\nFraud class distribution:")
    cls_counts = lbl_df[lbl_df["is_fraud"] == 1]["fraud_class"].value_counts()
    for cls, cnt in cls_counts.items():
        pct = cnt / lbl_df["is_fraud"].sum() * 100
        print(f"  {cls}: {cnt:,}  ({pct:.1f}%)")

    print("\nTransaction type distribution:")
    tc = txn_df["txn_type"].value_counts()
    for tt, cnt in tc.items():
        print(f"  {tt}: {cnt:,}")

    print("\nAmount histogram (P2P normal, Tk):")
    p2p = txn_df[txn_df["txn_type"] == "P2P_SEND"]["amount_tk"]
    fraud_ids = set(lbl_df[lbl_df["is_fraud"] == 1]["txn_id"])
    p2p_normal = txn_df[
        (txn_df["txn_type"] == "P2P_SEND") &
        (~txn_df["txn_id"].isin(fraud_ids))
    ]["amount_tk"]
    bins = [0, 500, 1000, 2000, 5000, 10000, 25000, 50000, float("inf")]
    labels_h = ["<500", "500-1k", "1k-2k", "2k-5k", "5k-10k", "10k-25k", "25k-50k", "50k+"]
    counts, _ = np.histogram(p2p_normal, bins=bins)
    for lh, cnt in zip(labels_h, counts):
        bar = "?" * min(int(cnt / max(counts) * 40), 40)
        print(f"  {lh:>10}: {bar} {cnt:,}")

    print("\nScenario coverage:")
    sc_ids = lbl_df[lbl_df["scenario_id"].notna()]["scenario_id"].unique()
    for sid in sorted(sc_ids):
        print(f"  {sid}: {(lbl_df['scenario_id'] == sid).sum()} rows")

    print("="*60)


# ?? Main ??????????????????????????????????????????????????????????????????????

def main():
    args = _parse_args()
    t_start = time.time()

    print("[START] Prohori Dataset Generator")
    print(f"   Config : {args.config}")
    print(f"   Output : {args.out}")
    print(f"   Sample : {args.sample:,} rows")
    print()

    # ?? 1. Load config ????????????????????????????????????????????????????????
    cfg = load_config(args.config)
    rng = np.random.default_rng(cfg.seed)
    sim_start = cfg.sim_start_dt
    sim_end   = cfg.sim_end_dt
    print(f"   Window : {sim_start.date()} -> {sim_end.date()}  ({cfg.sim_days} days)")

    # Shared counter (monotonic, never reset)
    counter = itertools.count(1)

    # ?? 2. Build customers, agents, profiles ??????????????????????????????????
    print("\n[LOG] Building customers & agents?")
    customers = build_customers(cfg, rng)
    agents    = build_agents(cfg, rng, customers)
    profiles  = build_profiles(cfg, rng, customers, customers["customer_id"].tolist())
    print(f"   Customers: {len(customers):,} | Agents: {len(agents):,}")

    # ?? 3. Simulate normal life ???????????????????????????????????????????????
    print("\n[CITY]  Simulating normal life?")
    target_normal = int(cfg.target_txn_rows * (1 - cfg.fraud_rate) * 0.95)
    t3 = time.time()
    normal_txns = simulate_normal_life(
        cfg, rng, customers, agents, profiles, counter, target_normal
    )
    print(f"   {len(normal_txns):,} normal rows in {time.time()-t3:.1f}s")

    # All label rows for normal txns (is_fraud=0)
    normal_labels = [dict(txn_id=t["txn_id"], is_fraud=0, fraud_class=None,
                          fraud_role=None, case_id=None, scenario_id=None,
                          is_benign_lookalike=0, expected_band="ALLOW")
                     for t in normal_txns]

    # ?? 4. Inject fraud classes ???????????????????????????????????????????????
    print("\n[FRAUD] Injecting fraud (S1?S7)?")
    all_fraud_txns: list  = []
    all_fraud_lbls: list  = []

    s1_t, s1_l = inject_s1(cfg, rng, customers, profiles, counter, sim_start, sim_end)
    s2_t, s2_l = inject_s2(cfg, rng, customers, profiles, counter, sim_start, sim_end)
    s3_t, s3_l = inject_s3(cfg, rng, customers, profiles, counter, sim_start, sim_end)
    s4_t, s4_l = inject_s4(cfg, rng, customers, profiles, counter, sim_start, sim_end)

    # Collect fraud wallet IDs for S5
    fraud_wallet_ids = []
    for lrow in s1_l + s2_l + s3_l + s4_l:
        if lrow.get("is_fraud") and lrow.get("fraud_role") in ("cashout",):
            # Get the sender from the txn dict (match by txn_id)
            pass   # we'll pull from txn dicts below

    s1_s4_txns = s1_t + s2_t + s3_t + s4_t
    fraud_wallet_ids = list({
        t["sender_id"] for t in s1_s4_txns
        if str(t["sender_id"]).startswith("W-")
    })

    s5_t, s5_l = inject_s5(cfg, rng, customers, agents, profiles, counter,
                            sim_start, sim_end, fraud_wallet_ids)
    s6_t, s6_l = inject_s6(cfg, rng, customers, profiles, counter, sim_start, sim_end)
    s7_t, s7_l = inject_s7(cfg, rng, customers, profiles, counter, sim_start, sim_end)

    for t, l in [(s1_t, s1_l), (s2_t, s2_l), (s3_t, s3_l), (s4_t, s4_l),
                 (s5_t, s5_l), (s6_t, s6_l), (s7_t, s7_l)]:
        all_fraud_txns.extend(t)
        all_fraud_lbls.extend(l)

    fraud_counts = {
        "S1": sum(1 for l in s1_l if l["is_fraud"]),
        "S2": sum(1 for l in s2_l if l["is_fraud"]),
        "S3": sum(1 for l in s3_l if l["is_fraud"]),
        "S4": sum(1 for l in s4_l if l["is_fraud"]),
        "S5": sum(1 for l in s5_l if l["is_fraud"]),
        "S6": sum(1 for l in s6_l if l["is_fraud"]),
        "S7": sum(1 for l in s7_l if l["is_fraud"]),
    }
    print(f"   Fraud row counts: {fraud_counts}")

    # ?? 5. Plant showcase scenarios ???????????????????????????????????????????
    print("\n[SCENARIO] Planting showcase scenarios (SC-01..SC-10, SB-01..SB-08)?")
    sc_txns, sc_lbls = plant_scenarios(cfg, counter, profiles, sim_start, rng)
    print(f"   {len(sc_txns):,} scenario rows planted")

    # ?? 6. Combine + enforce balances ?????????????????????????????????????????
    all_txn_rows = normal_txns + all_fraud_txns + sc_txns
    all_lbl_rows = normal_labels + all_fraud_lbls + sc_lbls

    txn_df, lbl_df = enforce_balances(all_txn_rows, all_lbl_rows, cfg, rng, profiles)

    print(f"\n   Final dataset: {len(txn_df):,} transactions")

    # ?? 7. Write files ????????????????????????????????????????????????????????
    write_files(txn_df, lbl_df, customers, agents,
                out_dir=args.out,
                sample_n=args.sample,
                write_parquet=args.parquet)

    # ?? Summary report ????????????????????????????????????????????????????????
    _print_summary(txn_df, lbl_df, cfg)

    # ?? 8. Run acceptance tests ???????????????????????????????????????????????
    if not args.no_tests:
        print("\n[TEST] Running acceptance tests T1?T14?")
        docs_dir = os.path.join(PROJECT_ROOT, "docs")
        all_passed = run_tests(
            txn_df, lbl_df, cfg,
            sim_start=sim_start,
            sim_end=sim_end + __import__("datetime").timedelta(hours=23),
            output_file=os.path.join(docs_dir, "data_validation.txt"),
        )
        if not all_passed:
            print("\n[WARN]  Some tests failed. Review docs/data_validation.txt")
    else:
        print("\n[WARN]  Tests skipped (--no-tests)")

    print(f"\n[OK] Generation complete in {time.time()-t_start:.1f}s")
    print(f"   Data -> {args.out}/")
    print(f"   Sample (git-safe) -> {args.out}/sample/")


if __name__ == "__main__":
    main()
