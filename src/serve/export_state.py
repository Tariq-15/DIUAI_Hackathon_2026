"""Export what the live API needs, and nothing else (Render free tier = 512 MB RAM).

    python -m src.serve.export_state      # -> artifacts/demo_state.joblib

Contents: the streaming feature store replayed to the end of the window (windows auto-trim),
the last 24 h graph snapshot (node stats), last known balances, planted demo results.
The 600k-row dataset itself is NOT shipped.
"""
from __future__ import annotations

import argparse
import json

import joblib
import networkx as nx
import numpy as np
import pandas as pd

from src.common.config import DAY, load_config, resolve
from src.datagen.generate import load
from src.features.build import replay, to_sec
from src.features.graph import graph_snapshot


def export(cfg, verbose=True):
    data = load(cfg)
    start = pd.Timestamp(cfg["world"]["start_date"])
    _, store, ts = replay(data, cfg, verbose=False)
    tx = data["transactions"]
    snap = graph_snapshot(tx, ts, data["complaints"][data["complaints"].category == "FRAUD"], start)
    # last known balance = the balance after the final row each wallet appears in (either side)
    long = pd.concat([tx[["txn_id", "sender_id", "sender_bal_after"]].set_axis(["txn_id", "w", "b"], axis=1),
                      tx[["txn_id", "receiver_id", "receiver_bal_after"]].set_axis(["txn_id", "w", "b"], axis=1)])
    long = long.dropna().sort_values("txn_id").drop_duplicates("w", keep="last")
    bal = dict(zip(long.w, long.b.astype(float)))
    rep = resolve(cfg, "reports_dir")
    metrics = json.loads((rep / "metrics_test.json").read_text(encoding="utf-8")) if (rep / "metrics_test.json").exists() else {}
    agents = json.loads((rep / "agent_watch.json").read_text(encoding="utf-8")) if (rep / "agent_watch.json").exists() else {}
    cust = data["customers"]
    state = dict(store=store, graph=snap, balances=bal, now_sec=int(ts.max()), start=str(start.date()),
                 msisdn={m: w for m, w in zip(cust.msisdn, cust.wallet_id)},
                 demo=metrics.get("demo_scenarios", []), agent_watch=agents,
                 metrics=dict(comparison=metrics.get("comparison"), bands=metrics.get("bands"),
                              impact=metrics.get("impact"), friction=metrics.get("friction")))
    path = resolve(cfg, "artifacts_dir") / "demo_state.joblib"
    joblib.dump(state, path, compress=3)
    export_serve_bundle(cfg, verbose)
    if verbose:
        print(f"[export] {len(store.w):,} wallets, {len(snap['nodes']):,} graph nodes -> {path} "
              f"({path.stat().st_size / 1e6:.1f} MB)")
    return path


SERVE_DROP = ("xgb", "logit")        # comparison models for the evaluation only; the live policy never uses them


def export_serve_bundle(cfg, verbose=True):
    """artifacts/serve_bundle.joblib: the model bundle without the comparison models, so the API image needs no
    XGBoost (a large install) and loads faster. Scores are identical: the policy uses LightGBM, the Isolation
    Forest, the graph rules, the calibrator and the band mapper only."""
    art = resolve(cfg, "artifacts_dir")
    bundle = joblib.load(art / "model_bundle.joblib")
    path = art / "serve_bundle.joblib"
    joblib.dump({k: v for k, v in bundle.items() if k not in SERVE_DROP}, path, compress=3)
    if verbose:
        print(f"[export] serving bundle -> {path} ({path.stat().st_size / 1e6:.1f} MB)")
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=None)
    export(load_config(ap.parse_args().config))


if __name__ == "__main__":
    main()
