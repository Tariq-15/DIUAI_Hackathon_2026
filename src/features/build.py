"""Replay every transaction through the streaming feature store, add hourly graph features,
attach labels and splits.

    python -m src.features.build            # -> data/features/features.parquet
"""
from __future__ import annotations

import argparse
import time

import numpy as np
import pandas as pd

from src.common.config import load_config, resolve, save_json
from src.datagen.generate import load
from .graph import build_graph_features
from .spec import ALL_FEATURES, FEATURE_GROUPS
from .store import INCOMING, OUTGOING, SCORED_TYPES, STREAM_FEATURES, FeatureStore


def to_sec(ts: pd.Series, start: pd.Timestamp) -> np.ndarray:
    return ((ts - start).dt.total_seconds()).to_numpy().astype(np.int64)


def fraud_reports(complaints: pd.DataFrame) -> pd.DataFrame:
    """Only FRAUD reports count as evidence against a wallet; WRONG_SEND disputes are not accusations."""
    return complaints[complaints.category == "FRAUD"]


def make_store(data: dict, cfg: dict) -> FeatureStore:
    start = pd.Timestamp(cfg["world"]["start_date"])
    cust = data["customers"]
    signup = dict(zip(cust.wallet_id, to_sec(cust.signup_ts, start)))
    kyc = dict(zip(cust.wallet_id, np.where(cust.kyc_level == "KYC2", 2, 1)))
    onboard = dict(zip(data["agents"].agent_id, to_sec(data["agents"].onboard_ts, start)))
    onboard.update(zip(data["merchants"].merchant_id, to_sec(data["merchants"].onboard_ts, start)))
    return FeatureStore(0, signup, kyc, onboard, cfg["features"]["passthrough_window_min"])


def side_columns(tx: pd.DataFrame):
    typ = tx.txn_type.values
    st, rt = tx.sender_type.values, tx.receiver_type.values
    out = np.isin(typ, list(OUTGOING)) & (st == "C")
    inc = np.isin(typ, list(INCOMING)) & (rt == "C")
    cust = np.where(out, tx.sender_id.values, np.where(inc, tx.receiver_id.values, None))
    cp = np.where(out, tx.receiver_id.values, np.where(inc, tx.sender_id.values, tx.receiver_id.values))
    return cust, cp


def replay(data: dict, cfg: dict, store: FeatureStore | None = None, verbose=True):
    start = pd.Timestamp(cfg["world"]["start_date"])
    tx = data["transactions"]
    store = store or make_store(data, cfg)
    ts = to_sec(tx.ts, start)
    dow = tx.ts.dt.dayofweek.to_numpy()
    ev = data["account_events"].sort_values("ts", kind="stable")
    ev_t = to_sec(ev.ts, start).tolist()
    ev_w, ev_ty, ev_d = ev.wallet_id.tolist(), ev.event_type.tolist(), ev.device_id.tolist()
    cp_df = fraud_reports(data["complaints"]).sort_values("ts", kind="stable")
    cp_t = to_sec(cp_df.ts, start).tolist()
    cp_w = cp_df.reported_wallet_id.tolist()
    cols = [tx[c].tolist() for c in ("txn_type", "sender_id", "sender_type", "receiver_id", "receiver_type", "amount",
                                     "status", "sender_bal_before", "receiver_bal_before", "device_id", "channel",
                                     "area_id")]
    TY, SR, SK, DS, DK, AM, STt, SB, RB, DV, CH, AR = cols
    ts_l, dow_l = ts.tolist(), dow.tolist()
    n = len(ts_l)
    feats = [None] * n
    ei = ci = 0
    n_ev, n_cp = len(ev_t), len(cp_t)
    compute, update = store.compute, store.update
    apply_event, apply_complaint = store.apply_event, store.apply_complaint
    t0 = time.time()
    for i in range(n):
        t = ts_l[i]
        while ei < n_ev and ev_t[ei] <= t:
            apply_event(ev_t[ei], ev_w[ei], ev_ty[ei], ev_d[ei])
            ei += 1
        while ci < n_cp and cp_t[ci] < t:
            apply_complaint(cp_w[ci])
            ci += 1
        f, depth = compute(t, TY[i], SR[i], SK[i], DS[i], DK[i], AM[i], SB[i], RB[i], DV[i], CH[i], AR[i], dow_l[i])
        feats[i] = f
        update(t, TY[i], SR[i], SK[i], DS[i], DK[i], AM[i], STt[i] == "SUCCESS", DV[i], CH[i], AR[i], depth)
        if verbose and i and i % 100_000 == 0:
            print(f"   [replay] {i:,}/{n:,} rows ({time.time() - t0:.0f}s)", flush=True)
    F = pd.DataFrame(np.array(feats, dtype=np.float64), columns=STREAM_FEATURES, index=tx.index)
    return F, store, ts


def build(cfg: dict, data: dict | None = None, verbose=True) -> pd.DataFrame:
    log = (lambda *a: print(*a, flush=True)) if verbose else (lambda *a: None)
    data = data or load(cfg)
    start = pd.Timestamp(cfg["world"]["start_date"])
    tx = data["transactions"]
    t0 = time.time()
    F, store, ts = replay(data, cfg, verbose=verbose)
    log(f"[features] streaming replay: {len(F):,} rows x {F.shape[1]} features in {time.time() - t0:.0f}s")
    t1 = time.time()
    cust, cp = side_columns(tx)
    scored = tx.txn_type.isin(SCORED_TYPES).values
    cpl = fraud_reports(data["complaints"])
    G = build_graph_features(tx, cust, cp, ts, to_sec(cpl.ts, start), cpl.reported_wallet_id.values, scored,
                             verbose=verbose)
    log(f"[features] graph snapshots: {time.time() - t1:.0f}s")
    lab = data["labels"].set_index("txn_id").loc[tx.txn_id]
    meta = pd.DataFrame({
        "txn_id": tx.txn_id.values, "ts_sec": ts, "day": ts // 86400, "split": lab.split.values,
        "txn_type": tx.txn_type.values, "status": tx.status.values, "scored": scored,
        "is_fraud": lab.is_fraud.values.astype(np.int8), "scenario": lab.scenario.values,
        "case_id": lab.case_id.values, "fraud_role": lab.fraud_role.values,
        "sender_id": tx.sender_id.values, "receiver_id": tx.receiver_id.values,
        "cust_id": cust, "cp_id": cp, "device_id": tx.device_id.values,
    }, index=tx.index)
    out = pd.concat([meta, F, G], axis=1)
    out = out.loc[:, ~out.columns.duplicated()]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=None)
    ap.add_argument("--data", default=None)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    cfg = load_config(a.config, data_dir=a.data)
    if a.out:
        cfg["paths"]["features_dir"] = a.out
    df = build(cfg)
    d = resolve(cfg, "features_dir")
    df.to_parquet(d / "features.parquet", index=False)
    save_json(dict(groups=FEATURE_GROUPS, all_features=ALL_FEATURES), d / "feature_spec.json")
    s = df[df.scored]
    print(f"[done] {len(df):,} rows ({len(s):,} scored, fraud {int(s.is_fraud.sum()):,}) -> {d / 'features.parquet'}")


if __name__ == "__main__":
    main()
