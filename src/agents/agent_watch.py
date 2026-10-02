"""Agent Watch: rule-based peer z-scores per agent-day (no ML on ~9 rogue agents).

Signals per agent-day (cash-outs it paid out):
  volume vs peer median (log2 ratio) | night share (00-06, 23-24) | share paid to wallets < 7 days old |
  pass-through share (customer received >= 50% of the amount in the hour before) |
  share of customers already reported to 16268 (complaints filed before the day ends)
Each is a robust z-score against peers in the same area on the same day (division if the
area has too few agents). Composite -> 0-100 score; flagged at >= 80.
A separate 'register compromise' signal counts fraud complainants who visited the agent in
the 7 days before their scam, tested against the agent's footfall (Poisson): the
agent-register-harvesting pattern (S1 variant).

Evaluation is case-level: did each rogue episode get flagged on at least one of its days,
and how many innocent agent-days were flagged?

    python -m src.agents.agent_watch
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from src.common.config import DAY, load_config, resolve, save_json
from src.datagen.generate import load
from src.models import plots

WEIGHTS = {"z_volume": 0.5, "z_night": 0.15, "z_young": 0.1, "z_pass": 0.1, "z_reported": 0.15}
SCALE = 1.37                     # composite 2.2 -> score 80 (picked on train: ~0.6 false alarms/day over 300 agents)


def robust_z(x: pd.Series, groups: pd.Series, floor: float) -> pd.Series:
    med = x.groupby(groups).transform("median")
    mad = (x - med).abs().groupby(groups).transform("median")
    return (x - med) / (1.4826 * mad + floor)


def agent_days(data: dict, cfg: dict) -> pd.DataFrame:
    tx = data["transactions"]
    start = pd.Timestamp(cfg["world"]["start_date"])
    cust = data["customers"].set_index("wallet_id")
    co = tx[(tx.txn_type == "CASH_OUT") & (tx.status == "SUCCESS") & (tx.receiver_type == "A")].copy()
    co["day"] = ((co.ts - start).dt.total_seconds() // DAY).astype(int)
    co["hour"] = co.ts.dt.hour
    co["night"] = (co.hour < 6) | (co.hour >= 23)
    age = (co.ts - co.sender_id.map(cust.signup_ts)).dt.total_seconds() / DAY
    co["young"] = age < 7
    # pass-through: money landed in the customer's wallet within the hour before the cash-out
    inflow = tx[(tx.status == "SUCCESS") & (tx.receiver_type == "C") &
                tx.txn_type.isin(["SEND_MONEY", "ADD_MONEY", "CASH_IN", "REMITTANCE_IN", "SALARY"])]
    inflow = inflow[["ts", "receiver_id", "amount"]].rename(columns={"receiver_id": "sender_id", "amount": "in_amt", "ts": "t_in"})
    co = co.sort_values("ts")
    mm = pd.merge_asof(co[["ts", "sender_id", "amount"]].reset_index(), inflow.sort_values("t_in"), left_on="ts",
                       right_on="t_in", by="sender_id", direction="backward", tolerance=pd.Timedelta(hours=1))
    co["pass"] = (mm.set_index("index").in_amt.reindex(co.index).fillna(0) >= 0.5 * co.amount).values
    # customers already reported before the end of that day
    cp = data["complaints"]
    first_rep = cp.groupby("reported_wallet_id").ts.min()
    rep_ts = co.sender_id.map(first_rep)
    day_end = start + pd.to_timedelta(co.day + 1, unit="D")
    co["reported"] = rep_ts.notna() & (rep_ts < day_end)
    g = co.groupby(["receiver_id", "day"])
    ad = pd.DataFrame({
        "cashouts": g.size(), "volume": g.amount.sum(), "customers": g.sender_id.nunique(),
        "night_share": g.night.mean(), "young_share": g.young.mean(), "pass_share": g["pass"].mean(),
        "reported_share": g.reported.mean(),
    }).reset_index().rename(columns={"receiver_id": "agent_id"})
    # fill agent-days with no cash-outs so peers are complete
    agents = data["agents"]
    full = pd.MultiIndex.from_product([agents.agent_id, range(cfg["world"]["n_days"])], names=["agent_id", "day"])
    ad = ad.set_index(["agent_id", "day"]).reindex(full).fillna(0).reset_index()
    ad = ad.merge(agents[["agent_id", "area_id", "division"]], on="agent_id")
    n_area = agents.groupby("area_id").size()
    ad["peer_group"] = np.where(ad.area_id.map(n_area) >= cfg["agent_watch"]["min_peer_agents"], ad.area_id, ad.division)
    ad["peer_key"] = ad.peer_group + "|" + ad.day.astype(str)
    return ad, co


def register_compromise(data: dict, cfg: dict, window_days: int = 30, alpha: float = 1e-3) -> pd.DataFrame:
    """Per agent-day: fraud complainants (complaint known by that day) who visited this agent in
    the 7 days before their scam, over a trailing window. Poisson test against the agent's share
    of footfall: many victims sharing one shop is the register-harvesting fingerprint."""
    from scipy.stats import poisson
    tx, cp = data["transactions"], data["complaints"]
    start = pd.Timestamp(cfg["world"]["start_date"])
    fraud_cp = cp[(cp.category == "FRAUD") & cp.complainant_id.str.startswith("W")]
    fc = fraud_cp.assign(t_scam=fraud_cp.related_txn_id.map(tx.set_index("txn_id").ts)).dropna(subset=["t_scam"])
    v = tx[(tx.status == "SUCCESS") & tx.txn_type.isin(["CASH_IN", "CASH_OUT"]) &
           ((tx.sender_type == "A") | (tx.receiver_type == "A"))]
    visits = pd.DataFrame({"wallet": np.where(v.txn_type == "CASH_IN", v.receiver_id, v.sender_id),
                           "agent": np.where(v.txn_type == "CASH_IN", v.sender_id, v.receiver_id), "t_visit": v.ts})
    j = fc[["complainant_id", "ts", "t_scam"]].merge(visits, left_on="complainant_id", right_on="wallet")
    j = j[(j.t_visit < j.t_scam) & (j.t_visit >= j.t_scam - pd.Timedelta(days=7))]
    j = j.drop_duplicates(["complainant_id", "agent"])
    j["day"] = ((j.ts - start).dt.total_seconds() // DAY).astype(int)          # day the complaint became known
    visits["day"] = ((visits.t_visit - start).dt.total_seconds() // DAY).astype(int)
    rows = []
    n_days = cfg["world"]["n_days"]
    for d in range(n_days):
        lo = d - window_days
        hit = j[(j.day <= d) & (j.day > lo)].groupby("agent").complainant_id.nunique()
        if hit.empty:
            continue
        foot = visits[(visits.day <= d) & (visits.day > lo)].groupby("agent").wallet.nunique()
        lam = hit.sum() * foot / foot.sum()
        for agent, k in hit.items():
            p = float(poisson.sf(k - 1, max(lam.get(agent, 0.0), 1e-3)))
            rows.append((agent, d, int(k), round(float(lam.get(agent, 0.0)), 2), p))
    return pd.DataFrame(rows, columns=["agent_id", "day", "victims_visited", "victims_expected", "p_value"])


def score(ad: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    ad = ad.copy()
    ad["log_volume"] = np.log1p(ad.volume)
    peer_med = ad.groupby("peer_key").volume.transform("median")
    ad["volume_ratio"] = (ad.volume + 1000) / (peer_med + 1000)
    ad["z_volume"] = np.log2(ad.volume_ratio)          # 8x the area median -> 3
    ad["z_night"] = robust_z(ad.night_share, ad.peer_key, 0.05)
    ad["z_young"] = robust_z(ad.young_share, ad.peer_key, 0.05)
    ad["z_pass"] = robust_z(ad.pass_share, ad.peer_key, 0.08)
    ad["z_reported"] = robust_z(ad.reported_share, ad.peer_key, 0.05)
    comp = sum(w * ad[k].clip(0, 8) for k, w in WEIGHTS.items())
    ad["composite"] = comp
    ad["score"] = (100 * (1 - np.exp(-comp / SCALE))).round(1)
    ad["flagged"] = (ad.score >= 80) & (ad.cashouts >= 3)
    return ad


def evaluate_agents(ad: pd.DataFrame, truth: pd.DataFrame, cfg: dict) -> dict:
    rog = truth[truth.is_rogue == 1]
    ep_days = set()
    episodes = []
    for r in rog.itertuples():
        for e in str(r.episodes).split(";"):
            if e:
                s, t = map(int, e.split("-"))
                days0 = list(range(s - 1, t))
                episodes.append((r.agent_id, days0))
                ep_days.update((r.agent_id, d) for d in days0)
    ad = ad.copy()
    ad["is_episode"] = [(a, d) in ep_days for a, d in zip(ad.agent_id, ad.day)]
    s = cfg["splits"]
    ad["split"] = np.where(ad.day + 1 <= s["train_days"][1], "train", np.where(ad.day + 1 <= s["val_days"][1], "val", "test"))
    out = {}
    for split, g in ad.groupby("split"):
        tp = int((g.flagged & g.is_episode).sum())
        fp = int((g.flagged & ~g.is_episode).sum())
        fn = int((~g.flagged & g.is_episode).sum())
        eps = [(a, ds) for a, ds in episodes if ad.loc[(ad.agent_id == a) & ad.day.isin(ds), "split"].iloc[0] == split]
        caught = sum(bool(g[(g.agent_id == a) & g.day.isin(ds)].flagged.any()) for a, ds in eps)
        out[split] = dict(agent_day_precision=round(tp / max(tp + fp, 1), 3), agent_day_recall=round(tp / max(tp + fn, 1), 3),
                          episodes=len(eps), episodes_flagged=caught,
                          false_alarm_agent_days_per_day=round(fp / g.day.nunique(), 2))
    return out, ad


def run(cfg, verbose=True):
    data = load(cfg)
    ad, _ = agent_days(data, cfg)
    ad = score(ad, cfg)
    rc = register_compromise(data, cfg)
    ad = ad.merge(rc, on=["agent_id", "day"], how="left").fillna({"victims_visited": 0, "victims_expected": 0, "p_value": 1.0})
    ad["register_flag"] = (ad.victims_visited >= 4) & (ad.p_value < 1e-3)
    truth = data["agent_truth"]
    res, ad = evaluate_agents(ad, truth, cfg)
    harvested = set(truth.agent_id[truth.is_register_harvested == 1])
    reg = ad[ad.register_flag].agent_id.unique()
    reg_eval = dict(harvested_agents=len(harvested), harvested_flagged=int(len(harvested & set(reg))),
                    other_agents_flagged=int(len(set(reg) - harvested)))
    planted = {p["id"]: p for p in data["planted"]}
    sc06_agent = planted["SC-06"]["agent"]
    me = ad[ad.agent_id == sc06_agent]
    test_days = me[(me.day + 1 >= cfg["splits"]["test_days"][0])]
    sc06 = dict(agent=sc06_agent, max_score=float(test_days.score.max()), flagged=bool(test_days.flagged.any()),
                flagged_days=[int(d) + 1 for d in test_days[test_days.flagged].day],
                max_volume_vs_peer_median=None)
    peers = ad[(ad.peer_key.isin(me.peer_key)) & (ad.agent_id != sc06_agent)].groupby("day").volume.median()
    ratio = (me.set_index("day").volume / peers.clip(lower=1000)).reindex(test_days.day)
    sc06["max_volume_vs_peer_median"] = round(float(ratio.max()), 1)
    eps = [tuple(map(int, e.split("-"))) for e in str(truth.set_index("agent_id").episodes.get(sc06_agent, "")).split(";") if e]
    fig = resolve(cfg, "reports_dir") / "figures"
    plots.agent_volume(me.day.values + 1, me.volume.values, peers.reindex(me.day).fillna(0).values, eps,
                       fig / "agent_watch_sc06.png", sc06_agent)
    top = ad[ad.day == ad.day.max()].sort_values("score", ascending=False).head(10)
    report = dict(by_split=res, register_compromise=reg_eval, sc06=sc06, weights=WEIGHTS,
                  threshold=80, top_agents_last_day=top[["agent_id", "area_id", "score", "cashouts", "volume",
                                                          "night_share", "young_share"]].round(3).to_dict("records"))
    save_json(report, resolve(cfg, "reports_dir") / "agent_watch.json")
    ad.to_parquet(resolve(cfg, "features_dir") / "agent_scores.parquet", index=False)
    if verbose:
        for k, v in res.items():
            print(f"[agent-watch] {k:<5} {v}")
        print(f"[agent-watch] register-compromise: {reg_eval}")
        print(f"[agent-watch] SC-06 {sc06}")
    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=None)
    a = ap.parse_args()
    run(load_config(a.config))


if __name__ == "__main__":
    main()
