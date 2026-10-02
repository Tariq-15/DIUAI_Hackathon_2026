"""Leakage guarantee: features of a transaction must not change when the future is deleted."""
import numpy as np
import pandas as pd

from src.features.build import replay
from src.features.store import FeatureStore, Win


def _truncate(data, cutoff):
    d = dict(data)
    d["transactions"] = data["transactions"][data["transactions"].ts < cutoff].reset_index(drop=True)
    d["account_events"] = data["account_events"][data["account_events"].ts < cutoff]
    d["complaints"] = data["complaints"][data["complaints"].ts < cutoff]
    return d


def test_no_future_leakage(tiny_data, tiny_cfg):
    full, _, _ = replay(tiny_data, tiny_cfg, verbose=False)
    cutoff = tiny_data["transactions"].ts.quantile(0.6)
    part, _, _ = replay(_truncate(tiny_data, cutoff), tiny_cfg, verbose=False)
    a = full.iloc[:len(part)].to_numpy()
    b = part.to_numpy()
    same = (a == b) | (np.isnan(a) & np.isnan(b))
    assert same.all(), f"{(~same).sum()} feature values changed when the future was removed"


def test_window_counts():
    w = Win(3600)
    w.add(0, "a", 10, True)
    w.add(100, "b", 5, False)
    w.add(200, "a", 1, False)
    w.trim(3650)                       # first item expires
    assert len(w.dq) == 2 and len(w.keys) == 2 and w.total == 6 and not w.fkeys


def test_first_time_pair_and_fan_in():
    st = FeatureStore(0, {"W1": -100 * 86400, "W2": -100 * 86400, "W3": -86400, "W9": -86400}, {}, {})
    names = __import__("src.features.store", fromlist=["STREAM_FEATURES"]).STREAM_FEATURES
    idx = {n: i for i, n in enumerate(names)}
    f, d = st.compute(1000, "SEND_MONEY", "W1", "C", "W9", "C", 500, 1000, 0, "D1", "APP", "A1", 2)
    assert f[idx["pair_first"]] == 1 and f[idx["cp_in_uniq_24h"]] == 0
    st.update(1000, "SEND_MONEY", "W1", "C", "W9", "C", 500, True, "D1", "APP", "A1", d)
    f, d = st.compute(2000, "SEND_MONEY", "W2", "C", "W9", "C", 500, 1000, 0, "D2", "APP", "A1", 2)
    assert f[idx["cp_in_uniq_24h"]] == 1 and f[idx["cp_in_new_24h"]] == 1
    st.update(2000, "SEND_MONEY", "W2", "C", "W9", "C", 500, True, "D2", "APP", "A1", d)
    f, _ = st.compute(3000, "SEND_MONEY", "W1", "C", "W9", "C", 500, 500, 1000, "D1", "APP", "A1", 2)
    assert f[idx["pair_first"]] == 0 and f[idx["cp_in_uniq_24h"]] == 2 and f[idx["is_new_device"]] == 0


def test_pass_through_depth():
    names = __import__("src.features.store", fromlist=["STREAM_FEATURES"]).STREAM_FEATURES
    idx = {n: i for i, n in enumerate(names)}
    st = FeatureStore(0, {w: -86400 for w in ("V", "M1", "M2")}, {}, {})
    hop = [("V", "M1"), ("M1", "M2")]
    t = 0
    for s, r in hop:
        t += 300
        f, d = st.compute(t, "SEND_MONEY", s, "C", r, "C", 10000, 10000, 0, "D", "APP", "A", 1)
        st.update(t, "SEND_MONEY", s, "C", r, "C", 10000, True, "D", "APP", "A", d)
    f, d = st.compute(t + 300, "CASH_OUT", "M2", "C", "AG", "A", 9500, 10000, np.nan, "D", "APP", "A", 1)
    assert f[idx["chain_depth"]] == 2 and f[idx["passthrough_ratio"]] > 1


def test_graph_features_present(tiny_features):
    s = tiny_features[tiny_features.scored]
    assert s["g_cp_in_deg"].notna().mean() > 0.95
