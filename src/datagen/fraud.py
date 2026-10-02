"""Fraud injection: rings, mules and scenario scripts S1-S8.

S1 OTP/PIN takeover (incl. agent-register harvesting variant)   S5 fake online seller
S2 collector wallet (many first-time senders, then cash-out)      S6 SIM-swap takeover (high balances)
S3 mule chain / layering (hops attached to S1/S2/S6/S8 cases)     S7 guided victim / pressure scam (own device)
S4 rogue agent collusion (episodes; agent-level label)            S8 card-to-wallet ADD_MONEY burst

Each script pushes `Ev`s whose callbacks decide the next step from the live ledger state,
so amounts always respect balances and limits (fraudsters 'structure' around caps).
"""
from __future__ import annotations

import math
from collections import defaultdict

import numpy as np

from src.common.config import DAY, split_of_day
from .engine import CTRL, Ev, Sim
from .world import A, CH, T

H = 3600
MIN = 60


class Ring:
    def __init__(self, rid, area, devices, rogue=None, weight=1.0):
        self.rid, self.area, self.devices, self.rogue, self.weight = rid, area, devices, rogue, weight
        self.mules: list[tuple[int, int]] = []          # (acct, usable_from_ts) already used in a case
        self.pool: list[tuple[int, int]] = []           # recruited + warmed-up, not yet used
        self.recips: list[list] = []                    # S7 receiving wallets: [acct, uses_left, active_until]
        self.episodes: list[tuple[int, int]] = []


def frac_of_balance(frac, round_to=100):
    def fn(sim: Sim, ev: Ev):
        b = sim.bal[ev.src]
        if b <= 0:
            return 0.0
        amt = b * frac
        if ev.typ == T["CASH_OUT"]:
            amt = min(amt, (b - 5) / (1 + sim.fee_rate))
        else:
            amt = min(amt, b - (6 if amt > 25000 else 1))
        return float(math.floor(amt / round_to) * round_to)
    return fn


def all_cashable(sim: Sim, ev: Ev):
    b = sim.bal[ev.src]
    return float(math.floor(((b - 5) / (1 + sim.fee_rate)) / 100) * 100)


class FraudPlanner:
    def __init__(self, sim: Sim, cfg: dict, rng: np.random.Generator):
        self.sim, self.w, self.cfg, self.rng = sim, sim.w, cfg, rng
        self.fc = cfg["fraud"]
        self.cases: dict[str, dict] = {}
        self.roles: dict[int, set] = defaultdict(set)
        self.wallet_ring: dict[int, int] = {}
        self.wallet_cases: dict[int, set] = defaultdict(set)
        self.reserved: set[int] = set()                 # planted-scenario wallets
        sim.protected = self.reserved
        self.used: set[int] = set()                     # victims / converted wallets
        self.counters = defaultdict(int)
        self.agent_truth: dict[int, dict] = {}
        self.n_days = cfg["world"]["n_days"]
        w = self.w
        n = w.n_normal_customers
        self.c_seg = np.array(w.c_seg[:n])
        self.c_kyc = np.array(w.c_kyc[:n])
        self.c_chan = np.array(w.c_chan[:n])
        self.c_income = np.array(w.c_income[:n])
        self.c_ageb = np.array(w.c_ageb[:n])
        self.c_act = np.array(w.c_act[:n])
        self.c_signup = np.array(w.c_signup_ts[:n])
        self.c_area = np.array(w.c_area[:n])
        self.blocked = np.zeros(n, bool)                 # victims, converted wallets, planted wallets
        self.split_days = {k: (cfg["splits"][f"{k}_days"][0] - 1, cfg["splits"][f"{k}_days"][1] - 1)
                           for k in ("train", "val", "test")}

    # ================================================================== infrastructure
    def setup_rings(self):
        rng, w = self.rng, self.w
        n_rogue = self.fc["S4_rogue_agent"]["agents"]
        n_total_cases = sum(v.get("cases", 0) for v in self.fc.values() if isinstance(v, dict))
        n_rings = n_rogue + max(3, int(round(n_total_cases / 40)))
        area_counts = np.bincount(w.agent_area, minlength=w.n_areas)
        eligible = [a for a in w.agents if area_counts[w.acct_area[a]] >= 3]
        rogues = list(rng.choice(eligible, n_rogue, replace=False))
        self.rings = []
        for r in range(n_rings):
            rogue = int(rogues[r]) if r < n_rogue else None
            area = w.acct_area[rogue] if rogue is not None else int(rng.choice(w.n_areas, p=w.area_w))
            devices = [w.new_device() for _ in range(int(rng.integers(6, 16)))]     # burner phones
            ring = Ring(r, area, devices, rogue, 4.5 if rogue is not None else 1.0)
            if rogue is not None:
                ring.episodes = self._episodes()
                self.agent_truth[rogue] = dict(ring=r, rogue=True, harvested=False,
                                               episodes=[(s // DAY + 1, e // DAY) for s, e in ring.episodes])
            self.rings.append(ring)
        others = [a for a in w.agents if a not in set(rogues)]
        self.harvest_agents = [int(a) for a in rng.choice(others, self.fc["S1_otp_takeover"]["harvest_agents"], replace=False)]
        for a in self.harvest_agents:
            self.agent_truth[a] = dict(ring=None, rogue=False, harvested=True, episodes=[])
        self.ring_p = np.array([r.weight for r in self.rings])
        self.ring_p /= self.ring_p.sum()
        end = self.n_days * DAY
        for ring in self.rings:                           # recruit + 'age' wallets ahead of use
            for _ in range(int(6 + 6 * ring.weight)):
                signup = int(rng.uniform(-60 * DAY, end - DAY))
                dev = self.ring_device(ring) if rng.random() < self.fc["ring_device_share"] else w.new_device()
                acct = self.new_wallet(signup, ring.area, dev, "recruited", ring)
                self.warm_up(acct, signup, min(signup + 30 * DAY, end))
                ring.pool.append((acct, signup))

    def _episodes(self):
        """Rogue-agent bursts: 2 in train, 1 in val, 1 in test, 2-3 days each."""
        rng = self.rng
        eps = []
        for split, k in (("train", 2), ("val", 1), ("test", 1)):
            lo, hi = self.split_days[split]
            starts = []
            for _ in range(k):
                for _try in range(50):
                    L = int(rng.integers(2, 4))
                    s = int(rng.integers(lo, hi - L + 2))
                    if all(abs(s - s2) > 4 for s2 in starts):
                        break
                starts.append(s)
                eps.append((s * DAY, min(s + L, hi + 1) * DAY))
        return eps

    def sample_days(self, n: int) -> np.ndarray:
        """Stratified case days: every scenario appears in train, val and test."""
        rng = self.rng
        lens = {k: hi - lo + 1 for k, (lo, hi) in self.split_days.items()}
        tot = sum(lens.values())
        splits = list(lens)
        assign = splits[:min(n, 3)] + list(rng.choice(splits, max(0, n - 3), p=[lens[s] / tot for s in splits]))
        days = [int(rng.integers(self.split_days[s][0], self.split_days[s][1] + 1)) for s in assign]
        rng.shuffle(days)
        return np.array(days)

    def pick_ring(self):
        return self.rings[int(self.rng.choice(len(self.rings), p=self.ring_p))]

    def case_time(self, day, ring, hour_fn):
        """Rogue rings run ~90% of their cases inside the agent's episode in the same split."""
        rng = self.rng
        if ring is not None and ring.rogue is not None and rng.random() < 0.9:
            split = split_of_day(self.cfg, int(day))
            eps = [e for e in ring.episodes if split_of_day(self.cfg, e[0] // DAY) == split]
            if eps:
                s, e = eps[int(rng.integers(len(eps)))]
                day = int(rng.integers(s // DAY, max(s // DAY + 1, e // DAY)))
        return int(day) * DAY + int(hour_fn() * H) + int(rng.integers(0, 60))

    def new_case(self, scen, ring, t0, **extra):
        self.counters[scen] += 1
        cid = f"{scen}-{self.counters[scen]:04d}"
        self.cases[cid] = dict(case_id=cid, scenario=scen, ring=None if ring is None else ring.rid, t0=int(t0),
                               split=split_of_day(self.cfg, int(t0) // DAY), victims=[], wallets=[], parent=None,
                               _ring=ring, **extra)
        return cid

    def block(self, acct):
        ci = acct - self.w.C0
        if 0 <= ci < len(self.blocked):
            self.blocked[ci] = True

    def reserve(self, acct):
        self.reserved.add(acct)
        self.block(acct)

    def tag(self, acct, role, cid=None, ring=None):
        self.roles[acct].add(role)
        self.block(acct)
        if cid:
            self.wallet_cases[acct].add(cid)
            c = self.cases.get(cid)
            if c is not None and acct not in c["wallets"]:
                c["wallets"].append(acct)
        if ring is not None:
            self.wallet_ring[acct] = ring.rid

    # ------------------------------------------------------------------ wallet pools
    def pick_customers(self, k, t0, weights=None, mask=None, min_age_days=5):
        rng = self.rng
        n = len(self.c_seg)
        ok = self.c_signup <= t0 - min_age_days * DAY
        if mask is not None:
            ok &= mask
        ok &= ~self.blocked
        idx = np.flatnonzero(ok)
        if len(idx) == 0:
            return []
        p = None
        if weights is not None:
            p = weights[idx].astype(float)
            p = p / p.sum() if p.sum() > 0 else None
        k = min(k, len(idx))
        pick = rng.choice(idx, k, replace=False, p=p)
        out = [int(self.w.C0 + i) for i in pick]
        self.used.update(out)
        self.blocked[pick] = True
        return out

    def _fake_profile(self, area, kyc=None):
        rng, w = self.rng, self.w
        seg = str(rng.choice(["student", "small_business", "salaried", "gig_rider", "homemaker"]))
        return dict(seg=seg, income=float(rng.uniform(8000, 30000)), kyc=kyc or (2 if rng.random() < 0.7 else 1),
                    chan=CH["APP"], gender="F" if rng.random() < 0.3 else "M", ageb=int(rng.choice(5, p=[.35, .4, .15, .08, .02])),
                    area=area, hmu=float(rng.uniform(10, 22)), hsig=2.0, act=0.0)

    def new_wallet(self, signup_ts, area, device, role, ring=None, cid=None, kyc=None, msisdn_special=None):
        w, sim = self.w, self.sim
        prof = self._fake_profile(area, kyc)
        acct = w.add_customer(signup_ts=int(signup_ts), device=device, msisdn_special=msisdn_special, **prof)
        sim.ensure_account(acct)
        if signup_ts >= 0:
            sim.record_acct_event(signup_ts, acct, A["SIGNUP"], device, area, CH["APP"], None)
        self.tag(acct, role, cid, ring)
        return acct

    def buy_account(self, t_use, ring, role, cid=None, dormant=None, kyc2=False):
        """Aged mule: a real, old, low-activity wallet bought for Tk 3,000-4,000. Its owner's normal
        activity stops; the gang logs in from its own phone."""
        rng, w, sim = self.rng, self.w, self.sim
        mask = (self.c_act < 0.35) & (self.c_signup < -120 * DAY)
        if kyc2:
            mask &= self.c_kyc == 2
        got = self.pick_customers(1, t_use, mask=mask)
        if not got:
            return None
        acct = got[0]
        t_buy = int(t_use - rng.uniform(0.5, 10) * DAY)
        if sim.now > 0:
            t_buy = max(t_buy, sim.now)
        dormant = rng.random() < 0.5 if dormant is None else dormant
        sim.suppress_from[acct] = int(t_buy - rng.uniform(10, 45) * DAY) if (dormant and sim.now == 0) else t_buy
        dev = ring.devices[int(rng.integers(len(ring.devices)))] if ring is not None else w.new_device()
        if t_buy >= 0 and t_buy > sim.now:
            sim.push(Ev(t_buy, A["DEVICE_CHANGE"], acct, acct, device=dev, area=ring.area if ring else None,
                        channel=CH["APP"], meta="set_device"))
        elif t_buy >= 0:                                  # bought right now (mid-run)
            w.c_device[w.cust_of(acct)] = dev
            sim.record_acct_event(t_buy, acct, A["DEVICE_CHANGE"], dev, ring.area if ring else -1, CH["APP"], None)
        else:
            w.c_device[w.cust_of(acct)] = dev
        self.tag(acct, role, cid, ring)
        self.roles[acct].add("aged")
        return acct

    def get_mule(self, ring, t, cid=None, exclude=()):
        rng = self.rng
        avail = [m for m, ts in ring.mules if ts <= t - H and m not in exclude]
        if avail and rng.random() < 0.35:
            m = avail[int(rng.integers(len(avail)))]
            self.tag(m, "mule", cid, ring)
            return m
        if rng.random() < self.fc["aged_mule_share"]:
            m = self.buy_account(t, ring, "mule", cid)
            if m is not None:
                ring.mules.append((m, t - H))
                return m
        ready = [i for i, (a, su) in enumerate(ring.pool) if su <= t - 12 * H and a not in exclude]
        if ready and rng.random() < 0.85:
            a, su = ring.pool.pop(ready[int(rng.integers(len(ready)))])
            self.tag(a, "mule", cid, ring)
            ring.mules.append((a, t - H))
            return a
        signup = int(t - rng.uniform(0.5, 60) * DAY)
        dev = self.ring_device(ring) if rng.random() < self.fc["ring_device_share"] else self.w.new_device()
        m = self.new_wallet(signup, ring.area, dev, "mule", ring, cid)
        self.warm_up(m, signup, t)
        ring.mules.append((m, max(signup, t - H)))
        return m

    def warm_up(self, acct, t_from, t_to):
        """Gangs 'age' a fresh wallet: a cash-in, a few recharges and small transfers (label 0)."""
        rng, sim, w = self.rng, self.sim, self.w
        t_from, t_to = max(int(t_from), sim.now + 60) + H, int(t_to) - 2 * H
        days = (t_to - t_from) / DAY
        if days < 0.5:
            return
        n = min(int(rng.poisson(self.fc["warmup_rate_per_day"] * days)), 15)
        if n == 0:
            return
        area = w.acct_area[acct]
        pool = w.agents_in_area.get(area) or w.agents
        t_ci = int(t_from + rng.uniform(0, min(days, 2)) * DAY)
        t_ci = (t_ci // DAY) * DAY + int(rng.uniform(10, 20) * H)
        if t_ci < t_to:
            sim.push(Ev(t_ci, T["CASH_IN"], pool[int(rng.integers(len(pool)))], acct,
                        amount=float(rng.choice([500, 1000, 1500, 2000, 3000])), fit=True, min_amt=100))
        for _ in range(n):
            lo = max(t_ci, t_from) + H
            if t_to <= lo:
                break
            t = int(rng.uniform(lo, t_to))
            t = (t // DAY) * DAY + int(rng.uniform(9, 22.5) * H)
            if t >= t_to or t <= t_ci:
                continue
            if rng.random() < 0.55:
                sim.push(Ev(t, T["MOBILE_RECHARGE"], acct, w.billers[8 + int(rng.integers(4))],
                            amount=float(rng.choice([20, 50, 100, 149, 200])), fit=True, min_amt=10, channel=CH["APP"]))
            else:
                for _try in range(10):                    # never touch planted / dormant / converted wallets
                    ci = int(rng.integers(0, w.n_normal_customers))
                    to = w.acct_of(ci)
                    if not self.blocked[ci] and to not in sim.suppress_from:
                        break
                else:
                    continue
                sim.push(Ev(t, T["SEND_MONEY"], acct, to, amount=float(rng.choice([100, 200, 300, 500])), fit=True,
                            min_amt=50, channel=CH["APP"], meta="warmup"))

    def ring_device(self, ring):
        return ring.devices[int(self.rng.integers(len(ring.devices)))]

    # ------------------------------------------------------------------ money movement helpers
    def pick_agent(self, ring, wallet, t):
        rng, w = self.rng, self.w
        if ring is not None and ring.rogue is not None:
            in_ep = any(s <= t < e for s, e in ring.episodes)
            if rng.random() < (0.92 if in_ep else 0.15):
                return ring.rogue, t                       # rogue shop opens any hour for the gang
        area = w.acct_area[wallet]
        pool = w.agents_in_area.get(area) or w.agents
        agent = pool[int(rng.integers(len(pool)))]
        h = (t % DAY) / H
        if h < 8.5 or h >= 21.5:
            day = t // DAY + (1 if h >= 21.5 else 0)
            t = day * DAY + int(rng.uniform(8.6, 11) * H)
        return agent, t

    def schedule_cashout(self, wallet, case_id, t, scen, role, tries=0):
        rng, sim = self.rng, self.sim
        case = self.cases[case_id]
        ring = case["_ring"]
        agent, t2 = self.pick_agent(ring, wallet, int(t))

        def after(sim_, ev, ok, row, amount):
            if tries >= 6 or sim_.bal[wallet] < 800:
                return
            if ok and sim_.allowance(wallet, "cash_out", ev.ts) >= 500:
                nxt = ev.ts + int(rng.uniform(3, 40) * MIN)          # next agent: structuring
            else:
                if ring is not None and rng.random() < 0.4:
                    m2 = self.get_mule(ring, ev.ts, case_id, exclude={wallet})
                    sim_.push(Ev(ev.ts + int(rng.uniform(5, 30) * MIN), T["SEND_MONEY"], wallet, m2,
                                 amount_fn=frac_of_balance(0.97, 10), channel=CH["APP"], area=ring.area,
                                 label=(scen, case_id, "mule_hop"), fit=True, min_amt=300,
                                 cb=self.on_funded(m2, case_id, None)))
                    return
                nxt = (ev.ts // DAY + 1) * DAY + int(rng.uniform(9, 12) * H)
            self.schedule_cashout(wallet, case_id, nxt, scen, role, tries + 1)

        sim.push(Ev(t2, T["CASH_OUT"], wallet, agent, amount_fn=all_cashable, channel=CH["APP"],
                    area=self.w.acct_area[agent], label=(scen, case_id, role), cb=after, fit=True, min_amt=300))

    def on_funded(self, mule, case_id, chain, depth=0):
        """After money lands in a mule: forward along the chain, or cash out."""
        def cb(sim_, ev, ok, row, amount):
            if not ok:
                return
            self.mule_next(mule, case_id, chain, depth, ev.ts)
        return cb

    def mule_next(self, mule, case_id, chain, depth, t):
        rng, sim = self.rng, self.sim
        case = self.cases[case_id]
        ring = case["_ring"]
        if chain is not None and chain["hops_left"] > 0 and ring is not None:
            lo, hi = self.fc["S3_mule_chain"]["hop_delay_min"]
            n_next = 2 if rng.random() < 0.3 else 1
            keep = 0.90 if rng.random() < 0.4 else float(rng.uniform(0.9, 0.99))   # gang cut ~Tk1,000 per 10,000
            nxt_chain = dict(chain, hops_left=chain["hops_left"] - 1)
            t1 = t + int(rng.uniform(lo, hi) * MIN)
            sent = 0.0
            for j in range(n_next):
                share = keep / n_next
                f = share / max(1e-9, 1 - sent)
                sent += share
                m2 = self.get_mule(ring, t, chain["cid"], exclude={mule})
                self.tag(m2, "mule", chain["cid"], ring)
                sim.push(Ev(t1 + j * int(rng.uniform(20, 120)), T["SEND_MONEY"], mule, m2,
                            amount_fn=frac_of_balance(min(f, 0.995), int(rng.choice([10, 100]))), channel=CH["APP"],
                            area=ring.area, label=("S3", chain["cid"], "mule_hop"), fit=True, min_amt=300,
                            cb=self.on_funded(m2, case_id, nxt_chain, depth + 1)))
        else:
            if chain is not None:
                scen, cid = "S3", chain["cid"]
            else:
                scen, cid = case["scenario"], case_id
            if cid != case_id:
                self.cases[cid]["_ring"] = ring
            wait = rng.uniform(5, 90) * MIN if rng.random() < 0.6 else rng.uniform(2, 20) * H
            self.schedule_cashout(mule, cid, t + int(wait), scen, "mule_cashout")

    def start_chain(self, src, case_id, t, frac=0.8, label_scen="S3"):
        """First hop out of a fraud wallet into an S3 chain."""
        rng, sim = self.rng, self.sim
        case = self.cases[case_id]
        chain = case.get("chain")
        ring = case["_ring"]
        m = self.get_mule(ring, t, chain["cid"], exclude={src})
        sim.push(Ev(t, T["SEND_MONEY"], src, m, amount_fn=frac_of_balance(frac, 100), channel=CH["APP"],
                    area=ring.area, label=("S3", chain["cid"], "mule_hop"), fit=True, min_amt=300,
                    cb=self.on_funded(m, case_id, dict(chain, hops_left=chain["hops"] - 1), 1)))

    # ================================================================== scenario planning
    def plan_cases(self):
        """Call after setup_rings() (and after planted wallets are reserved)."""
        rng = self.rng
        specs = []
        hour_fns = {
            "S1": lambda: rng.uniform(0, 5.5) if rng.random() < 0.35 else rng.uniform(9, 23.5),
            "S2": lambda: rng.uniform(8, 14),
            "S5": lambda: rng.uniform(10, 20),
            "S6": lambda: rng.uniform(0, 5.5) if rng.random() < 0.55 else rng.uniform(9, 18),
            "S7": lambda: rng.uniform(9, 20),
            "S8": lambda: rng.uniform(0, 5.5) if rng.random() < 0.5 else rng.uniform(8, 23.5),
        }
        keys = {"S1": "S1_otp_takeover", "S2": "S2_collector_wallet", "S5": "S5_fake_seller",
                "S6": "S6_sim_swap", "S7": "S7_guided_victim", "S8": "S8_card_add_money"}
        for scen, key in keys.items():
            n = self.fc[key]["cases"]
            for day in self.sample_days(n):
                ring = None if scen == "S5" else self.pick_ring()
                t0 = self.case_time(day, ring, hour_fns[scen])
                specs.append((scen, ring, t0))
        specs.sort(key=lambda s: s[2])
        cids = [self.new_case(scen, ring, t0) for scen, ring, t0 in specs]
        self._choose_chain_parents(cids)
        launch = {"S1": self.s1_takeover, "S2": self.s2_collector, "S5": self.s5_fake_seller,
                  "S6": self.s6_sim_swap, "S7": self.s7_guided_victim, "S8": self.s8_card_add_money}
        n_harvest = int(round(self.fc["S1_otp_takeover"]["cases"] * self.fc["S1_otp_takeover"]["register_harvest_share"]))
        s1 = [c for c in cids if c.startswith("S1")]
        harvest = set(rng.choice(s1, min(n_harvest, len(s1)), replace=False)) if s1 else set()
        for cid in cids:
            c = self.cases[cid]
            if c["scenario"] == "S1":
                self.s1_takeover(cid, harvest=cid in harvest)
            else:
                launch[c["scenario"]](cid)

    def _choose_chain_parents(self, cids):
        rng = self.rng
        n = self.fc["S3_mule_chain"]["cases"]
        wmap = {"S1": 0.5, "S2": 1.5, "S6": 3.0, "S8": 2.0}
        cand = [c for c in cids if self.cases[c]["scenario"] in wmap]
        chosen = []
        for split in ("train", "val", "test"):               # at least one chain per split
            pool = [c for c in cand if self.cases[c]["split"] == split and c not in chosen]
            if pool:
                chosen.append(pool[int(rng.integers(len(pool)))])
        rest = [c for c in cand if c not in chosen]
        p = np.array([wmap[self.cases[c]["scenario"]] for c in rest])
        k = max(0, min(n - len(chosen), len(rest)))
        if k:
            chosen += list(rng.choice(rest, k, replace=False, p=p / p.sum()))
        lo, hi = self.fc["S3_mule_chain"]["hops"]
        for c in sorted(chosen, key=lambda x: self.cases[x]["t0"]):
            par = self.cases[c]
            ccid = self.new_case("S3", par["_ring"], par["t0"])
            self.cases[ccid]["parent"] = c
            par["chain"] = dict(cid=ccid, hops=int(rng.integers(lo, hi + 1)))

    # ------------------------------------------------------------------ S1
    def s1_takeover(self, cid, harvest=False):
        rng, sim, w = self.rng, self.sim, self.w
        c = self.cases[cid]
        ring, t0 = c["_ring"], c["t0"]
        remote = (not harvest) and rng.random() < self.fc["S1_otp_takeover"].get("remote_access_share", 0.0)
        c["variant"] = "register_harvest" if harvest else ("remote_access_app" if remote else "otp_call")
        weights = np.clip(self.c_income, 5000, None)
        mask = None
        if harvest:
            ha = int(rng.choice(self.harvest_agents))
            c["harvest_agent"] = w.ids[ha]
            home = np.array([ha in hs for hs in w.c_home_agents[:len(self.c_seg)]])
            mask = home | (self.c_area == w.acct_area[ha])
        got = self.pick_customers(1, t0, weights=weights, mask=mask)
        if not got:
            return
        v = got[0]
        c["victims"].append(v)
        self.tag(v, "victim", cid)
        if harvest:                                           # the real agent visit whose register gets photographed
            tv = int((t0 // DAY - rng.integers(1, 6)) * DAY + rng.uniform(10, 20) * H)
            if tv > 0:
                sim.push(Ev(tv, T["CASH_IN"], ha, v, amount=float(rng.choice([1000, 2000, 3000, 5000, 6000])), fit=True,
                            min_amt=100))
        if remote:                    # victim installs a screen-sharing app: the gang drives the victim's own phone
            dev, area, chan = None, None, None
        else:
            dev, area, chan = self.ring_device(ring), ring.area, CH["APP"]
            sim.push(Ev(t0, A["DEVICE_CHANGE"], v, v, device=dev, area=ring.area, channel=CH["APP"],
                        label=("S1", cid, "takeover_login")))
            if rng.random() < 0.5:
                sim.push(Ev(t0 + int(rng.uniform(10, 60)), A["PIN_RESET"], v, v, device=dev, area=ring.area,
                            channel=CH["APP"], label=("S1", cid, "pin_reset")))
        n_send = 4 if harvest else int(rng.choice([1, 2, 3], p=[.55, .3, .15]))
        total = float(rng.uniform(0.85, 0.99)) if rng.random() < 0.6 else float(rng.uniform(0.4, 0.85))
        shares = rng.dirichlet(np.full(n_send, 2.0))
        t = t0 + (int(rng.uniform(15, 40)) if harvest else int(rng.uniform(30, 180)))
        sent = 0.0
        chain = c.get("chain")
        for j in range(n_send):
            f = shares[j] * total / max(1e-9, 1 - sent)
            sent += shares[j] * total
            m = self.get_mule(ring, t0, cid)
            cb = self.on_funded(m, cid, dict(chain, hops_left=chain["hops"] - 1) if (chain and j == 0) else None, 1)
            sim.push(Ev(t, T["SEND_MONEY"], v, m, amount_fn=frac_of_balance(min(f, 0.995), int(rng.choice([10, 100]))),
                        device=dev, channel=chan, area=area, label=("S1", cid, "takeover_drain"),
                        cb=cb, fit=True, min_amt=200))
            t += int(rng.uniform(4, 9)) if harvest else int(rng.uniform(30, 400))

    # ------------------------------------------------------------------ S2
    def s2_collector(self, cid):
        rng, sim, w = self.rng, self.sim, self.w
        c = self.cases[cid]
        ring, t0 = c["_ring"], c["t0"]
        spec = self.fc["S2_collector_wallet"]
        if rng.random() < 0.15:
            col = self.buy_account(t0, ring, "collector", cid)
        else:
            col = None
        if col is None:
            col = self.new_wallet(int(t0 - rng.uniform(1, 3) * DAY), ring.area, self.ring_device(ring), "collector",
                                  ring, cid)
            self.warm_up(col, t0 - 3 * DAY, t0)
        c["collector"] = col
        scam = str(rng.choice(["job_fee", "lottery", "parcel_customs", "loan_fee"]))
        c["variant"] = scam
        lo_hi = {"job_fee": (1000, 3000), "lottery": (2000, 8000), "parcel_customs": (800, 2500), "loan_fee": (500, 2000)}[scam]
        n_v = int(rng.integers(spec["victims"][0], spec["victims"][1] + 1))
        window = float(rng.uniform(*spec["window_hours"])) * H
        segw = np.where(np.isin(self.c_seg, ["student", "homemaker", "garment_worker"]), 3.0, 1.0)
        victims = self.pick_customers(n_v, t0, weights=segw)
        times = np.sort(t0 + rng.uniform(0, window, len(victims))).astype(int)
        for v, tv in zip(victims, times):
            c["victims"].append(v)
            self.tag(v, "victim", cid)
            amt = float(np.round(rng.uniform(*lo_hi) / 100) * 100)
            sim.push(Ev(int(tv), T["SEND_MONEY"], v, col, amount=amt, label=("S2", cid, "victim_payment"),
                        topup=True, fit=False, min_amt=100))
            if rng.random() < 0.15:                           # "one more processing fee"
                sim.push(Ev(int(tv + rng.uniform(20, 90) * MIN), T["SEND_MONEY"], v, col,
                            amount=float(np.round(amt * rng.uniform(0.5, 1.5) / 100) * 100),
                            label=("S2", cid, "victim_payment"), topup=True, min_amt=100))
        t_mid = int(t0 + window * rng.uniform(0.35, 0.6))
        t_end = int(t0 + window + rng.uniform(0.5, 3) * H)
        if c.get("chain"):
            self.start_chain(col, cid, t_mid, frac=0.75)
        else:
            self.schedule_cashout(col, cid, t_mid, "S2", "collector_cashout")
        self.schedule_cashout(col, cid, t_end, "S2", "collector_cashout")

    # ------------------------------------------------------------------ S5
    def s5_fake_seller(self, cid):
        rng, sim, w = self.rng, self.sim, self.w
        c = self.cases[cid]
        t0 = c["t0"]
        spec = self.fc["S5_fake_seller"]
        seller = None
        if rng.random() < 0.4:
            seller = self.buy_account(t0, None, "fake_seller", cid, dormant=False)
        if seller is None:
            area = int(rng.choice(w.n_areas, p=w.area_w))
            signup = int(t0 - rng.uniform(5, 45) * DAY)
            seller = self.new_wallet(signup, area, w.new_device(), "fake_seller", None, cid)
            self.warm_up(seller, signup, t0)
        c["seller"] = seller
        c["variant"] = str(rng.choice(["phone", "dress", "eid_items", "gadget"]))
        dur = float(rng.uniform(*spec["duration_days"])) * DAY
        n_b = int(rng.integers(spec["buyers"][0], spec["buyers"][1] + 1))
        buyers = self.pick_customers(n_b, t0)
        times = []
        for _ in buyers:
            d = rng.uniform(0, dur)
            t = int(t0 + d)
            h = rng.uniform(10, 23.5)
            times.append(int((t // DAY) * DAY + h * H))
        for v, tv in sorted(zip(buyers, times), key=lambda x: x[1]):
            c["victims"].append(v)
            self.tag(v, "victim", cid)
            amt = float(np.round(rng.uniform(800, 6000) / 10) * 10)
            sim.push(Ev(tv, T["SEND_MONEY"], v, seller, amount=amt, label=("S5", cid, "buyer_payment"), topup=True,
                        min_amt=100))
        day0, day_end = t0 // DAY, int((t0 + dur) // DAY) + 1
        for d in range(day0, day_end + 1):
            tco = int(d * DAY + rng.uniform(18, 21) * H)
            self.schedule_cashout(seller, cid, tco, "S5", "seller_cashout", tries=4)

    # ------------------------------------------------------------------ S6
    def s6_sim_swap(self, cid):
        rng, sim, w = self.rng, self.sim, self.w
        c = self.cases[cid]
        ring, t0 = c["_ring"], c["t0"]
        mask = (self.c_kyc == 2) & np.isin(self.c_seg, ["small_business", "salaried"]) & (self.c_income > 25000)
        got = self.pick_customers(1, t0, weights=self.c_income, mask=mask)
        if not got:
            return
        v = got[0]
        c["victims"].append(v)
        self.tag(v, "victim", cid)
        ci = w.cust_of(v)
        ha = w.c_home_agents[ci][0]
        for back in (1, 2):                                   # business owner banks the day's takings
            tb = int((t0 // DAY - back) * DAY + rng.uniform(10, 19) * H)
            if tb > 0:
                sim.push(Ev(tb, T["CASH_IN"], ha, v, amount=float(rng.integers(20, 31) * 1000), fit=True, min_amt=1000))
        dev = self.ring_device(ring)
        sim.push(Ev(t0, A["SIM_SWAP"], v, v, area=ring.area, channel=CH["SYSTEM"], label=("S6", cid, "sim_swap")))
        t1 = t0 + int(rng.uniform(5, 40) * MIN)
        sim.push(Ev(t1, A["DEVICE_CHANGE"], v, v, device=dev, area=ring.area, channel=CH["APP"],
                    label=("S6", cid, "takeover_login")))
        sim.push(Ev(t1 + int(rng.uniform(60, 180)), A["PIN_RESET"], v, v, device=dev, area=ring.area,
                    channel=CH["APP"], label=("S6", cid, "pin_reset")))
        t = t1 + int(rng.uniform(4, 10) * MIN)
        chain = c.get("chain")
        for j, f in enumerate([0.65, 0.92, 0.95][:int(rng.integers(2, 4))]):
            m = self.get_mule(ring, t0, cid)
            cb = self.on_funded(m, cid, dict(chain, hops_left=chain["hops"] - 1) if (chain and j == 0) else None, 1)
            sim.push(Ev(t, T["SEND_MONEY"], v, m, amount_fn=frac_of_balance(f, 100), device=dev, channel=CH["APP"],
                        area=ring.area, label=("S6", cid, "takeover_drain"), cb=cb, fit=True, min_amt=500))
            t += int(rng.uniform(2, 8) * MIN)
        if rng.random() < 0.4:                                # victim hasn't recovered the SIM by morning
            t2 = int((t0 // DAY + 1) * DAY + rng.uniform(7.5, 10) * H)
            m = self.get_mule(ring, t2, cid)
            sim.push(Ev(t2, T["SEND_MONEY"], v, m, amount_fn=frac_of_balance(0.95, 100), device=dev,
                        channel=CH["APP"], area=ring.area, label=("S6", cid, "takeover_drain"),
                        cb=self.on_funded(m, cid, None, 1), fit=True, min_amt=500))

    # ------------------------------------------------------------------ S7
    def get_recipient(self, ring, t, cid):
        rng, w = self.rng, self.w
        live = [r for r in ring.recips if r[1] > 0 and r[2] > t]
        if live:
            r = live[int(rng.integers(len(live)))]
            r[1] -= 1
            self.tag(r[0], "scam_recipient", cid, ring)
            return r[0]
        acct = None
        if rng.random() < 0.4:
            acct = self.buy_account(t, ring, "scam_recipient", cid)
        if acct is None:
            signup = int(t - rng.uniform(3, 90) * DAY)
            dev = self.ring_device(ring) if rng.random() < self.fc["ring_device_share"] else w.new_device()
            acct = self.new_wallet(signup, ring.area, dev, "scam_recipient", ring, cid)
            self.warm_up(acct, signup, t)
        ring.recips.append([acct, int(rng.integers(0, 6)), int(t + rng.uniform(1, 5) * DAY)])
        return acct

    def s7_guided_victim(self, cid):
        rng, sim, w = self.rng, self.sim, self.w
        c = self.cases[cid]
        ring, t0 = c["_ring"], c["t0"]
        c["variant"] = str(rng.choice(["jail_guard", "lawyer", "police", "relative_in_hospital", "fake_upay_officer"]))
        wts = np.where(np.isin(self.c_seg, ["homemaker", "farmer_rural", "remittance_family"]), 2.5, 1.0)
        wts = wts * np.where(self.c_ageb >= 3, 2.0, 1.0) * np.where(self.c_chan == CH["USSD"], 1.5, 1.0)
        got = self.pick_customers(1, t0, weights=wts)
        if not got:
            return
        v = got[0]
        c["victims"].append(v)
        self.tag(v, "victim", cid)
        rec = self.get_recipient(ring, t0, cid)
        c["recipient"] = rec
        target = float(rng.choice([3000, 5000, 8000, 10000, 12000, 15000, 20000, 25000],
                                  p=[.12, .2, .15, .18, .1, .1, .1, .05]))
        ha = w.c_home_agents[w.cust_of(v)][0]

        def recipient_cb(sim_, ev, ok, row, amount):
            if ok:
                self.schedule_cashout(rec, cid, ev.ts + int(rng.uniform(5, 40) * MIN), "S7", "recipient_cashout", tries=3)

        def start(sim_, ev, ok, row, amount):
            need = target + 5 - sim_.bal[v]
            t_send = t0 + int(rng.uniform(1, 5) * MIN)
            if need > 0:                                      # brings cash to the shop first
                amt = math.ceil((need + rng.uniform(0, 500)) / 500) * 500
                sim_.push(Ev(t0, T["CASH_IN"], ha, v, amount=float(amt), fit=True, min_amt=100))
                t_send = t0 + int(rng.uniform(6, 25) * MIN)
            sim_.push(Ev(t_send, T["SEND_MONEY"], v, rec, amount=target, label=("S7", cid, "coerced_send"),
                         cb=recipient_cb, fit=True, min_amt=500))
            if rng.random() < 0.25:                           # "a little more for bail"
                sim_.push(Ev(t_send + int(rng.uniform(15, 60) * MIN), T["SEND_MONEY"], v, rec,
                             amount=float(np.round(target * rng.uniform(0.3, 0.8) / 500) * 500),
                             label=("S7", cid, "coerced_send"), cb=recipient_cb, fit=True, min_amt=500, topup=True))

        sim.push(Ev(t0, CTRL, v, v, cb=start))

    # ------------------------------------------------------------------ S8
    def s8_card_add_money(self, cid):
        rng, sim, w = self.rng, self.sim, self.w
        c = self.cases[cid]
        ring, t0 = c["_ring"], c["t0"]
        wal = None
        if rng.random() < 0.4:
            wal = self.buy_account(t0, ring, "card_fraud_wallet", cid)
        if wal is None:
            signup = int(t0 - rng.uniform(1, 30) * DAY)
            wal = self.new_wallet(signup, ring.area, self.ring_device(ring), "card_fraud_wallet", ring, cid, kyc=2)
            self.warm_up(wal, signup, t0)
        c["wallet"] = wal
        n_chunks = int(rng.integers(self.fc["S8_card_add_money"]["chunks"][0], self.fc["S8_card_add_money"]["chunks"][1] + 1))
        t = t0
        for j in range(n_chunks):
            amt = float(rng.choice([10000, 15000, 20000, 24990, 25000]))
            fit = rng.random() < 0.5                          # half the gangs probe the limit and get rejected
            sim.push(Ev(t, T["ADD_MONEY"], w.ext["X_CARD"], wal, amount=amt, channel=CH["APP"], area=ring.area,
                        label=("S8", cid, "card_add_money"), fit=fit, min_amt=1000))
            t += int(rng.uniform(1, 6) * MIN)
        tco = t + int(rng.uniform(3, 30) * MIN)
        if c.get("chain"):
            self.start_chain(wal, cid, tco, frac=0.6)
            self.schedule_cashout(wal, cid, tco + int(rng.uniform(5, 20) * MIN), "S8", "cashout")
        else:
            self.schedule_cashout(wal, cid, tco, "S8", "cashout")

    # ================================================================== outputs
    def case_table(self, sim):
        rows = []
        for cid, c in self.cases.items():
            rows.append(dict(case_id=cid, scenario=c["scenario"], ring_id=c["ring"], t0=c["t0"], split=c["split"],
                             parent_case=c["parent"], variant=c.get("variant", ""),
                             victims=";".join(self.w.ids[v] for v in c["victims"]),
                             wallets=";".join(self.w.ids[x] for x in c["wallets"]),
                             harvest_agent=c.get("harvest_agent", "")))
        return rows
