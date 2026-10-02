"""Planted demo scenarios, all inside the TEST window so the demo runs on unseen data.

SC-xx = scams the system must catch; SB-xx = benign look-alikes it must NOT block.
Bands are the policy bands from config (ALLOW < 30 <= NUDGE < 60 <= STEP_UP < 80 <= HOLD).
Expected bands are checked against the trained model in reports/demo_scenarios.md; the data
properties (counts, ages, timings) are hard-checked by validation T13.

Fixes vs. the earlier draft spec: SC-02's victim is KYC2 (12,500 > KYC1 daily cap); SC-01's
two big cash-outs come from two different mules (each <= 30,000 cash-out cap); SB-05 is
expected ALLOW with NUDGE tolerated (it is a monthly routine for remittance families).
"""
from __future__ import annotations

import numpy as np

from src.common.config import DAY
from .engine import Ev
from .fraud import FraudPlanner, frac_of_balance, all_cashable
from .world import A, CH, T

H, MIN = 3600, 60


def at(day1: int, hh: int, mm: int = 0, ss: int = 0) -> int:
    return (day1 - 1) * DAY + hh * H + mm * MIN + ss


SPECS = {
    "SC-01": dict(kind="SC", scenario="S6", title="SIM-swap takeover of a business owner at 01:40",
                  expected="HOLD", acceptable=["STEP_UP", "HOLD"]),
    "SC-02": dict(kind="SC", scenario="S1", title="Agent-register harvest: OTP takeover drains 12,500 to 4 mules in 30 s",
                  expected="STEP_UP", acceptable=["STEP_UP", "HOLD"]),
    "SC-03": dict(kind="SC", scenario="S2", title="Collector wallet: 2 days old, 14 strangers paid it in 3 h; victim #15 about to send",
                  expected="STEP_UP", acceptable=["STEP_UP", "HOLD"]),
    "SC-04": dict(kind="SC", scenario="S3", title="Mule chain through a 400-day-old dormant account (hops of 4, 6, 9 min)",
                  expected="STEP_UP", acceptable=["STEP_UP", "HOLD"]),
    "SC-05": dict(kind="SC", scenario="S7", title="'Jail guard' pressure scam: 60+ USSD farmer cashes in 20,000 and sends it",
                  expected="NUDGE", acceptable=["NUDGE", "STEP_UP", "HOLD"]),
    "SC-06": dict(kind="SC", scenario="S4", title="Rogue agent: night cash-outs for the ring, ~8-10x peer volume",
                  expected="FLAGGED", acceptable=["FLAGGED"]),
    "SC-07": dict(kind="SC", scenario="S8", title="Stolen card: 2 x 25,000 Add Money at 03:10, cash-out 29,500 at 03:40",
                  expected="HOLD", acceptable=["STEP_UP", "HOLD"]),
    "SC-08": dict(kind="SC", scenario="S5", title="Fake phone seller: 9 advance payments in 3 days; buyer #1 already reported it to 16268",
                  expected="NUDGE", acceptable=["NUDGE", "STEP_UP", "HOLD"]),
    "SB-01": dict(kind="SB", scenario="NONE", title="Busy shop owner's personal wallet: 12 payers in a day",
                  expected="ALLOW", acceptable=["ALLOW", "NUDGE"]),
    "SB-02": dict(kind="SB", scenario="NONE", title="Legit new phone, then usual bill + 2,000 to mother",
                  expected="ALLOW", acceptable=["ALLOW", "NUDGE"]),
    "SB-03": dict(kind="SB", scenario="NONE", title="Rent advance: 35,000 to a new landlord, Friday 11:00, own phone",
                  expected="NUDGE", acceptable=["ALLOW", "NUDGE", "STEP_UP"]),
    "SB-04": dict(kind="SB", scenario="NONE", title="Student cashes out 4,900 twelve minutes after parent sends 5,000",
                  expected="ALLOW", acceptable=["ALLOW", "NUDGE"]),
    "SB-05": dict(kind="SB", scenario="NONE", title="Remittance family cashes out 29,500 twenty minutes after 48,250 lands",
                  expected="ALLOW", acceptable=["ALLOW", "NUDGE"]),
}


class Planter:
    def __init__(self, planner: FraudPlanner):
        self.p, self.sim, self.w, self.rng = planner, planner.sim, planner.w, planner.rng
        self.records = {k: dict(id=k, **v, key_row=None, key_ok=None, wallets={}, agent=None) for k, v in SPECS.items()}
        self.msisdn_seq = 0
        self.complaints = []            # scripted 16268 complaints: (ts, complainant, reported, capture-key)
        self.captured = {}              # capture-key -> ledger row

    # ------------------------------------------------------------------ helpers
    def special_msisdn(self):
        self.msisdn_seq += 1
        return self.msisdn_seq

    def key_cb(self, sid, inner=None):
        def cb(sim, ev, ok, row, amount):
            self.records[sid]["key_row"] = row
            self.records[sid]["key_ok"] = bool(ok)
            if inner:
                inner(sim, ev, ok, row, amount)
        return cb

    def capture(self, key):
        def cb(sim, ev, ok, row, amount):
            self.captured[key] = row
        return cb

    def case(self, sid, scen, ring, t0):
        self.p.cases[sid] = dict(case_id=sid, scenario=scen, ring=None if ring is None else ring.rid, t0=int(t0),
                                 split="test", victims=[], wallets=[], parent=None, _ring=ring, planted=True)
        return sid

    def pick(self, mask, weights=None, t0=at(51, 0)):
        got = self.p.pick_customers(1, t0, weights=weights, mask=mask, min_age_days=30)
        if not got:
            got = self.p.pick_customers(1, t0, weights=weights, min_age_days=30)
        self.p.reserve(got[0])
        return got[0]

    def quiet(self, acct, d0, d1):
        self.sim.quiet.setdefault(acct, []).append(((d0 - 1) * DAY, d1 * DAY))

    def wallet(self, sid, name, acct):
        self.records[sid]["wallets"][name] = self.w.ids[acct]

    def new_mule(self, sid, ring, signup, device=None, kyc=2):
        return self.p.new_wallet(signup, ring.area, device if device is not None else self.p.ring_device(ring),
                                 "mule", ring, sid, kyc=kyc, msisdn_special=self.special_msisdn())

    def agent_in_area(self, area):
        pool = self.w.agents_in_area.get(area) or self.w.agents
        return pool[0]

    # ------------------------------------------------------------------ setup (before random cases)
    def prepare_rogue(self):
        """SC-06's agent: force its test episode to days 54-57."""
        ring = self.p.rings[0]
        ring.episodes = [e for e in ring.episodes if e[0] < (self.p.split_days["test"][0]) * DAY] + [(at(54, 0), at(58, 0))]
        self.p.agent_truth[ring.rogue]["episodes"] = [(s // DAY + 1, e // DAY) for s, e in ring.episodes]
        self.records["SC-06"]["agent"] = self.w.ids[ring.rogue]
        return ring

    def plant_all(self):
        rogue_ring = self.p.rings[0]
        other_ring = self.p.rings[-1]
        self.sc01(rogue_ring)
        self.sc02(other_ring)
        self.sc03(rogue_ring)
        self.sc04(other_ring)
        self.sc05(other_ring)
        self.sc07(rogue_ring)
        self.sc08()
        self.sb01()
        self.sb02()
        self.sb03()
        self.sb04()
        self.sb05()

    # ------------------------------------------------------------------ SC
    def sc01(self, ring):
        sid, sim, p, w = "SC-01", self.sim, self.p, self.w
        t0 = at(54, 1, 40)
        self.case(sid, "S6", ring, t0)
        seg = p.c_seg
        v = self.pick((seg == "small_business") & (p.c_kyc == 2) & (p.c_chan == CH["APP"]) & (p.c_income > 50000))
        p.cases[sid]["victims"].append(v); p.tag(v, "victim", sid)
        self.quiet(v, 52, 54)
        ha = w.c_home_agents[w.cust_of(v)][0]
        sim.push(Ev(at(52, 18, 10), T["CASH_IN"], ha, v, amount=30000.0))
        sim.push(Ev(at(53, 17, 45), T["CASH_IN"], ha, v, amount=30000.0))
        sim.push(Ev(at(53, 20, 5), T["ADD_MONEY"], w.ext["X_BANK"], v, amount=25000.0))
        m1 = p.buy_account(t0, ring, "mule", sid, dormant=True, kyc2=True)
        m2 = self.new_mule(sid, ring, at(46, 15))
        m3 = self.new_mule(sid, ring, at(50, 11))
        dev = ring.devices[0]
        sim.push(Ev(t0, A["SIM_SWAP"], v, v, area=ring.area, channel=CH["SYSTEM"], label=("S6", sid, "sim_swap")))
        sim.push(Ev(at(54, 1, 52), A["DEVICE_CHANGE"], v, v, device=dev, area=ring.area, channel=CH["APP"],
                    label=("S6", sid, "takeover_login")))
        sim.push(Ev(at(54, 1, 53), A["PIN_RESET"], v, v, device=dev, area=ring.area, channel=CH["APP"],
                    label=("S6", sid, "pin_reset")))
        sim.push(Ev(at(54, 1, 55), T["SEND_MONEY"], v, m1, amount=48000.0, device=dev, channel=CH["APP"],
                    area=ring.area, label=("S6", sid, "takeover_drain"), cb=self.key_cb(sid)))
        sim.push(Ev(at(54, 2, 7), T["SEND_MONEY"], m1, m2, amount=47000.0, channel=CH["APP"], area=ring.area,
                    label=("S6", sid, "mule_hop")))
        sim.push(Ev(at(54, 2, 30), T["CASH_OUT"], m2, ring.rogue, amount=29000.0, channel=CH["APP"],
                    label=("S6", sid, "mule_cashout")))
        sim.push(Ev(at(54, 2, 41), T["SEND_MONEY"], m2, m3, amount=17000.0, channel=CH["APP"], area=ring.area,
                    label=("S6", sid, "mule_hop")))
        sim.push(Ev(at(54, 3, 5), T["CASH_OUT"], m3, ring.rogue, amount=16500.0, channel=CH["APP"],
                    label=("S6", sid, "mule_cashout")))
        for n, a in (("victim", v), ("aged_mule", m1), ("mule2", m2), ("mule3", m3)):
            self.wallet(sid, n, a)
        self.records[sid]["agent"] = w.ids[ring.rogue]

    def sc02(self, ring):
        sid, sim, p, w = "SC-02", self.sim, self.p, self.w
        t0 = at(53, 20, 14)
        self.case(sid, "S1", ring, t0)
        ha = p.harvest_agents[0]
        home = np.array([ha in hs for hs in w.c_home_agents[:len(p.c_seg)]])
        v = self.pick((p.c_seg == "salaried") & (p.c_kyc == 2) & (p.c_chan == CH["APP"]) & home)
        p.cases[sid]["victims"].append(v); p.tag(v, "victim", sid)
        p.cases[sid]["harvest_agent"] = w.ids[ha]
        self.quiet(v, 52, 53)
        sim.push(Ev(at(52, 11, 20), T["CASH_IN"], ha, v, amount=13000.0))
        devs = ring.devices[:2]
        mules = [self.new_mule(sid, ring, at(53, 9) - int(d * DAY), devs[i % 2]) for i, d in enumerate((3, 4, 5, 3.5))]
        dev = ring.devices[-1]
        sim.push(Ev(t0, A["DEVICE_CHANGE"], v, v, device=dev, area=ring.area, channel=CH["APP"],
                    label=("S1", sid, "takeover_login")))
        for i, (sec, amt) in enumerate(((8, 3000.0), (15, 3500.0), (22, 3000.0), (31, 3000.0))):
            m = mules[i]
            sim.push(Ev(t0 + sec, T["SEND_MONEY"], v, m, amount=amt, device=dev, channel=CH["APP"], area=ring.area,
                        label=("S1", sid, "takeover_drain"), cb=self.key_cb(sid) if i == 0 else None))
            ag = self.agent_in_area(ring.area)
            sim.push(Ev(t0 + int((20 + 12 * i) * MIN), T["CASH_OUT"], m, ag, amount_fn=all_cashable, channel=CH["APP"],
                        label=("S1", sid, "mule_cashout"), fit=True, min_amt=300))
        self.wallet(sid, "victim", v)
        self.records[sid]["agent"] = w.ids[ha]
        for i, m in enumerate(mules):
            self.wallet(sid, f"mule{i + 1}", m)

    def sc03(self, ring):
        sid, sim, p, w, rng = "SC-03", self.sim, self.p, self.w, self.rng
        t_sign = at(55, 10, 0)
        self.case(sid, "S2", ring, at(57, 9))
        col = p.new_wallet(t_sign, ring.area, ring.devices[1], "collector", ring, sid, kyc=2,
                           msisdn_special=self.special_msisdn())
        p.cases[sid]["variant"] = "job_fee"
        segw = np.where(np.isin(p.c_seg, ["student", "homemaker", "garment_worker"]), 3.0, 1.0)
        victims = p.pick_customers(15, at(57, 9), weights=segw, min_age_days=30)
        offs = np.sort(rng.uniform(10 * MIN, 2.95 * H, 14)).astype(int)   # 09:10-11:57, all inside the 3 h window
        amts = rng.choice([1500, 2000, 2500], 15)
        for i, v in enumerate(victims):
            p.reserve(v)
            p.cases[sid]["victims"].append(v); p.tag(v, "victim", sid)
            self.quiet(v, 56, 57)
            ha = w.c_home_agents[w.cust_of(v)][0]
            sim.push(Ev(at(56, 17) + i * 60, T["CASH_IN"], ha, v, amount=3000.0))
            t = at(57, 9) + int(offs[i]) if i < 14 else at(57, 12, 5)
            sim.push(Ev(t, T["SEND_MONEY"], v, col, amount=float(amts[i] if i < 14 else 2000),
                        label=("S2", sid, "victim_payment"), cb=self.key_cb(sid) if i == 14 else None))
        sim.push(Ev(at(57, 12, 40), T["CASH_OUT"], col, ring.rogue, amount_fn=all_cashable, channel=CH["APP"],
                    label=("S2", sid, "collector_cashout"), fit=True, min_amt=300))
        sim.push(Ev(at(57, 13, 20), T["CASH_OUT"], col, self.agent_in_area(ring.area), amount_fn=all_cashable,
                    channel=CH["APP"], label=("S2", sid, "collector_cashout"), fit=True, min_amt=300))
        self.wallet(sid, "collector", col)
        self.wallet(sid, "victim15", victims[-1])

    def sc04(self, ring):
        sid, sim, p, w = "SC-04", self.sim, self.p, self.w
        t0 = at(56, 15, 30)
        self.case(sid, "S3", ring, t0)
        v = self.pick((p.c_kyc == 2) & (p.c_chan == CH["APP"]) & (p.c_income > 20000))
        p.cases[sid]["victims"].append(v); p.tag(v, "victim", sid)
        self.quiet(v, 55, 56)
        ha = w.c_home_agents[w.cust_of(v)][0]
        sim.push(Ev(at(55, 19), T["CASH_IN"], ha, v, amount=10000.0))
        sim.push(Ev(at(55, 21), T["ADD_MONEY"], w.ext["X_BANK"], v, amount=15000.0))
        mask = (p.c_act < 0.35) & (p.c_signup < -400 * DAY) & (p.c_kyc == 2)
        got = p.pick_customers(1, t0, mask=mask) or p.pick_customers(1, t0, mask=(p.c_signup < -400 * DAY) & (p.c_kyc == 2))
        a1 = got[0]
        p.reserve(a1)
        sim.suppress_from[a1] = -1                     # silent for the whole window: dormant
        w.c_device[w.cust_of(a1)] = ring.devices[2 % len(ring.devices)]
        p.tag(a1, "mule", sid, ring); p.roles[a1].add("aged")
        m2 = self.new_mule(sid, ring, at(50, 14))
        m3 = self.new_mule(sid, ring, at(48, 10))
        dev = ring.devices[0]
        sim.push(Ev(t0, A["DEVICE_CHANGE"], v, v, device=dev, area=ring.area, channel=CH["APP"],
                    label=("S1", sid, "takeover_login")))
        sim.push(Ev(at(56, 15, 32), T["SEND_MONEY"], v, a1, amount=20000.0, device=dev, channel=CH["APP"],
                    area=ring.area, label=("S1", sid, "takeover_drain")))
        sim.push(Ev(at(56, 15, 36), T["SEND_MONEY"], a1, m2, amount=19500.0, channel=CH["APP"], area=ring.area,
                    label=("S3", sid, "mule_hop"), cb=self.key_cb(sid)))
        sim.push(Ev(at(56, 15, 42), T["SEND_MONEY"], m2, m3, amount=19000.0, channel=CH["APP"], area=ring.area,
                    label=("S3", sid, "mule_hop")))
        sim.push(Ev(at(56, 15, 51), T["CASH_OUT"], m3, self.agent_in_area(ring.area), amount=18500.0,
                    channel=CH["APP"], label=("S3", sid, "mule_cashout")))
        for n, a in (("victim", v), ("aged_mule", a1), ("mule2", m2), ("mule3", m3)):
            self.wallet(sid, n, a)

    def sc05(self, ring):
        sid, sim, p, w = "SC-05", self.sim, self.p, self.w
        t0 = at(52, 14, 2)
        self.case(sid, "S7", ring, t0)
        p.cases[sid]["variant"] = "jail_guard"
        v = self.pick((p.c_seg == "farmer_rural") & (p.c_chan == CH["USSD"]) & (p.c_kyc == 2) & (p.c_ageb >= 3))
        ci = w.cust_of(v)
        w.c_ageb[ci] = 4                               # 60+
        p.cases[sid]["victims"].append(v); p.tag(v, "victim", sid)
        self.quiet(v, 52, 52)
        mask = (p.c_act < 0.35) & (p.c_signup < -365 * DAY) & (p.c_kyc == 2)
        r = (p.pick_customers(1, t0, mask=mask) or p.pick_customers(1, t0, mask=(p.c_kyc == 2)))[0]
        p.reserve(r)
        sim.suppress_from[r] = at(51, 0)
        w.c_device[w.cust_of(r)] = ring.devices[-1]
        p.tag(r, "scam_recipient", sid, ring); p.roles[r].add("aged")
        ha = w.c_home_agents[ci][0]
        sim.push(Ev(t0, T["CASH_IN"], ha, v, amount=20000.0))
        sim.push(Ev(at(52, 14, 20), T["SEND_MONEY"], v, r, amount=20000.0, label=("S7", sid, "coerced_send"),
                    cb=self.key_cb(sid)))
        sim.push(Ev(at(52, 14, 31), T["CASH_OUT"], r, self.agent_in_area(w.acct_area[r]), amount=19500.0,
                    channel=CH["APP"], label=("S7", sid, "recipient_cashout")))
        self.wallet(sid, "victim", v)
        self.wallet(sid, "recipient", r)

    def sc07(self, ring):
        sid, sim, p, w = "SC-07", self.sim, self.p, self.w
        t0 = at(56, 3, 10)
        self.case(sid, "S8", ring, t0)
        wal = p.new_wallet(at(52, 13), ring.area, ring.devices[0], "card_fraud_wallet", ring, sid, kyc=2,
                           msisdn_special=self.special_msisdn())
        m = self.new_mule(sid, ring, at(49, 16))
        for k, mm in enumerate((10, 14, 18)):
            sim.push(Ev(at(56, 3, mm), T["ADD_MONEY"], w.ext["X_CARD"], wal, amount=25000.0, channel=CH["APP"],
                        area=ring.area, label=("S8", sid, "card_add_money")))
        sim.push(Ev(at(56, 3, 40), T["CASH_OUT"], wal, ring.rogue, amount=29500.0, channel=CH["APP"],
                    label=("S8", sid, "cashout"), cb=self.key_cb(sid)))
        sim.push(Ev(at(56, 3, 52), T["SEND_MONEY"], wal, m, amount=19500.0, channel=CH["APP"], area=ring.area,
                    label=("S8", sid, "mule_hop")))
        sim.push(Ev(at(56, 4, 20), T["CASH_OUT"], m, ring.rogue, amount=19000.0, channel=CH["APP"],
                    label=("S8", sid, "mule_cashout")))
        self.wallet(sid, "wallet", wal)
        self.wallet(sid, "mule", m)
        self.records[sid]["agent"] = w.ids[ring.rogue]

    def sc08(self):
        sid, sim, p, w, rng = "SC-08", self.sim, self.p, self.w, self.rng
        self.case(sid, "S5", None, at(52, 11))
        p.cases[sid]["variant"] = "phone"
        mask = (p.c_act < 0.35) & (p.c_signup < -200 * DAY) & (p.c_chan == CH["APP"])
        seller = (p.pick_customers(1, at(52, 0), mask=mask) or p.pick_customers(1, at(52, 0), mask=(p.c_signup < -200 * DAY)))[0]
        p.reserve(seller)
        sim.suppress_from[seller] = at(51, 0)
        p.tag(seller, "fake_seller", sid); p.roles[seller].add("aged")
        buyers = p.pick_customers(9, at(52, 0), min_age_days=30)
        amts = [1500, 2200, 3500, 1800, 4500, 2500, 6000, 3000, 2000]
        times = [at(52, 11, 5), at(52, 15, 40), at(52, 21, 10), at(53, 10, 30), at(53, 19, 45),
                 at(54, 12, 15), at(54, 20, 30), at(55, 9, 50), at(55, 16, 20)]
        for i, (b, a, t) in enumerate(zip(buyers, amts, times)):
            p.reserve(b)
            p.cases[sid]["victims"].append(b); p.tag(b, "victim", sid)
            self.quiet(b, t // DAY + 1, t // DAY + 1)
            ha = w.c_home_agents[w.cust_of(b)][0]
            sim.push(Ev(t - 2 * H, T["CASH_IN"], ha, b, amount=float(a + 1000)))
            cb = self.key_cb(sid) if i == 6 else (self.capture("SC-08-buyer1") if i == 0 else None)
            sim.push(Ev(t, T["SEND_MONEY"], b, seller, amount=float(a), label=("S5", sid, "buyer_payment"), cb=cb))
        self.complaints.append((at(53, 18, 0), buyers[0], seller, "SC-08-buyer1"))   # parcel never came
        ag = self.agent_in_area(w.acct_area[seller])
        for d in (52, 53, 54, 55):
            sim.push(Ev(at(d, 21, 30), T["CASH_OUT"], seller, ag, amount_fn=all_cashable, channel=CH["APP"],
                        label=("S5", sid, "seller_cashout"), fit=True, min_amt=300))
        self.wallet(sid, "seller", seller)
        self.wallet(sid, "buyer7", buyers[6])

    # ------------------------------------------------------------------ SB (benign, label = none)
    def sb01(self):
        sid, sim, p, w, rng = "SB-01", self.sim, self.p, self.w, self.rng
        segs = np.array(w.c_seg[:w.n_normal_customers])
        areas = np.array(w.c_area[:w.n_normal_customers])
        signup = np.array(w.c_signup_ts[:w.n_normal_customers])
        best = None
        for a in np.argsort(-np.bincount(areas, minlength=w.n_areas)):
            idx = np.flatnonzero((segs == "small_business") & (areas == a))
            if len(idx) and signup[idx[0]] < -3 * 365 * DAY and not p.blocked[idx[0]]:
                best = idx[0]
                break
        if best is None:
            best = int(np.flatnonzero(segs == "small_business")[0])
        shop = w.acct_of(int(best))
        p.reserve(shop)
        payers = p.pick_customers(12, at(55, 0), mask=(areas == areas[best]), min_age_days=30)
        times = np.sort(rng.uniform(9, 21, len(payers)))
        for i, (b, h) in enumerate(zip(payers, times)):
            p.reserve(b)
            t = at(55, 0) + int(h * H) if i != 9 else at(55, 18, 30)
            sim.push(Ev(t, T["SEND_MONEY"], b, shop, amount=float(rng.integers(20, 150) * 10), topup=True,
                        cb=self.key_cb(sid) if i == 9 else None))
        self.wallet(sid, "shop", shop)
        self.wallet(sid, "payer10", payers[9])

    def sb02(self):
        sid, sim, p, w = "SB-02", self.sim, self.p, self.w
        ncontacts = np.array([len(c) for c in w.c_contacts[:w.n_normal_customers]])
        v = self.pick((p.c_seg == "salaried") & (p.c_kyc == 2) & (p.c_chan == CH["APP"]) & (ncontacts >= 3))
        ci = w.cust_of(v)
        self.quiet(v, 52, 53)
        mother = w.c_contacts[ci][0]
        ha = w.c_home_agents[ci][0]
        sim.push(Ev(at(52, 12), T["CASH_IN"], ha, v, amount=5000.0))
        dev = w.new_device()
        sim.push(Ev(at(53, 19, 30), A["DEVICE_CHANGE"], v, v, device=dev, channel=CH["APP"], meta="set_device"))
        sim.push(Ev(at(53, 19, 45), T["BILL_PAY"], v, w.billers[0], amount=1450.0))
        sim.push(Ev(at(53, 19, 50), T["SEND_MONEY"], v, mother, amount=2000.0, cb=self.key_cb(sid)))
        self.wallet(sid, "customer", v)
        self.wallet(sid, "mother", mother)

    def sb03(self):
        sid, sim, p, w = "SB-03", self.sim, self.p, self.w
        v = self.pick((p.c_seg == "salaried") & (p.c_kyc == 2) & (p.c_chan == CH["APP"]) & (p.c_income > 40000))
        ci = w.cust_of(v)
        contacts = set(w.c_contacts[ci])
        mask = (p.c_area == w.c_area[ci]) & (p.c_signup < -5 * 365 * DAY)
        mask &= ~np.isin(w.C0 + np.arange(len(mask)), list(contacts))
        landlord = self.pick(mask)
        self.quiet(v, 51, 52)
        sim.push(Ev(at(51, 18), T["CASH_IN"], w.c_home_agents[ci][0], v, amount=15000.0))
        sim.push(Ev(at(51, 20), T["ADD_MONEY"], w.ext["X_BANK"], v, amount=25000.0))
        sim.push(Ev(at(52, 11, 0), T["SEND_MONEY"], v, landlord, amount=35000.0, cb=self.key_cb(sid)))
        self.wallet(sid, "tenant", v)
        self.wallet(sid, "landlord", landlord)

    def sb04(self):
        sid, sim, p, w = "SB-04", self.sim, self.p, self.w
        n = w.n_normal_customers
        stud = None
        for i in np.flatnonzero((p.c_seg == "student") & ~p.blocked):
            for par in w.c_contacts[i]:
                pc = w.cust_of(par)
                if pc < n and w.c_seg[pc] in ("salaried", "small_business", "remittance_family") \
                        and w.acct_of(i) in w.c_contacts[pc] and not p.blocked[pc]:
                    stud, parent = w.acct_of(int(i)), par
                    break
            if stud is not None:
                break
        if stud is None:                                      # tiny worlds: fall back to any student + contact
            i = int(np.flatnonzero((p.c_seg == "student") & ~p.blocked)[0])
            stud, parent = w.acct_of(i), w.c_contacts[i][0]
        p.reserve(stud); p.reserve(parent)
        self.quiet(stud, 54, 54); self.quiet(parent, 53, 54)
        for d in (20, 40):                                    # a visible history between them
            sim.push(Ev(at(d, 10), T["SEND_MONEY"], parent, stud, amount=3000.0, topup=True))
        sim.push(Ev(at(53, 18), T["CASH_IN"], w.c_home_agents[w.cust_of(parent)][0], parent, amount=6000.0))
        sim.push(Ev(at(54, 10, 0), T["SEND_MONEY"], parent, stud, amount=5000.0))
        sim.push(Ev(at(54, 10, 12), T["CASH_OUT"], stud, w.c_home_agents[w.cust_of(stud)][0], amount=4900.0,
                    cb=self.key_cb(sid)))
        self.wallet(sid, "student", stud)
        self.wallet(sid, "parent", parent)

    def sb05(self):
        sid, sim, p, w = "SB-05", self.sim, self.p, self.w
        v = self.pick((p.c_seg == "remittance_family") & (p.c_kyc == 2))
        self.quiet(v, 56, 56)
        sim.push(Ev(at(56, 16, 0), T["REMITTANCE_IN"], w.ext["X_REMIT"], v, amount=48250.0))
        sim.push(Ev(at(56, 16, 20), T["CASH_OUT"], v, w.c_home_agents[w.cust_of(v)][0], amount=29500.0,
                    cb=self.key_cb(sid)))
        self.wallet(sid, "customer", v)

    def table(self, txn_ids):
        out = []
        for k, r in self.records.items():
            r = {kk: vv for kk, vv in r.items()}
            row = r.pop("key_row")
            r["key_txn_id"] = txn_ids[row] if row is not None and row >= 0 else None
            out.append(r)
        return out
