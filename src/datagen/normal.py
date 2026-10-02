"""Vectorised 'normal life' event candidates.

Produces intended events only; the ledger (engine.py) later enforces balances and KYC
limits, inserts cash-ins when a customer is short, and records the final rows.
"""
from __future__ import annotations

import numpy as np

from src.common.config import DAY
from .world import A, CH, MERCHANT_CATS, T, World

RATES = {  # expected events per active day, before the per-customer activity multiplier
    "salaried":          dict(SEND_MONEY=.25, CASH_OUT=.08, CASH_IN=.05, PAYMENT=.24, BILL_PAY=.04, MOBILE_RECHARGE=.22, ADD_MONEY=.06),
    "garment_worker":    dict(SEND_MONEY=.16, CASH_OUT=.09, CASH_IN=.04, PAYMENT=.08, BILL_PAY=.01, MOBILE_RECHARGE=.20, ADD_MONEY=.00),
    "small_business":    dict(SEND_MONEY=.34, CASH_OUT=.12, CASH_IN=.15, PAYMENT=.20, BILL_PAY=.04, MOBILE_RECHARGE=.20, ADD_MONEY=.05),
    "student":           dict(SEND_MONEY=.18, CASH_OUT=.08, CASH_IN=.06, PAYMENT=.16, BILL_PAY=.01, MOBILE_RECHARGE=.30, ADD_MONEY=.01),
    "remittance_family": dict(SEND_MONEY=.14, CASH_OUT=.07, CASH_IN=.03, PAYMENT=.12, BILL_PAY=.03, MOBILE_RECHARGE=.15, ADD_MONEY=.01),
    "homemaker":         dict(SEND_MONEY=.10, CASH_OUT=.05, CASH_IN=.05, PAYMENT=.10, BILL_PAY=.03, MOBILE_RECHARGE=.15, ADD_MONEY=.00),
    "farmer_rural":      dict(SEND_MONEY=.08, CASH_OUT=.06, CASH_IN=.06, PAYMENT=.05, BILL_PAY=.01, MOBILE_RECHARGE=.12, ADD_MONEY=.00),
    "gig_rider":         dict(SEND_MONEY=.22, CASH_OUT=.14, CASH_IN=.08, PAYMENT=.12, BILL_PAY=.01, MOBILE_RECHARGE=.25, ADD_MONEY=.01),
}
RATE_TYPES = ["SEND_MONEY", "CASH_OUT", "CASH_IN", "PAYMENT", "BILL_PAY", "MOBILE_RECHARGE", "ADD_MONEY"]
RECHARGE_AMTS = np.array([20, 30, 49, 50, 99, 100, 149, 200, 300, 500])
RECHARGE_P = np.array([.06, .05, .10, .12, .10, .20, .08, .14, .08, .07])
SALAMI_AMTS = np.array([100, 200, 500, 1000, 2000])
SALAMI_P = np.array([.25, .30, .30, .12, .03])


def _pad(lists, fill=-1):
    m = max((len(x) for x in lists), default=1) or 1
    out = np.full((len(lists), m), fill, dtype=np.int64)
    cnt = np.zeros(len(lists), dtype=np.int64)
    for i, x in enumerate(lists):
        out[i, :len(x)] = x
        cnt[i] = len(x)
    return out, cnt


def round_human(x: np.ndarray, rng) -> np.ndarray:
    """People type round amounts: 500, 1000, 2500 ... small amounts end in 0."""
    r = rng.random(len(x))
    out = np.where(r < 0.55, np.round(x, -2), np.where(r < 0.8, np.round(x / 500) * 500, np.round(x, -1)))
    out = np.where(x < 400, np.round(x, -1), out)
    return np.maximum(out, 10.0)


class NormalGenerator:
    def __init__(self, world: World, cfg: dict, rng: np.random.Generator):
        self.w, self.cfg, self.rng = world, cfg, rng
        w = world
        self.NC = w.n_normal_customers
        n = self.NC
        self.seg = np.array([w.segments.index(s) for s in w.c_seg[:n]])
        self.act = np.array(w.c_act[:n])
        self.income = np.array(w.c_income[:n])
        self.kyc = np.array(w.c_kyc[:n])
        self.chan = np.array(w.c_chan[:n])
        self.area = np.array(w.c_area[:n])
        self.signup = np.array(w.c_signup_ts[:n], dtype=np.int64)
        self.hmu = np.array(w.c_hmu[:n])
        self.hsig = np.array(w.c_hsig[:n])
        self.acct_area = np.array(w.acct_area)
        self.D = w.n_days
        self.days = w.start + np.arange(self.D) * np.timedelta64(1, "D")
        dt = self.days.astype("datetime64[D]")
        self.dom = (dt - dt.astype("datetime64[M]")).astype(int) + 1
        self.month = dt.astype("datetime64[M]").astype(int)
        self.wday = (dt.astype("datetime64[D]").view("int64") - 4) % 7      # 0 = Monday (1970-01-01 was Thu)
        self.eid = np.array(cfg["world"]["eid_days"]) - 1
        lim = cfg["limits"]
        self.cap = {lt: np.where(self.kyc == 2, lim["KYC2"][lt]["per_txn"], lim["KYC1"][lt]["per_txn"])
                    for lt in ("send_money", "cash_out", "cash_in", "payment", "add_money")}
        self.H, self.Hn = _pad([x for x in w.c_home_agents[:n]])
        self.M, self.Mn = _pad([x for x in w.c_merch[:n]])
        self.Ct, self.Ctn = _pad([x for x in w.c_contacts[:n]])
        cw = np.zeros(self.Ct.shape)
        for i, ws in enumerate(w.c_cweights[:n]):
            cw[i, :len(ws)] = ws
        self.Ccum = np.cumsum(cw, axis=1)
        self.Ccum[:, -1] = np.maximum(self.Ccum[:, -1], 1.0)
        self.agent_pool, self.agent_pool_n = _pad([w.agents_in_area[a] or w.agents for a in range(w.n_areas)])
        self.merch_pool, self.merch_pool_n = _pad([w.merchants_in_area[a] or w.merchants for a in range(w.n_areas)])
        cust_by_area = [np.flatnonzero(self.area == a) for a in range(w.n_areas)]
        self.cust_pool, self.cust_pool_n = _pad([w.C0 + x for x in cust_by_area])
        sb = self.seg == w.segments.index("small_business")
        self.shop_pool, self.shop_pool_n = _pad([w.C0 + np.flatnonzero(sb & (self.area == a)) for a in range(w.n_areas)])
        self.merch_cat = w.merchant_cat
        self.out = []

    # ---------------------------------------------------------------- helpers
    def _emit(self, ts, typ, src, dst, amount, area=None, dev=None):
        n = len(ts)
        if n == 0:
            return
        self.out.append(dict(ts=np.asarray(ts, np.int64), typ=np.full(n, typ, np.int16) if np.isscalar(typ) else np.asarray(typ, np.int16),
                             src=np.asarray(src, np.int64), dst=np.asarray(dst, np.int64),
                             amount=np.asarray(amount, np.float64),
                             area=np.full(n, -1, np.int64) if area is None else np.asarray(area, np.int64),
                             dev=np.full(n, -1, np.int64) if dev is None else np.asarray(dev, np.int64)))

    def _hours(self, c, kind="personal"):
        rng = self.rng
        n = len(c)
        h = self.hmu[c] + self.hsig[c] * rng.standard_normal(n)
        mix = rng.random(n) < 0.12
        h[mix] = rng.uniform(7.5, 23.5, mix.sum())
        h = np.mod(h, 24)
        if kind == "agent":                                    # agent shops: ~08-22, rare edges
            bad = (h < 8) | (h >= 22)
            nb = bad.sum()
            edge = rng.random(nb) < 0.04
            h[bad] = np.where(edge, rng.choice([7.3, 22.2], nb) + rng.uniform(0, 0.6, nb), rng.uniform(8.5, 21.5, nb))
        elif kind == "bill":
            bad = (h < 7) | (h >= 23.5)
            h[bad] = rng.uniform(9, 22, bad.sum())
        return h

    def _ts(self, d, h):
        return d.astype(np.int64) * DAY + (h * 3600).astype(np.int64) + self.rng.integers(0, 60, len(d))

    def _pick_agent(self, c):
        rng = self.rng
        n = len(c)
        k = self.Hn[c]
        u = rng.random(n)
        idx = np.where(k == 1, 0, np.where(k == 2, (u > 0.78).astype(int), np.select([u < 0.7, u < 0.9], [0, 1], 2)))
        ag = self.H[c, idx]
        roam = rng.random(n) < 0.10
        a = self.area[c[roam]]
        ag[roam] = self.agent_pool[a, (rng.random(roam.sum()) * self.agent_pool_n[a]).astype(int)]
        return ag

    def _pick_contact(self, c):
        u = self.rng.random(len(c))
        idx = (self.Ccum[c] < u[:, None]).sum(1)
        idx = np.minimum(idx, np.maximum(self.Ctn[c] - 1, 0))
        dst = self.Ct[c, idx]
        dst[self.Ctn[c] == 0] = -1
        return dst

    def _random_customer(self, c, same_area_p=0.6):
        rng = self.rng
        n = len(c)
        same = rng.random(n) < same_area_p
        out = self.w.C0 + rng.integers(0, self.NC, n)
        a = self.area[c[same]]
        out[same] = self.cust_pool[a, (rng.random(same.sum()) * self.cust_pool_n[a]).astype(int)]
        return out

    def _travel_area(self, c):
        a = self.area[c].copy()
        tr = self.rng.random(len(c)) < 0.07
        a[tr] = self.rng.choice(self.w.n_areas, tr.sum(), p=self.w.area_w)
        return a

    # ---------------------------------------------------------------- day factors
    def _day_factors(self):
        D = self.D
        f = {t: np.ones(D) for t in RATE_TYPES}
        fri_sat = np.isin(self.wday, [4, 5])
        f["SEND_MONEY"][fri_sat] *= 1.15
        f["PAYMENT"][fri_sat] *= 1.10
        f["CASH_OUT"][self.wday == 4] *= 0.9
        early = self.dom <= 7
        for t, m in (("SEND_MONEY", 1.3), ("CASH_OUT", 1.35), ("PAYMENT", 1.2), ("CASH_IN", 0.9)):
            f[t][early] *= m
        mid = (self.dom >= 10) & (self.dom <= 20)
        f["BILL_PAY"][mid] *= 2.0
        f["BILL_PAY"][~mid] *= 0.5
        if len(self.eid):
            pre = np.arange(max(0, self.eid.min() - 4), self.eid.min())
            for t, m in (("PAYMENT", 1.8), ("CASH_OUT", 1.5), ("SEND_MONEY", 1.6), ("CASH_IN", 1.3)):
                f[t][pre] *= m
            for t, m in (("SEND_MONEY", 2.6), ("PAYMENT", 0.6), ("CASH_OUT", 0.5), ("CASH_IN", 0.5), ("MOBILE_RECHARGE", 1.3)):
                f[t][self.eid] *= m
        return f

    # ---------------------------------------------------------------- main
    def generate(self) -> dict:
        rng, w, cfg = self.rng, self.w, self.cfg
        NC, D = self.NC, self.D
        dayf = self._day_factors()
        sday = self.signup // DAY
        dgrid = np.arange(D)[None, :]
        alive = (dgrid > sday[:, None]).astype(float) + 0.5 * (dgrid == sday[:, None])
        segs = w.segments
        Ls = {}
        for t in RATE_TYPES:
            r = np.array([RATES[s][t] for s in segs])[self.seg] * self.act
            Ls[t] = r[:, None] * dayf[t][None, :] * alive
        expected = sum(L.sum() for L in Ls.values())
        target = cfg["world"]["target_txn_per_customer_day"] * NC * D * 0.87   # rest: inflows, top-ups, follow-ups
        k = target / expected
        for t in RATE_TYPES:
            counts = rng.poisson(Ls[t] * k)
            ci, di = np.nonzero(counts)
            reps = counts[ci, di]
            c = np.repeat(ci, reps)
            d = np.repeat(di, reps)
            getattr(self, "_gen_" + t.lower())(c, d)
        self._salary_and_remittance()
        self._fcommerce_sellers()
        self._bank_topups()
        self._welcome_inflows()
        self._account_events()
        ev = {key: np.concatenate([o[key] for o in self.out]) for key in self.out[0]}
        # drop anything before the receiving/sending customer exists or after the window
        ok = (ev["ts"] >= 0) & (ev["ts"] < D * DAY)
        signup_all = np.full(len(w.ids), -10**12, dtype=np.int64)
        signup_all[w.C0:w.C0 + NC] = self.signup
        ok &= ev["ts"] >= signup_all[np.maximum(ev["src"], 0)] + 300
        ok &= ev["ts"] >= signup_all[np.maximum(ev["dst"], 0)] + 300
        ok &= (ev["src"] != ev["dst"]) | (ev["typ"] >= 100)      # account events have src == dst
        ev = {key: v[ok] for key, v in ev.items()}
        order = np.argsort(ev["ts"], kind="stable")
        return {key: v[order] for key, v in ev.items()}

    # ---------------------------------------------------------------- per type
    def _gen_send_money(self, c, d):
        rng, w = self.rng, self.w
        n = len(c)
        ts = self._ts(d, self._hours(c))
        dst = self._pick_contact(c)
        new = (rng.random(n) < 0.07) | (dst < 0)
        dst[new] = self._random_customer(c[new])
        med = np.clip(self.income[c] * 0.035, 150, 5000)
        amt = round_human(med * rng.lognormal(0, 0.85, n), rng)
        big = rng.random(n) < 0.012                             # rent advance / hospital / land: big one-offs
        dst[big] = self._random_customer(c[big], 0.4)
        amt[big] = round_human(amt[big] * rng.uniform(4, 12, big.sum()), rng)
        eid = np.isin(d, self.eid) & (rng.random(n) < 0.7)
        amt[eid] = rng.choice(SALAMI_AMTS, eid.sum(), p=SALAMI_P)
        amt = np.minimum(amt, self.cap["send_money"][c])
        self._emit(ts, T["SEND_MONEY"], w.C0 + c, dst, amt, self._travel_area(c))
        self._receiver_followups(ts, dst, amt)

    def _receiver_followups(self, ts, dst, amt):
        """Legit pass-through: family hubs forward money within minutes; some receivers cash out
        soon after (students, homemakers, day labourers). Hard negatives for mule features."""
        rng, w = self.rng, self.w
        ci = dst - w.C0
        ok = (ci >= 0) & (ci < self.NC) & (amt >= 500)
        hub = np.zeros(len(dst), bool)
        hub[ok] = np.array(w.c_hub)[ci[ok]]
        fwd = hub & (rng.random(len(dst)) < 0.6)
        if fwd.any():
            c = ci[fwd]
            to = self._pick_contact(c)
            good = (to >= 0) & (to != dst[fwd])
            t2 = ts[fwd] + (rng.uniform(5, 90, fwd.sum()) * 60).astype(np.int64)
            a2 = np.minimum(np.round(amt[fwd] * rng.uniform(0.5, 1.0, fwd.sum()), -1), self.cap["send_money"][c])
            self._emit(t2[good], T["SEND_MONEY"], w.C0 + c[good], to[good], a2[good], self.area[c[good]])
        segs = np.array(w.c_seg[:self.NC])
        quick = ok & ~hub
        quick[ok] &= np.isin(segs[ci[ok]], ["student", "homemaker", "garment_worker", "farmer_rural", "gig_rider"])
        quick &= rng.random(len(dst)) < 0.18
        if quick.any():
            c = ci[quick]
            t2 = self._agent_hours_after(ts[quick], 0.3, 4)
            a2 = np.minimum(np.round(amt[quick] * rng.uniform(0.6, 1.0, quick.sum()), -2), self.cap["cash_out"][c])
            ag = self._pick_agent(c)
            m = a2 >= 100
            self._emit(t2[m], T["CASH_OUT"], w.C0 + c[m], ag[m], a2[m], self.acct_area[ag[m]])

    def _gen_cash_out(self, c, d):
        rng, w = self.rng, self.w
        n = len(c)
        ts = self._ts(d, self._hours(c, "agent"))
        ag = self._pick_agent(c)
        med = np.clip(self.income[c] * 0.10, 300, 10000)
        amt = med * rng.lognormal(0, 0.7, n)
        amt = np.where(rng.random(n) < 0.7, np.round(amt, -2), np.round(amt / 500) * 500)
        amt = np.minimum(np.maximum(amt, 100), self.cap["cash_out"][c])
        self._emit(ts, T["CASH_OUT"], w.C0 + c, ag, amt, self.acct_area[ag])

    def _gen_cash_in(self, c, d):
        rng, w = self.rng, self.w
        n = len(c)
        ts = self._ts(d, self._hours(c, "agent"))
        ag = self._pick_agent(c)
        med = np.clip(self.income[c] * 0.10, 300, 12000)
        amt = med * rng.lognormal(0, 0.7, n)
        amt = np.where(rng.random(n) < 0.6, np.round(amt, -2), np.round(amt / 500) * 500)
        amt = np.minimum(np.maximum(amt, 100), self.cap["cash_in"][c])
        self._emit(ts, T["CASH_IN"], ag, w.C0 + c, amt, self.acct_area[ag])

    def _gen_payment(self, c, d):
        rng, w = self.rng, self.w
        n = len(c)
        ts = self._ts(d, self._hours(c))
        u = rng.random(n)
        own = (u < 0.85) & (self.Mn[c] > 0)
        m = self.merch_pool[self.area[c], (rng.random(n) * self.merch_pool_n[self.area[c]]).astype(int)]
        pick = (rng.random(n) * np.maximum(self.Mn[c], 1)).astype(int)
        m[own] = self.M[c[own], pick[own]]
        mloc = m - w.merchants[0]
        cats = self.merch_cat[mloc]
        med = np.array([MERCHANT_CATS[x][0] for x in cats])
        sig = np.array([MERCHANT_CATS[x][1] for x in cats])
        amt = np.maximum(np.round(med * np.exp(sig * rng.standard_normal(n))), 20.0)
        amt = np.minimum(amt, self.cap["payment"][c])
        # paying a shop's *personal* wallet via Send Money: legit fan-in for small businesses
        a = self.area[c]
        shop = (rng.random(n) < 0.25) & (self.shop_pool_n[a] > 0)
        z = rng.zipf(1.6, shop.sum()) - 1
        sidx = np.minimum(z, self.shop_pool_n[a[shop]] - 1)
        shop_dst = self.shop_pool[a[shop], sidx]
        typ = np.full(n, T["PAYMENT"], np.int16)
        dst = m.copy()
        typ[shop] = T["SEND_MONEY"]
        dst[shop] = shop_dst
        area = np.where(shop, a, self.acct_area[m])
        self._emit(ts, typ, w.C0 + c, dst, amt, area)

    def _gen_bill_pay(self, c, d):
        rng, w = self.rng, self.w
        n = len(c)
        ts = self._ts(d, self._hours(c, "bill"))
        urban = w.area_urban[self.area[c]]
        bu = np.array(w.billers[:8])
        pu = np.array([.34, 0, .16, .12, .14, .12, .06, .06])
        pr = np.array([0, .55, 0, 0, .05, .2, .1, .1])
        bil = np.where(urban, rng.choice(bu, n, p=pu / pu.sum()), rng.choice(bu, n, p=pr / pr.sum()))
        amt = np.maximum(np.round(900 * rng.lognormal(0, 0.6, n)), 50.0)
        self._emit(ts, T["BILL_PAY"], w.C0 + c, bil, amt, self.area[c])

    def _gen_mobile_recharge(self, c, d):
        rng, w = self.rng, self.w
        ts = self._ts(d, self._hours(c))
        op = np.array(w.c_operator[:self.NC])[c]
        bil = np.array(w.billers[8:12])[op]
        amt = rng.choice(RECHARGE_AMTS, len(c), p=RECHARGE_P).astype(float)
        self._emit(ts, T["MOBILE_RECHARGE"], w.C0 + c, bil, amt, self._travel_area(c))

    def _gen_add_money(self, c, d):
        rng, w = self.rng, self.w
        n = len(c)
        ussd = self.chan[c] == CH["USSD"]
        c, d = c[~ussd], d[~ussd]
        n = len(c)
        ts = self._ts(d, self._hours(c))
        src = np.where(rng.random(n) < 0.85, w.ext["X_BANK"], w.ext["X_CARD"])
        amt = np.maximum(np.round(3000 * rng.lognormal(0, 0.7, n) / 500) * 500, 500)
        amt = np.minimum(amt, self.cap["add_money"][c])
        self._emit(ts, T["ADD_MONEY"], src, w.C0 + c, amt, self.area[c])

    def _salary_and_remittance(self):
        rng, w = self.rng, self.w
        sal_day = np.array(w.c_salary_day[:self.NC])
        segs = np.array(w.c_seg[:self.NC])
        via_wallet = np.where(segs == "garment_worker", 0.85, 0.6)
        c_list, ts_list = [], []
        for month in np.unique(self.month):
            mdays = np.flatnonzero(self.month == month)
            dom = self.dom[mdays]
            has = (sal_day > 0) & (rng.random(self.NC) < via_wallet)
            for ci in np.flatnonzero(has):
                hit = mdays[dom == sal_day[ci]]
                if len(hit):
                    c_list.append(ci)
                    ts_list.append(int(hit[0]) * DAY + int(rng.uniform(9, 17) * 3600))
        c = np.array(c_list, dtype=np.int64)
        ts = np.array(ts_list, dtype=np.int64)
        amt = np.round(self.income[c] * rng.uniform(0.97, 1.03, len(c)), -1)
        self._emit(ts, T["SALARY"], np.full(len(c), w.ext["X_EMPLOYER"]), w.C0 + c, amt, self.area[c])
        # follow-ups: send home + cash-out
        garment = segs[c] == "garment_worker"
        send = rng.random(len(c)) < np.where(garment, 0.85, 0.35)
        frac = np.where(garment, rng.uniform(0.4, 0.6, len(c)), rng.uniform(0.2, 0.4, len(c)))
        cs = c[send]
        dst = np.array([w.c_contacts[i][0] if w.c_contacts[i] else -1 for i in cs], dtype=np.int64)
        ok = dst >= 0
        tsend = ts[send] + (rng.uniform(2, 30, len(cs)) * 3600).astype(np.int64)
        samt = np.minimum(np.round(amt[send] * frac[send], -2), self.cap["send_money"][cs])
        self._emit(tsend[ok], T["SEND_MONEY"], w.C0 + cs[ok], dst[ok], samt[ok], self.area[cs[ok]])
        co = rng.random(len(c)) < 0.5
        cc = c[co]
        tco = self._agent_hours_after(ts[co], 1, 48)
        camt = np.minimum(np.round(amt[co] * rng.uniform(0.2, 0.5, len(cc)), -2), self.cap["cash_out"][cc])
        ag = self.H[cc, 0]
        self._emit(tco, T["CASH_OUT"], w.C0 + cc, ag, camt, self.acct_area[ag])

        # remittance families: 1-2 inflows a month, usually cashed out soon after (a NORMAL pattern)
        rem = np.flatnonzero(segs == "remittance_family")
        c_list, ts_list = [], []
        for month in np.unique(self.month):
            mdays = np.flatnonzero(self.month == month)
            k = rng.poisson(1.1, len(rem))
            for ci, kk in zip(rem, k):
                for _ in range(int(kk)):
                    c_list.append(ci)
                    ts_list.append(int(rng.choice(mdays)) * DAY + int(rng.uniform(8, 23) * 3600))
        c = np.array(c_list, dtype=np.int64)
        ts = np.array(ts_list, dtype=np.int64)
        amt = np.round(22000 * rng.lognormal(0, 0.45, len(c)) * 1.025)
        self._emit(ts, T["REMITTANCE_IN"], np.full(len(c), w.ext["X_REMIT"]), w.C0 + c, amt, self.area[c])
        co = rng.random(len(c)) < 0.8
        cc, tt, aa = c[co], ts[co], amt[co]
        frac = rng.uniform(0.5, 1.0, len(cc))
        want = np.round(aa * frac, -2)
        cap = self.cap["cash_out"][cc]
        first = np.minimum(want, cap - 500)
        t1 = self._agent_hours_after(tt, 10 / 60, 36)
        ag = self.H[cc, 0]
        self._emit(t1, T["CASH_OUT"], w.C0 + cc, ag, first, self.acct_area[ag])
        rest = want - first
        more = rest >= 1000
        t2 = t1[more] + DAY + (rng.uniform(-2, 3, more.sum()) * 3600).astype(np.int64)
        self._emit(t2, T["CASH_OUT"], w.C0 + cc[more], ag[more], np.minimum(rest[more], cap[more] - 500), self.acct_area[ag[more]])

    def _fcommerce_sellers(self):
        """Legit online sellers (the look-alike of collectors / fake sellers): orders from mostly
        first-time buyers all over the country, cash-out most evenings at their agent."""
        rng, w = self.rng, self.w
        segs = np.array(w.c_seg[:self.NC])
        pool = np.flatnonzero(np.isin(segs, ["small_business", "student", "homemaker"]))
        n = int(self.NC * self.cfg["population"].get("fcommerce_seller_share", 0.0))
        if n == 0 or not len(pool):
            return
        sellers = rng.choice(pool, min(n, len(pool)), replace=False)
        lam = rng.uniform(1.0, 6.0, len(sellers))
        sday = np.maximum(self.signup[sellers] // DAY, 0)
        for s, l, d0 in zip(sellers, lam, sday):
            days = np.arange(int(d0) + 1, self.D)
            k = rng.poisson(l, len(days))
            if k.sum() == 0:
                continue
            d = np.repeat(days, k)
            m = len(d)
            ts = d * DAY + (rng.uniform(10, 23.5, m) * 3600).astype(np.int64)
            repeat = rng.random(m) < 0.15
            buyers = w.C0 + rng.integers(0, self.NC, m)
            if repeat.any() and self.Ctn[s] > 0:
                buyers[repeat] = self.Ct[s, rng.integers(0, self.Ctn[s], repeat.sum())]
            amt = np.maximum(np.round(1200 * rng.lognormal(0, 0.6, m) / 50) * 50, 150)
            self._emit(ts, T["SEND_MONEY"], buyers, np.full(m, w.C0 + s), amt, self.area[buyers - w.C0])
            day_sum = np.bincount(d - days[0], weights=amt, minlength=len(days))
            co = (day_sum > 300) & (rng.random(len(days)) < 0.7)
            if co.any():
                cd = days[co]
                camt = np.minimum(np.round(day_sum[co] * rng.uniform(0.6, 0.95, co.sum()), -2), self.cap["cash_out"][s])
                tco = cd * DAY + (rng.uniform(20.5, 21.8, co.sum()) * 3600).astype(np.int64)
                ag = np.full(co.sum(), self.H[s, 0])
                self._emit(tco, T["CASH_OUT"], np.full(co.sum(), w.C0 + s), ag, camt, self.acct_area[ag])

    def _bank_topups(self):
        """Monthly 10-25k bank -> wallet moves (legit look-alike of card Add-Money fraud)."""
        rng, w = self.rng, self.w
        segs = np.array(w.c_seg[:self.NC])
        cand = np.flatnonzero((segs == "salaried") & (self.chan == CH["APP"]) & (self.kyc == 2))
        k = int(len(cand) * self.cfg["population"].get("bank_topup_share", 0.0))
        if k == 0:
            return
        who = rng.choice(cand, k, replace=False)
        c_list, ts_list = [], []
        for month in np.unique(self.month):
            mdays = np.flatnonzero(self.month == month)
            for c in who:
                d = int(rng.choice(mdays[:10] if len(mdays) > 10 else mdays))
                c_list.append(c)
                ts_list.append(d * DAY + int(rng.uniform(8, 24) * 3600))
        c = np.array(c_list, dtype=np.int64)
        ts = np.array(ts_list, dtype=np.int64)
        amt = rng.choice([10000, 15000, 20000, 24000, 25000], len(c)).astype(float)
        src = np.where(rng.random(len(c)) < 0.8, w.ext["X_BANK"], w.ext["X_CARD"])
        self._emit(ts, T["ADD_MONEY"], src, w.C0 + c, np.minimum(amt, self.cap["add_money"][c]), self.area[c])
        big = rng.random(len(c)) < 0.4                       # and part of it goes out soon after
        t2 = self._agent_hours_after(ts[big], 0.2, 6)
        ag = self.H[c[big], 0]
        self._emit(t2, T["CASH_OUT"], w.C0 + c[big], ag, np.round(amt[big] * rng.uniform(0.4, 0.9, big.sum()), -2),
                   self.acct_area[ag])

    def _agent_hours_after(self, ts, lo_h, hi_h):
        t = ts + (self.rng.uniform(lo_h, hi_h, len(ts)) * 3600).astype(np.int64)
        h = (t % DAY) / 3600
        late = h >= 21.5
        early = h < 8.5
        t = np.where(late, (t // DAY + 1) * DAY + (self.rng.uniform(9, 12, len(t)) * 3600).astype(np.int64), t)
        t = np.where(early, (t // DAY) * DAY + (self.rng.uniform(9, 12, len(t)) * 3600).astype(np.int64), t)
        return t

    def _welcome_inflows(self):
        rng, w = self.rng, self.w
        new = np.flatnonzero(self.signup >= 0)
        if not len(new):
            return
        ts = self.signup[new] + (rng.uniform(0.3, 24, len(new)) * 3600).astype(np.int64)
        has_c = self.Ctn[new] > 0
        via_p2p = has_c & (rng.random(len(new)) < 0.6)
        src = np.where(via_p2p, self.Ct[new, 0], self._pick_agent(new))
        amt = np.round(rng.uniform(500, 3000, len(new)), -2)
        typ = np.where(via_p2p, T["SEND_MONEY"], T["CASH_IN"])
        self._emit(ts, typ, src, w.C0 + new, amt, self.area[new])

    def _account_events(self):
        """Legit device changes, SIM replacements and PIN resets (hard negatives for takeover)."""
        rng, w, pop = self.rng, self.w, self.cfg["population"]
        NC, D = self.NC, self.D
        for kind, p in (("DEVICE_CHANGE", pop["device_change_daily_prob"]), ("SIM_SWAP", pop["sim_swap_daily_prob"]),
                        ("PIN_RESET", 0.0004)):
            n = rng.poisson(NC * D * p)
            c = rng.integers(0, NC, n)
            d = rng.integers(0, D, n)
            ts = d * DAY + (rng.uniform(9, 23, n) * 3600).astype(np.int64)
            dev = np.full(n, -1, np.int64)
            if kind == "DEVICE_CHANGE":
                dev = np.array([w.new_device() for _ in range(n)], np.int64)
            self._emit(ts, A[kind], w.C0 + c, w.C0 + c, np.zeros(n), self.area[c], dev)
            if kind in ("DEVICE_CHANGE", "SIM_SWAP"):            # new phone / new SIM, then a bigger-than-usual move
                f = rng.random(n) < 0.25
                cf = c[f]
                t2 = ts[f] + (rng.uniform(0.1, 6, f.sum()) * 3600).astype(np.int64)
                to = self._pick_contact(cf)
                amt = np.minimum(round_human(self.income[cf] * rng.uniform(0.15, 0.6, f.sum()), rng),
                                 self.cap["send_money"][cf])
                ok = to >= 0
                self._emit(t2[ok], T["SEND_MONEY"], w.C0 + cf[ok], to[ok], amt[ok], self.area[cf[ok]])
            if kind == "SIM_SWAP":                              # many legit swaps come with a new phone
                f = rng.random(n) < 0.6
                t2 = ts[f] + (rng.uniform(0.5, 24, f.sum()) * 3600).astype(np.int64)
                dev2 = np.array([w.new_device() for _ in range(f.sum())], np.int64)
                self._emit(t2, A["DEVICE_CHANGE"], w.C0 + c[f], w.C0 + c[f], np.zeros(f.sum()), self.area[c[f]], dev2)


def generate_normal(world: World, cfg: dict, rng) -> dict:
    return NormalGenerator(world, cfg, rng).generate()
