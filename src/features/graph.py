"""Windowed transaction-graph features, rebuilt once per hour (never per transaction).

A transaction in hour H only sees the snapshot built from edges in [H-24h, H), so graph
features carry at most one hour of staleness and no future information.

Per node (sender-side customer and counterparty):
  in/out degree (unique counterparties, 24 h), PageRank x N, size of the node's weakly
  connected component in the FAST-FLOW subgraph (edges u->v where v moved >=50% of the money
  on within 2 h, as known at snapshot time), distinct wallets two hops upstream, and number
  of neighbours with a complaint already filed (16268).
"""
from __future__ import annotations

from collections import defaultdict

import numpy as np
import pandas as pd

try:                                   # optional at serve time: the in-browser build keeps the start-up snapshot
    import networkx as nx
except ImportError:                    # pragma: no cover
    nx = None

DAY, HOUR = 86_400, 3_600
GRAPH_FEATURES = ["g_cust_in_deg", "g_cust_out_deg", "g_cust_pagerank", "g_cust_ff_comp", "g_cust_nbr_complained",
                  "g_cp_in_deg", "g_cp_out_deg", "g_cp_pagerank", "g_cp_ff_comp", "g_cp_two_hop_in",
                  "g_cp_nbr_complained"]


def forward_times(src, dst, ts, amt, is_p2p):
    """For each P2P edge u->v at t: first time v's cumulative outflow after t reaches 50% of the
    amount within 2 h (inf if never)."""
    out_by = defaultdict(list)
    for i in range(len(src)):
        out_by[src[i]].append(i)
    fwd = np.full(len(src), np.inf)
    for i in np.flatnonzero(is_p2p):
        lst = out_by.get(dst[i])
        if not lst:
            continue
        t = ts[i]
        pos = _bisect_ts(lst, ts, t)
        need = 0.5 * amt[i]
        cum = 0.0
        for j in lst[pos:]:
            if ts[j] > t + 2 * HOUR:
                break
            cum += amt[j]
            if cum >= need:
                fwd[i] = ts[j]
                break
    return fwd


def _bisect_ts(lst, ts, t):
    lo, hi = 0, len(lst)
    while lo < hi:
        mid = (lo + hi) // 2
        if ts[lst[mid]] <= t:
            lo = mid + 1
        else:
            hi = mid
    return lo


def build_graph_features(tx: pd.DataFrame, cust_col: np.ndarray, cp_col: np.ndarray, ts_sec: np.ndarray,
                         complaints_sec: np.ndarray, complaint_wallets: np.ndarray, query_mask: np.ndarray,
                         verbose=True) -> pd.DataFrame:
    """tx sorted by time. cust_col/cp_col: customer-side wallet and counterparty per row."""
    ok = (tx.status.values == "SUCCESS")
    typ = tx.txn_type.values
    e_mask = ok & (((typ == "SEND_MONEY") & (tx.receiver_type.values == "C")) | (typ == "CASH_OUT")) & \
        (tx.sender_type.values == "C")
    e_src = tx.sender_id.values[e_mask]
    e_dst = tx.receiver_id.values[e_mask]
    e_ts = ts_sec[e_mask]
    e_amt = tx.amount.values[e_mask]
    e_p2p = typ[e_mask] == "SEND_MONEY"
    fwd = forward_times(e_src, e_dst, e_ts, e_amt, e_p2p)
    n_hours = int(ts_sec.max() // HOUR) + 1     # for progress messages
    q_idx = np.flatnonzero(query_mask)
    q_hour = ts_sec[q_idx] // HOUR
    order = np.argsort(q_hour, kind="stable")
    q_idx, q_hour = q_idx[order], q_hour[order]
    out = np.full((len(tx), len(GRAPH_FEATURES)), np.nan)
    c_order = np.argsort(complaints_sec, kind="stable")
    c_sec, c_w = complaints_sec[c_order], complaint_wallets[c_order]
    complained: set = set()
    ci = 0
    lo = hi = 0
    qp = 0
    n_e = len(e_ts)
    for H in np.unique(q_hour):
        t_end = int(H) * HOUR
        t_start = t_end - DAY
        while hi < n_e and e_ts[hi] < t_end:
            hi += 1
        while lo < hi and e_ts[lo] < t_start:
            lo += 1
        while ci < len(c_sec) and c_sec[ci] < t_end:
            complained.add(c_w[ci])
            ci += 1
        rows = []
        while qp < len(q_idx) and q_hour[qp] == H:
            rows.append(q_idx[qp])
            qp += 1
        if not rows:
            continue
        G = nx.DiGraph()
        G.add_edges_from(zip(e_src[lo:hi], e_dst[lo:hi]))
        nN = max(G.number_of_nodes(), 1)
        pr = nx.pagerank(G, tol=1e-4, max_iter=60) if G.number_of_edges() else {}
        ffm = (fwd[lo:hi] < t_end) & e_p2p[lo:hi]
        F = nx.Graph()
        F.add_edges_from(zip(e_src[lo:hi][ffm], e_dst[lo:hi][ffm]))
        comp = {}
        for cc in nx.connected_components(F):
            size = len(cc)
            for v in cc:
                comp[v] = size
        cache = {}

        def node_feats(v):
            r = cache.get(v)
            if r is not None:
                return r
            if v in G:
                preds = set(G.predecessors(v))
                succs = set(G.successors(v))
                two = set()
                for p in preds:
                    two.update(G.predecessors(p))
                two.discard(v)
                nbr_c = sum(1 for x in preds | succs if x in complained)
                r = (len(preds), len(succs), pr.get(v, 0.0) * nN, comp.get(v, 1), len(two), nbr_c)
            else:
                r = (0, 0, 0.0, 1, 0, 0)
            cache[v] = r
            return r
        for i in rows:
            cu, cp = cust_col[i], cp_col[i]
            a = node_feats(cu) if cu else (np.nan,) * 6
            b = node_feats(cp) if cp else (np.nan,) * 6
            out[i] = (a[0], a[1], a[2], a[3], a[5], b[0], b[1], b[2], b[3], b[4], b[5])
        if verbose and int(H) % 240 == 0:
            print(f"   [graph] hour {H}/{n_hours}: window edges={hi - lo:,} nodes={G.number_of_nodes():,}", flush=True)
    return pd.DataFrame(out, columns=GRAPH_FEATURES, index=tx.index)


def graph_snapshot(tx: pd.DataFrame, ts: np.ndarray, complaints: pd.DataFrame, start=None) -> dict:
    """Node stats of the last-24 h graph (the same snapshot the model is trained with), for serving."""
    end = int(ts.max()) + 1
    m = (tx.status.values == "SUCCESS") & (tx.sender_type.values == "C") & (ts >= end - 86_400) & \
        (((tx.txn_type.values == "SEND_MONEY") & (tx.receiver_type.values == "C")) | (tx.txn_type.values == "CASH_OUT"))
    src, dst = tx.sender_id.values[m], tx.receiver_id.values[m]
    e_ts, amt = ts[m], tx.amount.values[m]
    p2p = tx.txn_type.values[m] == "SEND_MONEY"
    fwd = forward_times(src, dst, e_ts, amt, p2p)
    G = nx.DiGraph()
    G.add_edges_from(zip(src, dst))
    pr = nx.pagerank(G, tol=1e-4, max_iter=60) if G.number_of_edges() else {}
    F = nx.Graph()
    ff = (fwd < end) & p2p
    F.add_edges_from(zip(src[ff], dst[ff]))
    comp = {v: len(cc) for cc in nx.connected_components(F) for v in cc}
    complained = set(complaints.reported_wallet_id)
    nN = max(G.number_of_nodes(), 1)
    nodes = {}
    for v in G.nodes:
        preds, succs = set(G.predecessors(v)), set(G.successors(v))
        two = set()
        for p in preds:
            two.update(G.predecessors(p))
        two.discard(v)
        nodes[v] = (len(preds), len(succs), pr.get(v, 0.0) * nN, comp.get(v, 1), len(two),
                    sum(1 for x in preds | succs if x in complained))
    return dict(nodes=nodes, built_at=end)
