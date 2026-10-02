"""Data validation T1-T14. Each check returns (passed, details).

T1 schema & keys            T6 volume & type mix          T11 anti-shortcut (no trivial tells)
T2 referential integrity    T7 amount realism             T12 split integrity
T3 balance conservation     T8 fraud prevalence & spread  T13 planted demo scenarios
T4 KYC limits respected     T9 label consistency          T14 reproducibility (seed 42)
T5 temporal realism         T10 scenario signatures
"""
from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd

from src.common.config import DAY, load_config, split_bounds_sec

REQUIRED = {
    "transactions": ["txn_id", "ts", "txn_type", "sender_id", "sender_type", "receiver_id", "receiver_type", "amount",
                     "fee", "status", "fail_reason", "device_id", "channel", "area_id"],
    "labels": ["txn_id", "is_fraud", "scenario", "case_id", "fraud_role", "split"],
    "customers": ["wallet_id", "msisdn", "signup_ts", "kyc_level", "channel", "segment", "gender", "age_band",
                  "division", "area_id", "urban_rural", "home_agent_id"],
    "agents": ["agent_id", "area_id", "division", "onboard_ts"],
    "account_events": ["event_id", "ts", "wallet_id", "event_type"],
    "complaints": ["complaint_id", "ts", "complainant_id", "reported_wallet_id", "category"],
}
KEYS = {"transactions": "txn_id", "labels": "txn_id", "customers": "wallet_id", "agents": "agent_id",
        "merchants": "merchant_id", "account_events": "event_id", "complaints": "complaint_id", "cases": "case_id"}
LIMIT_OF = {"SEND_MONEY": ("send_money", "sender_id"), "CASH_OUT": ("cash_out", "sender_id"),
            "PAYMENT": ("payment", "sender_id"), "BILL_PAY": ("payment", "sender_id"),
            "MOBILE_RECHARGE": ("payment", "sender_id"), "CASH_IN": ("cash_in", "receiver_id"),
            "ADD_MONEY": ("add_money", "receiver_id")}
SCENARIOS = ["S1", "S2", "S3", "S5", "S6", "S7", "S8"]
SCORED = ["SEND_MONEY", "CASH_OUT", "PAYMENT", "ADD_MONEY"]


def _secs(cfg, ts: pd.Series) -> np.ndarray:
    return ((ts - pd.Timestamp(cfg["world"]["start_date"])).dt.total_seconds()).to_numpy().astype(np.int64)


class Checker:
    def __init__(self, data: dict, cfg: dict):
        self.d, self.cfg = data, cfg
        self.tx = data["transactions"]
        self.lab = data["labels"]
        self.cust = data["customers"]
        self.txl = self.tx.merge(self.lab, on="txn_id", how="left")
        self.sec = _secs(cfg, self.tx.ts)

    # ------------------------------------------------------------------ T1
    def t1_schema(self):
        problems = []
        for t, cols in REQUIRED.items():
            df = self.d[t]
            miss = [c for c in cols if c not in df.columns]
            if miss:
                problems.append(f"{t}: missing {miss}")
                continue
            nn = [c for c in cols if df[c].isna().any() and c not in ("device_id",)]
            if nn:
                problems.append(f"{t}: nulls in {nn}")
        for t, k in KEYS.items():
            if t in self.d and not self.d[t][k].is_unique:
                problems.append(f"{t}.{k} not unique")
        if (self.tx.amount <= 0).any():
            problems.append("non-positive amounts")
        if not self.tx.ts.is_monotonic_increasing:
            problems.append("transactions not time-ordered")
        return not problems, {"problems": problems, "rows": {t: len(self.d[t]) for t in REQUIRED}}

    # ------------------------------------------------------------------ T2
    def t2_refs(self):
        d = self.d
        known = set(d["customers"].wallet_id) | set(d["agents"].agent_id) | set(d["merchants"].merchant_id) | \
            set(d["billers"].biller_id) | {"X_EMPLOYER", "X_REMIT", "X_BANK", "X_CARD"}
        bad_s = (~self.tx.sender_id.isin(known)).sum()
        bad_r = (~self.tx.receiver_id.isin(known)).sum()
        lab_ok = len(self.lab) == len(self.tx) and set(self.lab.txn_id) == set(self.tx.txn_id)
        ev_bad = (~d["account_events"].wallet_id.isin(d["customers"].wallet_id)).sum()
        cp_bad = (~d["complaints"].reported_wallet_id.isin(d["customers"].wallet_id)).sum()
        ha_bad = (~d["customers"].home_agent_id.isin(d["agents"].agent_id)).sum()
        det = dict(bad_sender=int(bad_s), bad_receiver=int(bad_r), labels_match=lab_ok, bad_event_wallet=int(ev_bad),
                   bad_complaint_wallet=int(cp_bad), bad_home_agent=int(ha_bad))
        return bad_s == 0 and bad_r == 0 and lab_ok and ev_bad == 0 and cp_bad == 0 and ha_bad == 0, det

    # ------------------------------------------------------------------ T3
    def t3_balances(self):
        tx = self.tx
        ok = tx.status.values == "SUCCESS"
        s_tr = tx.sender_type.values != "X"
        r_tr = tx.receiver_type.values != "X"
        amt, fee = tx.amount.values, tx.fee.values
        sb0, sb1, rb0, rb1 = (tx[c].values for c in ("sender_bal_before", "sender_bal_after", "receiver_bal_before", "receiver_bal_after"))
        e1 = np.abs(np.where(ok, sb0 - amt - fee, sb0) - sb1)[s_tr]
        e2 = np.abs(np.where(ok, rb0 + amt, rb0) - rb1)[r_tr]
        row_err = int((e1 > 0.02).sum() + (e2 > 0.02).sum())
        idx = np.arange(len(tx))
        long = pd.DataFrame({
            "w": np.concatenate([tx.sender_id.values[s_tr], tx.receiver_id.values[r_tr]]),
            "i": np.concatenate([idx[s_tr], idx[r_tr]]),
            "b0": np.concatenate([sb0[s_tr], rb0[r_tr]]),
            "b1": np.concatenate([sb1[s_tr], rb1[r_tr]]),
        }).sort_values(["w", "i"], kind="stable")
        same = long.w.values[1:] == long.w.values[:-1]
        gap = np.abs(long.b0.values[1:] - long.b1.values[:-1])[same]
        chain_err = int((gap > 0.02).sum())
        neg = int((long.b1.values < -0.01).sum())
        return row_err == 0 and chain_err == 0 and neg == 0, dict(row_errors=row_err, chain_breaks=chain_err,
                                                                  negative_balances=neg, wallets=int(long.w.nunique()))

    # ------------------------------------------------------------------ T4
    def t4_limits(self):
        tx, cfg = self.tx, self.cfg
        kyc = self.cust.set_index("wallet_id").kyc_level
        rows = []
        for t, (lt, col) in LIMIT_OF.items():
            m = (tx.txn_type == t) & (tx.status == "SUCCESS")
            sub = tx.loc[m, ["ts", "amount", col]].rename(columns={col: "cust"})
            sub = sub[sub.cust.isin(kyc.index)]
            sub["ltype"] = lt
            rows.append(sub)
        s = pd.concat(rows)
        s["kyc"] = s.cust.map(kyc)
        s["day"] = s.ts.dt.floor("D")
        s["month"] = s.ts.dt.to_period("M")
        cap = {(k, lt): v for k in ("KYC1", "KYC2") for lt, v in cfg["limits"][k].items()}
        viol = {"per_txn": 0, "daily_amount": 0, "daily_count": 0, "monthly_amount": 0}
        s["per_txn"] = [cap[(k, l)]["per_txn"] for k, l in zip(s.kyc, s.ltype)]
        viol["per_txn"] = int((s.amount > s.per_txn + 1e-6).sum())
        g = s.groupby(["cust", "kyc", "ltype", "day"]).amount.agg(["sum", "count"]).reset_index()
        g["dcap"] = [cap[(k, l)]["daily_amount"] for k, l in zip(g.kyc, g.ltype)]
        g["ccap"] = [cap[(k, l)]["daily_count"] for k, l in zip(g.kyc, g.ltype)]
        viol["daily_amount"] = int((g["sum"] > g.dcap + 1e-6).sum())
        viol["daily_count"] = int((g["count"] > g.ccap).sum())
        mth = s.groupby(["cust", "kyc", "ltype", "month"]).amount.sum().reset_index()
        mth["mcap"] = [cap[(k, l)]["monthly_amount"] for k, l in zip(mth.kyc, mth.ltype)]
        viol["monthly_amount"] = int((mth.amount > mth.mcap + 1e-6).sum())
        failed_limit = int((tx.fail_reason == "LIMIT_EXCEEDED").sum())
        return sum(viol.values()) == 0, dict(violations=viol, rejected_attempts=failed_limit)

    # ------------------------------------------------------------------ T5
    def t5_temporal(self):
        x = self.txl
        cust_init = x.txn_type.isin(["SEND_MONEY", "PAYMENT", "MOBILE_RECHARGE", "BILL_PAY", "CASH_OUT"]) & (x.is_fraud == 0)
        hour = x.ts.dt.hour
        night = float((hour[cust_init] < 6).mean())
        hourly = hour[cust_init].value_counts(normalize=True).sort_index()
        peak = int(hourly.idxmax())
        p2p = x[(x.txn_type == "SEND_MONEY") & (x.is_fraud == 0)]
        per_day = p2p.groupby(p2p.ts.dt.floor("D")).size()
        eid = [pd.Timestamp(self.cfg["world"]["start_date"]) + pd.Timedelta(days=d - 1) for d in self.cfg["world"]["eid_days"]]
        eid_ratio = float(per_day.reindex(eid).mean() / per_day.median())
        sal = x[x.txn_type == "SALARY"]
        sal_dom_ok = bool(sal.ts.dt.day.between(1, 10).all())
        wd = per_day.groupby(per_day.index.dayofweek).mean()
        fri_ratio = float(wd.get(4, np.nan) / wd.drop([4, 5], errors="ignore").mean())
        cash = x[x.txn_type.isin(["CASH_IN", "CASH_OUT"]) & (x.is_fraud == 0)]
        cash_night = float((cash.ts.dt.hour < 7).mean())
        det = dict(night_share_00_06=round(night, 4), peak_hour=peak, eid_p2p_vs_median_day=round(eid_ratio, 2),
                   salary_on_days_1_10=sal_dom_ok, friday_p2p_vs_weekday=round(fri_ratio, 3),
                   normal_cash_night_share=round(cash_night, 4))
        ok = night < 0.07 and 17 <= peak <= 23 and eid_ratio > 1.8 and sal_dom_ok and fri_ratio > 1.0 and cash_night < 0.01
        return ok, det

    # ------------------------------------------------------------------ T6
    def t6_volume(self):
        w = self.cfg["world"]
        target = w["n_customers"] * w["n_days"] * w["target_txn_per_customer_day"]
        n = len(self.tx)
        mix = self.tx.txn_type.value_counts(normalize=True)
        bands = {"SEND_MONEY": (0.20, 0.40), "MOBILE_RECHARGE": (0.12, 0.30), "PAYMENT": (0.07, 0.20),
                 "CASH_IN": (0.07, 0.20), "CASH_OUT": (0.06, 0.18)}
        bad = {k: round(float(mix.get(k, 0)), 3) for k, (lo, hi) in bands.items() if not lo <= mix.get(k, 0) <= hi}
        fail = float((self.tx.status == "FAILED").mean())
        tol = 0.15 if self.cfg.get("_scale", 1.0) >= 0.5 else 0.25         # tiny worlds: signups weigh more
        ok = abs(n / target - 1) <= tol and not bad and fail < 0.06
        return ok, dict(rows=n, target=int(target), ratio=round(n / target, 3), out_of_band=bad,
                        failure_rate=round(fail, 4), mix={k: round(float(v), 3) for k, v in mix.items()})

    # ------------------------------------------------------------------ T7
    def t7_amounts(self):
        x = self.txl
        p2p = x[(x.txn_type == "SEND_MONEY") & (x.is_fraud == 0)].amount
        round100 = float((p2p % 100 == 0).mean())
        med = float(p2p.median())
        tail = float(p2p.quantile(0.99) / med)
        rech = x[x.txn_type == "MOBILE_RECHARGE"].amount
        rech_ok = bool(rech.isin([20, 30, 49, 50, 99, 100, 149, 200, 300, 500]).all())
        pay_round = float((x[x.txn_type == "PAYMENT"].amount % 100 == 0).mean())
        ok = round100 >= 0.45 and 300 <= med <= 3000 and tail > 8 and rech_ok and pay_round < 0.3
        return ok, dict(p2p_round100_share=round(round100, 3), p2p_median=med, p2p_p99_over_median=round(tail, 1),
                        recharge_amounts_valid=rech_ok, payment_round100_share=round(pay_round, 3))

    # ------------------------------------------------------------------ T8
    def t8_prevalence(self):
        x = self.txl
        share = float(x.is_fraud.mean())
        fr = x[x.is_fraud == 1]
        cov = fr.groupby(["scenario", "split"]).size().unstack(fill_value=0)
        missing = [f"{s}/{sp}" for s in SCENARIOS for sp in ("train", "val", "test")
                   if s not in cov.index or cov.loc[s].get(sp, 0) == 0]
        at = self.d["agent_truth"]
        rogue = at[at.is_rogue == 1]
        ep_split = set()
        for eps in rogue.episodes:
            for e in str(eps).split(";"):
                if e:
                    s = int(e.split("-")[0])
                    ep_split.add(self._split_of_day1(s))
        s4_ok = ep_split >= {"train", "val", "test"}
        ok = 0.003 <= share <= 0.008 and not missing and s4_ok
        return ok, dict(fraud_share=round(share, 5), fraud_rows=int(len(fr)), missing_scenario_split=missing,
                        rogue_agents=int(len(rogue)), rogue_episode_splits=sorted(ep_split),
                        rows_by_scenario_split=cov.to_dict())

    def _split_of_day1(self, d):
        s = self.cfg["splits"]
        return "train" if d <= s["train_days"][1] else ("val" if d <= s["val_days"][1] else "test")

    # ------------------------------------------------------------------ T9
    def t9_labels(self):
        x = self.txl
        fr = x[x.is_fraud == 1]
        bad_fr = int(((fr.scenario == "NONE") | (fr.case_id == "") | (fr.fraud_role == "")).sum())
        nf = x[x.is_fraud == 0]
        bad_nf = int((nf.scenario != "NONE").sum())
        cases = self.d["cases"]
        empty = cases[cases.n_fraud_txns == 0]
        nonempty_share = 1 - len(empty) / max(1, len(cases))
        orphan = int((~fr.case_id.isin(cases.case_id)).sum())
        ok = bad_fr == 0 and bad_nf == 0 and nonempty_share >= 0.95 and orphan == 0
        return ok, dict(fraud_rows_missing_meta=bad_fr, nonfraud_with_scenario=bad_nf,
                        cases=int(len(cases)), empty_cases=int(len(empty)), nonempty_share=round(nonempty_share, 3),
                        orphan_case_ids=orphan, roles=fr.fraud_role.value_counts().to_dict())

    # ------------------------------------------------------------------ T10
    def t10_signatures(self):
        x, d = self.txl, self.d
        det, ok = {}, True
        signup = self.cust.set_index("wallet_id").signup_ts
        # S2: young collector + many distinct first-time senders
        s2 = x[(x.scenario == "S2") & (x.fraud_role == "victim_payment")]
        first = s2.groupby("case_id").agg(t=("ts", "min"), col=("receiver_id", "first"), n=("sender_id", "nunique"))
        roles = d["wallet_truth"].set_index("wallet_id").roles
        aged = first.col.map(roles).fillna("").str.contains("aged")
        age_days = (first.t - first.col.map(signup)).dt.total_seconds() / DAY
        det["S2_new_collector_age_days_max"] = round(float(age_days[~aged].max()), 2)
        det["S2_min_unique_victims"] = int(first.n.min())
        ok &= det["S2_new_collector_age_days_max"] <= 3.1 and det["S2_min_unique_victims"] >= 5
        # S3: hop delay (time between money landing in a mule and it moving on)
        hops = x[(x.scenario == "S3") & (x.fraud_role == "mule_hop") & (x.status == "SUCCESS")].sort_values("ts")
        inflow = x[(x.is_fraud == 1) & (x.status == "SUCCESS") & (x.receiver_type == "C")].sort_values("ts")
        mm = pd.merge_asof(hops[["ts", "sender_id"]].rename(columns={"sender_id": "w"}),
                           inflow[["ts", "receiver_id"]].rename(columns={"receiver_id": "w", "ts": "t_in"}),
                           left_on="ts", right_on="t_in", by="w", direction="backward", allow_exact_matches=False)
        delay = (mm.ts - mm.t_in).dt.total_seconds() / 60
        det["S3_median_hop_delay_min"] = round(float(delay.median()), 1)
        ok &= det["S3_median_hop_delay_min"] < 30
        # S6: SIM swap precedes the drain
        ev = d["account_events"]
        sw = ev[(ev.event_type == "SIM_SWAP") & ev.case_id.str.startswith(("S6", "SC-01"))].groupby("case_id").ts.min()
        dr = x[(x.scenario == "S6") & (x.fraud_role == "takeover_drain")].groupby("case_id").ts.min()
        j = pd.concat([sw.rename("swap"), dr.rename("drain")], axis=1).dropna()
        gap = (j.drain - j.swap).dt.total_seconds() / 3600
        det["S6_swap_before_drain_share"] = round(float(((gap > 0) & (gap < 30)).mean()), 3)
        ok &= det["S6_swap_before_drain_share"] >= 0.95
        # S1 new device vs S7 own device
        cust_init = x[x.txn_type.isin(["SEND_MONEY", "PAYMENT", "MOBILE_RECHARGE", "BILL_PAY", "CASH_OUT"])]
        prior = cust_init[cust_init.is_fraud == 0][["sender_id", "device_id", "ts"]]
        first_seen = prior.groupby(["sender_id", "device_id"]).ts.min()

        def seen_before(rows):
            k = list(zip(rows.sender_id, rows.device_id))
            fs = first_seen.reindex(k)
            return (fs.values < rows.ts.values)
        remote = set(d["cases"].case_id[d["cases"].variant == "remote_access_app"])
        s1_all = x[(x.scenario == "S1") & (x.fraud_role == "takeover_drain")]
        s1 = s1_all[~s1_all.case_id.isin(remote)]                 # remote-access takeovers use the victim's phone
        det["S1_remote_access_share"] = round(float(s1_all.case_id.isin(remote).mean()), 3)
        s7 = x[(x.scenario == "S7") & (x.fraud_role == "coerced_send")]
        det["S1_drain_on_new_device_share"] = round(float(1 - seen_before(s1).mean()), 3)
        det["S7_send_on_own_device_share"] = round(float(seen_before(s7).mean()), 3)
        ok &= det["S1_drain_on_new_device_share"] >= 0.95 and det["S7_send_on_own_device_share"] >= 0.85
        # S8 starts with ADD_MONEY
        s8 = x[x.scenario == "S8"].sort_values("ts").groupby("case_id").txn_type.first()
        det["S8_starts_with_add_money_share"] = round(float((s8 == "ADD_MONEY").mean()), 3)
        ok &= det["S8_starts_with_add_money_share"] >= 0.95
        # S4 rogue agent volume multiplier vs peers in the same area, on episode days
        mult = self.rogue_multiplier()
        det["S4_episode_volume_multiplier_median"] = round(mult, 2)
        need = 4.0 if self.cfg.get("_scale", 1.0) >= 0.5 else 1.5      # tiny worlds have only ~3 gangs
        det["S4_required_multiplier"] = need
        ok &= mult >= need
        return bool(ok), det

    def rogue_multiplier(self):
        x, d = self.tx, self.d
        co = x[(x.txn_type == "CASH_OUT") & (x.status == "SUCCESS")]
        vol = co.groupby([co.receiver_id, co.ts.dt.floor("D")]).amount.sum()
        ag = d["agents"].set_index("agent_id")
        start = pd.Timestamp(self.cfg["world"]["start_date"])
        ratios = []
        for _, r in d["agent_truth"][d["agent_truth"].is_rogue == 1].iterrows():
            area = ag.area_id[r.agent_id]
            peers = ag.index[(ag.area_id == area) & (ag.index != r.agent_id)]
            for e in str(r.episodes).split(";"):
                if not e:
                    continue
                s, t = map(int, e.split("-"))
                for day1 in range(s, t + 1):
                    day = start + pd.Timedelta(days=day1 - 1)
                    me = vol.get((r.agent_id, day), 0.0)
                    pv = [vol.get((p, day), 0.0) for p in peers]
                    base = max(np.median(pv) if pv else 0.0, 1000.0)
                    ratios.append(me / base)
        return float(np.median(ratios)) if ratios else 0.0

    # ------------------------------------------------------------------ T11
    def t11_shortcuts(self):
        from sklearn.metrics import roc_auc_score
        x, d = self.txl, self.d
        det, ok = {}, True
        wt = d["wallet_truth"]
        mules = wt[wt.roles.str.contains("mule")]
        aged_share = float(mules.roles.str.contains("aged").mean())
        det["aged_mule_share"] = round(aged_share, 3)
        ok &= 0.15 <= aged_share <= 0.40
        sc = x[x.txn_type.isin(SCORED)]
        night_f = float((sc[sc.is_fraud == 1].ts.dt.hour < 6).mean())
        night_n = float((sc[sc.is_fraud == 0].ts.dt.hour < 6).mean())
        det["fraud_night_share"] = round(night_f, 3)
        det["normal_night_share"] = round(night_n, 3)
        ok &= night_f < 0.6 and night_f > night_n
        signup = self.cust.set_index("wallet_id").signup_ts
        start = pd.Timestamp(self.cfg["world"]["start_date"])
        new_legit = self.cust[(self.cust.signup_ts >= start) & ~self.cust.wallet_id.isin(wt.wallet_id)]
        det["legit_new_wallets"] = int(len(new_legit))
        ev = d["account_events"]
        det["legit_device_changes"] = int(((ev.event_type == "DEVICE_CHANGE") & (ev.case_id == "")).sum())
        det["legit_sim_swaps"] = int(((ev.event_type == "SIM_SWAP") & (ev.case_id == "")).sum())
        ok &= det["legit_new_wallets"] >= self.cfg["world"]["n_days"] * 0.5 and det["legit_device_changes"] >= 50
        # benign fan-in: innocent wallets receiving from >= 8 distinct senders in a day
        p2p = x[(x.txn_type == "SEND_MONEY") & (x.receiver_type == "C") & (x.is_fraud == 0)]
        fan = p2p.groupby([p2p.receiver_id, p2p.ts.dt.floor("D")]).sender_id.nunique()
        bad_w = set(wt.wallet_id[wt.roles.str.contains("collector|seller|recipient|mule")])
        benign = fan[(fan >= 8) & ~fan.index.get_level_values(0).isin(bad_w)]
        det["benign_fanin_wallet_days_ge8"] = int(len(benign))
        ok &= len(benign) >= 5
        # single raw features must not separate fraud on their own
        y = sc.is_fraud.values
        feats = {
            "amount": sc.amount.values,
            "hour_night": (sc.ts.dt.hour < 6).astype(int).values,
            "receiver_age_days": ((sc.ts - sc.receiver_id.map(signup)).dt.total_seconds() / DAY).fillna(9999).values,
            "sender_age_days": ((sc.ts - sc.sender_id.map(signup)).dt.total_seconds() / DAY).fillna(9999).values,
        }
        aucs = {}
        for k, v in feats.items():
            a = roc_auc_score(y, v)
            aucs[k] = round(float(max(a, 1 - a)), 3)
        det["single_feature_auc"] = aucs
        ok &= max(aucs.values()) <= 0.95
        return bool(ok), det

    # ------------------------------------------------------------------ T12
    def t12_splits(self):
        x = self.txl
        b = split_bounds_sec(self.cfg)
        exp = np.where(self.sec < b["train"][1], "train", np.where(self.sec < b["val"][1], "val", "test"))
        mismatch = int((exp != x.split.values).sum())
        contiguous = b["train"][1] == b["val"][0] and b["val"][1] == b["test"][0]
        pl = [p for p in self.d["planted"] if p.get("key_txn_id")]
        key_split = x.set_index("txn_id").split.reindex([p["key_txn_id"] for p in pl])
        planted_in_test = bool((key_split == "test").all())
        fr = x[x.is_fraud == 1]
        span = fr.groupby("case_id").split.nunique()
        det = dict(split_mismatch=mismatch, contiguous=contiguous, planted_keys_in_test=planted_in_test,
                   cases_spanning_3_splits=int((span >= 3).sum()),
                   fraud_rows_per_split=fr.split.value_counts().to_dict(),
                   rows_per_split=x.split.value_counts().to_dict())
        return mismatch == 0 and contiguous and planted_in_test and det["cases_spanning_3_splits"] == 0, det

    # ------------------------------------------------------------------ T13
    def t13_planted(self):
        x = self.txl.set_index("txn_id")
        pl = {p["id"]: p for p in self.d["planted"]}
        det, ok = {}, True
        signup = self.cust.set_index("wallet_id").signup_ts
        for k, p in pl.items():
            if k == "SC-06":
                continue
            good = p.get("key_txn_id") is not None and p.get("key_ok") and x.loc[p["key_txn_id"], "status"] == "SUCCESS"
            det[f"{k}_key_success"] = bool(good)
            ok &= bool(good)
        tx = self.txl

        def key(k):
            return x.loc[pl[k]["key_txn_id"]]
        # SC-03: 2-day-old collector, exactly 14 distinct first-time senders in the previous 3 h
        r = key("SC-03")
        col = r.receiver_id
        age = (r.ts - signup[col]).total_seconds() / DAY
        win = tx[(tx.receiver_id == col) & (tx.ts < r.ts) & (tx.ts >= r.ts - pd.Timedelta(hours=3)) & (tx.status == "SUCCESS")]
        det["SC-03_collector_age_days"] = round(age, 2)
        det["SC-03_senders_last_3h"] = int(win.sender_id.nunique())
        ok &= 1.9 <= age <= 2.2 and det["SC-03_senders_last_3h"] == 14
        # SC-01: SIM swap minutes before a 48,000 drain; mule cash-outs within the 30k cap
        r = key("SC-01")
        ev = self.d["account_events"]
        sw = ev[(ev.case_id == "SC-01") & (ev.event_type == "SIM_SWAP")].ts
        det["SC-01_amount"] = float(r.amount)
        det["SC-01_minutes_after_sim_swap"] = round((r.ts - sw.min()).total_seconds() / 60, 1) if len(sw) else None
        co = tx[(tx.case_id == "SC-01") & (tx.txn_type == "CASH_OUT")]
        det["SC-01_cashouts"] = co.amount.tolist()
        ok &= r.amount == 48000 and det["SC-01_minutes_after_sim_swap"] == 15 and (co.amount <= 30000).all()
        # SC-02: KYC2 victim, 4 sends within 30 s totalling 12,500
        s = tx[(tx.case_id == "SC-02") & (tx.fraud_role == "takeover_drain")]
        kyc = self.cust.set_index("wallet_id").kyc_level
        det["SC-02_victim_kyc"] = kyc[s.sender_id.iloc[0]]
        det["SC-02_total"] = float(s.amount.sum())
        det["SC-02_window_s"] = (s.ts.max() - s.ts.min()).total_seconds()
        ok &= det["SC-02_victim_kyc"] == "KYC2" and det["SC-02_total"] == 12500 and det["SC-02_window_s"] <= 30
        # SC-04: aged dormant mule, hop delays 4/6/9 min
        r = key("SC-04")
        a1 = r.sender_id
        det["SC-04_aged_mule_age_days"] = int((r.ts - signup[a1]).total_seconds() / DAY)
        quiet = tx[((tx.sender_id == a1) | (tx.receiver_id == a1)) & (tx.ts < r.ts - pd.Timedelta(minutes=10))]
        det["SC-04_aged_mule_prior_rows"] = int(len(quiet))
        ok &= det["SC-04_aged_mule_age_days"] >= 400 and det["SC-04_aged_mule_prior_rows"] == 0
        # SC-05: 60+ USSD victim, cash-in 18 min before the send
        r = key("SC-05")
        c = self.cust.set_index("wallet_id").loc[r.sender_id]
        ci = tx[(tx.receiver_id == r.sender_id) & (tx.txn_type == "CASH_IN") & (tx.ts <= r.ts)].ts.max()
        det["SC-05_victim"] = f"{c.age_band}/{c.channel}"
        det["SC-05_cashin_minutes_before"] = round((r.ts - ci).total_seconds() / 60, 1)
        ok &= c.age_band == "60+" and c.channel == "USSD" and det["SC-05_cashin_minutes_before"] == 18
        # SC-07: third card top-up rejected by the add-money limit
        am = tx[(tx.case_id == "SC-07") & (tx.txn_type == "ADD_MONEY")].sort_values("ts")
        det["SC-07_add_money_status"] = am.status.tolist()
        ok &= am.status.tolist() == ["SUCCESS", "SUCCESS", "FAILED"]
        # SC-06: rogue agent episode covers days 54-57
        at = self.d["agent_truth"].set_index("agent_id")
        ag = pl["SC-06"]["agent"]
        det["SC-06_agent_episodes"] = at.episodes.get(ag, "")
        ok &= "54-57" in str(det["SC-06_agent_episodes"])
        # SC-08: buyer #1's 16268 complaint is on file before buyer #7 pays (feedback loop)
        r = key("SC-08")
        cps = self.d["complaints"]
        before = cps[(cps.reported_wallet_id == r.receiver_id) & (cps.ts < r.ts)]
        det["SC-08_complaints_before_key"] = int(len(before))
        ok &= len(before) >= 1
        # SB-05: remittance lands 20 min before the cash-out
        r = key("SB-05")
        rem = tx[(tx.receiver_id == r.sender_id) & (tx.txn_type == "REMITTANCE_IN") & (tx.ts <= r.ts)].ts.max()
        det["SB-05_minutes_after_remittance"] = round((r.ts - rem).total_seconds() / 60, 1)
        ok &= det["SB-05_minutes_after_remittance"] == 20
        return bool(ok), det

    # ------------------------------------------------------------------ T14
    @staticmethod
    def t14_repro(cfg_path=None):
        from src.datagen.generate import build

        def h(seed):
            cfg = load_config(cfg_path, scale=0.03, seed=seed)
            out = build(cfg, verbose=False)
            b = pd.util.hash_pandas_object(out["transactions"], index=False).values.tobytes()
            b += pd.util.hash_pandas_object(out["labels"], index=False).values.tobytes()
            return hashlib.sha256(b).hexdigest()[:16]
        a, b, c = h(42), h(42), h(43)
        return a == b and a != c, dict(seed42_run1=a, seed42_run2=b, seed43=c)

    def run(self, skip_repro=False, cfg_path=None):
        tests = [("T1", "schema & keys", self.t1_schema), ("T2", "referential integrity", self.t2_refs),
                 ("T3", "balance conservation", self.t3_balances), ("T4", "KYC limits", self.t4_limits),
                 ("T5", "temporal realism", self.t5_temporal), ("T6", "volume & mix", self.t6_volume),
                 ("T7", "amount realism", self.t7_amounts), ("T8", "fraud prevalence & spread", self.t8_prevalence),
                 ("T9", "label consistency", self.t9_labels), ("T10", "scenario signatures", self.t10_signatures),
                 ("T11", "anti-shortcut", self.t11_shortcuts), ("T12", "split integrity", self.t12_splits),
                 ("T13", "planted scenarios", self.t13_planted)]
        if not skip_repro:
            tests.append(("T14", "reproducibility", lambda: self.t14_repro(cfg_path)))
        res = []
        for tid, name, fn in tests:
            try:
                ok, det = fn()
            except Exception as e:                      # a crashing check is a failing check
                ok, det = False, {"error": f"{type(e).__name__}: {e}"}
            res.append(dict(id=tid, name=name, passed=bool(ok), details=det))
        return res
