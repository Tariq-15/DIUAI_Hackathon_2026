"""Build the small demo world the product layer needs (customer app + analyst copilot).

    python -m src.serve.demo_world      # -> artifacts/demo_world.joblib (a few MB)

Contents, all derived from the generated data and the saved bundle (nothing hand-written):
  - recent edges (last 2 days) so the live engine can rebuild the 24 h graph snapshot and draw networks
  - historical alerts: the planted test-window scenarios and the final test day's STEP_UP/HOLD alerts,
    each re-scored by the bundle, with SHAP evidence and the money network around it
  - two demo customers for the phone app (chosen by rule, not by hand), Agent Watch series, fairness table
The live engine (src/serve/live.py) stages its own scenarios on top of this at start-up.
"""
from __future__ import annotations

import argparse
import json

import joblib
import numpy as np
import pandas as pd

from src.common.config import DAY, load_config, resolve
from src.datagen.generate import load
from src.features.build import to_sec
from src.models.explain import explainer, reasons_for, shap_matrix
from src.models.scoring import X_of, load_bundle, score_frame

HOUR = 3_600
EDGE_TYPES = ("SEND_MONEY", "CASH_OUT", "PAYMENT", "CASH_IN")
NETWORK_EDGES = 40


def _kind(acct: str) -> str:
    return {"W": "customer", "A": "agent", "M": "merchant", "B": "biller"}.get(str(acct)[:1], "other")


def pick_personas(data: dict, state: dict) -> dict:
    """Rahim: a garment worker who regularly sends to one family wallet. Salma: a small-business owner with a
    high balance (the SIM-swap target). Picked by rule so a new seed still yields sensible demo customers."""
    store, bal = state["store"], state["balances"]
    cust = data["customers"].set_index("wallet_id")
    out = {}
    for key, seg, gender, min_top in (("rahim", "garment_worker", "M", 10), ("salma", "small_business", "F", 10)):
        best = None
        for w, s in store.w.items():
            if w not in cust.index or not s.sent_to or s.n_out < 20 or len(s.devices) != 1:
                continue
            r = cust.loc[w]
            if r.segment != seg or r.gender != gender or r.kyc_level != "KYC2" or r.channel != "APP":
                continue
            top, n = max(s.sent_to.items(), key=lambda kv: kv[1])
            if not str(top).startswith("W") or n < min_top:
                continue
            cand = (bal.get(w, 0.0), w)
            if best is None or cand > best:
                best = cand
        if best is None:
            continue
        w = best[1]
        s, r = store.w[w], cust.loc[w]
        contacts = sorted(((k, n) for k, n in s.sent_to.items() if str(k).startswith("W") and k in cust.index),
                          key=lambda kv: -kv[1])[:4]
        out[key] = dict(wallet=w, msisdn=str(r.msisdn), segment=r.segment, gender=r.gender, age_band=r.age_band,
                        area_id=r.area_id, division=r.division, kyc=r.kyc_level, device=s.last_device,
                        balance=round(float(bal.get(w, 0.0)), 2), typical_amount=int(round(np.exp(s.s_log / s.n_out), -1)),
                        contacts=[dict(wallet=k, msisdn=str(cust.loc[k].msisdn), sent_before=int(n)) for k, n in contacts])
    return out


def network_around(tx: pd.DataFrame, ts: np.ndarray, sender: str, receiver: str, t: int, key_txn: str | None,
                   roles: dict | None = None) -> dict:
    """The money around one transaction: who paid the receiver in the 24 h before, where its money went next
    (two hops, up to 3 h after), and what the sender moved in the 2 h around it."""
    lo, hi = t - DAY, t + 3 * HOUR
    m = (ts >= lo) & (ts <= hi) & (tx.status.values == "SUCCESS") & np.isin(tx.txn_type.values, EDGE_TYPES)
    w = tx[m].assign(tsec=ts[m])
    into_r = w[w.receiver_id == receiver]
    out_r = w[w.sender_id == receiver]
    hop2 = w[w.sender_id.isin(set(out_r.receiver_id) - {receiver}) & (w.tsec >= t - 2 * HOUR)]
    by_s = w[((w.sender_id == sender) | (w.receiver_id == sender)) & (w.tsec >= t - 2 * HOUR) & (w.tsec <= t + 2 * HOUR)]
    if roles:
        planted = set(roles)
        extra = w[(w.sender_id.isin(planted) | w.receiver_id.isin(planted)) & (w.tsec >= t - 6 * HOUR)]
    else:
        extra = w.iloc[:0]
    e = pd.concat([into_r, out_r, hop2, by_s, extra]).drop_duplicates("txn_id")
    if key_txn is not None and key_txn not in set(e.txn_id):
        e = pd.concat([e, tx[tx.txn_id == key_txn].assign(tsec=t)])
    keep = e[e.txn_id == key_txn] if key_txn else e.iloc[:0]
    rest = e[e.txn_id != key_txn].sort_values("amount", ascending=False).head(NETWORK_EDGES - len(keep))
    e = pd.concat([keep, rest]).sort_values("tsec")
    edges = [dict(id=r.txn_id, source=r.sender_id, target=r.receiver_id, amount=float(r.amount), type=r.txn_type,
                  ts=int(r.tsec), key=bool(r.txn_id == key_txn)) for r in e.itertuples()]
    return dict(edges=edges, roles=roles or {})


def build(cfg: dict, verbose=True) -> dict:
    data = load(cfg)
    start = pd.Timestamp(cfg["world"]["start_date"])
    tx = data["transactions"]
    ts = to_sec(tx.ts, start)
    state = joblib.load(resolve(cfg, "artifacts_dir") / "demo_state.joblib")
    bundle = load_bundle(cfg)
    expl = explainer(bundle)
    end = int(ts.max())

    # ---------------- recent edges for the live graph (last 2 days, successful money movements)
    m = (ts >= end - 2 * DAY) & (tx.status.values == "SUCCESS") & np.isin(tx.txn_type.values, EDGE_TYPES)
    edges = pd.DataFrame({"ts": ts[m], "txn_id": tx.txn_id.values[m], "src": tx.sender_id.values[m], "dst": tx.receiver_id.values[m],
                          "amount": tx.amount.values[m], "type": tx.txn_type.values[m],
                          "src_kind": tx.sender_type.values[m], "dst_kind": tx.receiver_type.values[m]})
    complained = sorted(set(data["complaints"].loc[data["complaints"].category == "FRAUD", "reported_wallet_id"]))

    # ---------------- historical alerts: planted scenarios + the last test day's STEP_UP / HOLD
    feats = pd.read_parquet(resolve(cfg, "features_dir") / "features.parquet")
    feats = feats[feats.scored]
    planted = {p["key_txn_id"]: p for p in data["planted"] if p.get("key_txn_id")}
    last_day = feats[feats.day == feats.day.max()]
    s_last = score_frame(bundle, last_day)
    flagged = last_day[s_last.band.isin(["STEP_UP", "HOLD"]).values].assign(_score=s_last.risk_score[s_last.band.isin(["STEP_UP", "HOLD"])].values)
    fraud = flagged[flagged.is_fraud == 1].sort_values("_score", ascending=False)
    picks = list(fraud.groupby("scenario").head(2).head(10).txn_id)
    picks += list(flagged[flagged.is_fraud == 0].sort_values("_score", ascending=False).head(3).txn_id)   # honest: false alarms too
    ids = list(dict.fromkeys(list(planted) + picks))
    rows = feats[feats.txn_id.isin(ids)].set_index("txn_id").loc[[i for i in ids if i in set(feats.txn_id)]].reset_index()
    sc = score_frame(bundle, rows)
    X = X_of(rows, bundle["features"])
    sv = shap_matrix(expl, X)
    tx_by_id = tx.set_index("txn_id")
    alerts = []
    for i, r in rows.iterrows():
        s = sc.iloc[i]
        p = planted.get(r.txn_id)
        if p is None and s.band == "ALLOW":
            continue
        row = {k: (None if isinstance(v, float) and np.isnan(v) else v) for k, v in r.items()}
        srow = dict(zip(bundle["features"], sv[i]))
        reasons = reasons_for({k: (np.nan if v is None else v) for k, v in row.items()}, srow,
                              dict(graph=s.graph, anomaly=s.anomaly))
        top = sorted(srow.items(), key=lambda kv: -abs(kv[1]))[:10]
        t = tx_by_id.loc[r.txn_id]
        roles = {w: role for role, w in (p or {}).get("wallets", {}).items()}
        if p and p.get("agent"):
            roles[p["agent"]] = "agent"
        net = network_around(tx, ts, t.sender_id, t.receiver_id, int(r.ts_sec), r.txn_id, roles)
        alerts.append(dict(
            id=f"H-{r.txn_id}", source="historical", txn_id=r.txn_id, ts_sec=int(r.ts_sec),
            created=(start + pd.Timedelta(seconds=int(r.ts_sec))).isoformat(), sender_id=t.sender_id,
            receiver_id=t.receiver_id, txn_type=r.txn_type, amount=float(t.amount), risk_score=float(s.risk_score),
            band=s.band, policy_override=s.policy_override or None, p_fraud=round(float(s.p_fraud), 4),
            p_fraud_calibrated=round(float(s.p_cal), 4), anomaly=round(float(s.anomaly), 3), graph=round(float(s.graph), 3),
            reasons=reasons, shap=[dict(feature=f, value=row.get(f), shap=round(float(v), 4)) for f, v in top],
            evidence={k: (round(float(v), 3) if isinstance(v, (int, float, np.floating, np.integer)) and v is not None else v)
                      for k, v in row.items() if k in bundle["features"]},
            network=net, planted_id=(p or {}).get("id"), title=(p or {}).get("title"),
            truth=dict(is_fraud=int(r.is_fraud), scenario=row.get("scenario"), role=row.get("fraud_role")),
        ))

    # ---------------- Agent Watch series (test window) and fairness
    ag = pd.read_parquet(resolve(cfg, "features_dir") / "agent_scores.parquet")
    test = ag[ag.split == "test"]
    top_agents = test.groupby("agent_id").score.max().sort_values(ascending=False).head(8).index.tolist()
    aw = state.get("agent_watch", {})
    if aw.get("sc06", {}).get("agent") and aw["sc06"]["agent"] not in top_agents:
        top_agents.insert(0, aw["sc06"]["agent"])
    series = {a: test[test.agent_id == a].sort_values("day")[["day", "score", "volume", "volume_ratio", "cashouts",
                                                              "night_share", "young_share", "flagged", "is_episode"]]
              .round(3).to_dict("records") for a in top_agents}
    area = test.drop_duplicates("agent_id").set_index("agent_id").area_id.to_dict()
    rep = resolve(cfg, "reports_dir")
    fairness = pd.read_csv(rep / "fairness.csv").to_dict("records") if (rep / "fairness.csv").exists() else []
    metrics = json.loads((rep / "metrics_test.json").read_text(encoding="utf-8")) if (rep / "metrics_test.json").exists() else {}

    world = dict(
        built_at=end, edges=edges, complained=complained, alerts=alerts, personas=pick_personas(data, state),
        agents=dict(series=series, area={a: area.get(a) for a in top_agents}, sc06=aw.get("sc06"),
                    register_compromise=aw.get("register_compromise"), threshold=aw.get("threshold"),
                    by_split=aw.get("by_split")),
        fairness=fairness, shap_top=metrics.get("shap_top20"), per_scenario=metrics.get("per_scenario"),
        limits=cfg["limits"], fees=cfg.get("fees"),
    )
    path = resolve(cfg, "artifacts_dir") / "demo_world.joblib"
    joblib.dump(world, path, compress=3)
    if verbose:
        print(f"[demo_world] {len(edges):,} recent edges, {len(alerts)} historical alerts, "
              f"personas {list(world['personas'])} -> {path} ({path.stat().st_size / 1e6:.1f} MB)")
    return world


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=None)
    build(load_config(ap.parse_args().config))


if __name__ == "__main__":
    main()
