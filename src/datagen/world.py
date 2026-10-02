"""Entities of the synthetic MFS world: areas, agents, merchants, billers, customers.

Accounts share one integer index space:
    [externals][billers][agents][merchants][customers ... (grows as fraud wallets are created)]
"""
from __future__ import annotations

import numpy as np

from src.common.config import DAY

TXN_TYPES = ["SEND_MONEY", "CASH_OUT", "CASH_IN", "PAYMENT", "BILL_PAY", "MOBILE_RECHARGE",
             "ADD_MONEY", "SALARY", "REMITTANCE_IN", "FLOAT_TOPUP"]
T = {n: i for i, n in enumerate(TXN_TYPES)}
ACCT_EVENTS = ["SIGNUP", "DEVICE_CHANGE", "SIM_SWAP", "PIN_RESET"]
A = {n: 100 + i for i, n in enumerate(ACCT_EVENTS)}
CHANNELS = ["APP", "USSD", "AGENT", "SYSTEM"]
CH = {n: i for i, n in enumerate(CHANNELS)}
AGE_BANDS = ["18-24", "25-34", "35-44", "45-59", "60+"]
EXTERNALS = ["X_EMPLOYER", "X_REMIT", "X_BANK", "X_CARD"]
DIV_CODES = {"Dhaka": "DHK", "Chattogram": "CTG", "Rajshahi": "RAJ", "Khulna": "KHU",
             "Sylhet": "SYL", "Barishal": "BAR", "Rangpur": "RNG", "Mymensingh": "MYM"}
# category -> (median price Tk, lognormal sigma, share of merchants)
MERCHANT_CATS = {"grocery": (450, 0.7, 0.34), "pharmacy": (300, 0.7, 0.16), "restaurant": (600, 0.6, 0.14),
                 "fashion": (1500, 0.7, 0.12), "electronics": (4000, 0.8, 0.06), "fuel": (800, 0.5, 0.08),
                 "ecommerce": (1200, 0.8, 0.10)}
BILLERS = [("B001", "ELEC_URBAN", "bill"), ("B002", "ELEC_RURAL", "bill"), ("B003", "GAS", "bill"),
           ("B004", "WATER", "bill"), ("B005", "INTERNET", "bill"), ("B006", "EDU_FEE", "bill"),
           ("B007", "INSURANCE", "bill"), ("B008", "TV", "bill"), ("B009", "RECH_GP", "recharge"),
           ("B010", "RECH_ROBI", "recharge"), ("B011", "RECH_BL", "recharge"), ("B012", "RECH_TT", "recharge")]

# segment -> (hour mean, hour sd)
SEG_HOURS = {"salaried": (20.0, 2.2), "garment_worker": (21.0, 1.8), "small_business": (14.5, 3.5),
             "student": (21.5, 2.5), "remittance_family": (15.0, 3.0), "homemaker": (13.5, 2.8),
             "farmer_rural": (11.5, 3.0), "gig_rider": (16.0, 4.0)}
# segment -> gender share female, age-band weights
SEG_DEMO = {"salaried": (0.32, [0.10, 0.42, 0.30, 0.16, 0.02]),
            "garment_worker": (0.58, [0.30, 0.45, 0.20, 0.05, 0.00]),
            "small_business": (0.18, [0.04, 0.28, 0.34, 0.28, 0.06]),
            "student": (0.45, [0.85, 0.15, 0.00, 0.00, 0.00]),
            "remittance_family": (0.62, [0.08, 0.25, 0.27, 0.27, 0.13]),
            "homemaker": (0.97, [0.08, 0.30, 0.30, 0.22, 0.10]),
            "farmer_rural": (0.12, [0.05, 0.18, 0.27, 0.32, 0.18]),
            "gig_rider": (0.04, [0.38, 0.46, 0.13, 0.03, 0.00])}


class World:
    def __init__(self, cfg: dict, rng: np.random.Generator):
        self.cfg, self.rng = cfg, rng
        wc, pop = cfg["world"], cfg["population"]
        self.n_days = wc["n_days"]
        self.start = np.datetime64(wc["start_date"], "s")
        self.segments = list(pop["segments"])
        self._areas(pop)

        self.ids: list[str] = []
        self.kind: list[str] = []
        self.acct_area: list[int] = []
        self.ext = {x: self._acct(x, "X", -1) for x in EXTERNALS}
        self.billers = [self._acct(b, "B", -1) for b, _, _ in BILLERS]
        self.biller_name = {self.billers[i]: BILLERS[i][1] for i in range(len(BILLERS))}
        self._agents(wc["n_agents"])
        self._merchants(wc["n_merchants"])
        self.C0 = len(self.ids)
        self._init_customer_store()
        self._used_msisdn: set[int] = set()
        self.n_devices = len(self.agents)                  # agent terminals take device ints [0, n_agents)
        self._base_customers(wc["n_customers"], pop)
        self.n_base = self.n_cust
        self._new_legit_wallets(pop)
        self._contacts()
        self._households(pop)
        self.n_normal_customers = self.n_cust               # fraud wallets get appended later

    # ------------------------------------------------------------------ helpers
    def _acct(self, ident: str, kind: str, area: int) -> int:
        self.ids.append(ident)
        self.kind.append(kind)
        self.acct_area.append(area)
        return len(self.ids) - 1

    def new_device(self) -> int:
        d = self.n_devices
        self.n_devices += 1
        return d

    def device_name(self, d: int) -> str:
        if d < 0:
            return ""
        return f"AT{d:05d}" if d < len(self.agents) else f"DV{d:07d}"

    def _msisdn(self, special: int | None = None) -> str:
        if special is not None:
            return f"010{special:08d}"
        while True:
            n = int(self.rng.integers(1_000, 100_000_000))
            if n not in self._used_msisdn:
                self._used_msisdn.add(n)
                return f"010{n:08d}"

    # ------------------------------------------------------------------ geography
    def _areas(self, pop):
        divs = list(pop["divisions"])
        share = np.array([pop["divisions"][d] for d in divs], float)
        share /= share.sum()
        apd = pop["areas_per_division"]
        self.divisions = divs
        self.area_div = np.repeat(np.arange(len(divs)), apd)
        self.area_name = [f"{DIV_CODES[d]}-{k + 1:02d}" for d in divs for k in range(apd)]
        n = len(self.area_name)
        urban = np.zeros(n, bool)
        for di, d in enumerate(divs):
            n_urban = max(1, int(round(apd * (0.67 if d == "Dhaka" else 0.4))))
            urban[di * apd: di * apd + n_urban] = True
        self.area_urban = urban
        w = np.repeat(share / apd, apd) * np.where(urban, 1.5, 1.0)
        self.area_w = w / w.sum()
        self.n_areas = n

    # ------------------------------------------------------------------ agents / merchants
    def _agents(self, n):
        rng = self.rng
        base = max(1, n // self.n_areas)
        counts = np.full(self.n_areas, base)
        extra = n - counts.sum()
        if extra > 0:
            counts += rng.multinomial(extra, self.area_w)
        self.agents, self.agent_area = [], []
        k = 0
        for a, c in enumerate(counts):
            for _ in range(int(c)):
                k += 1
                self.agents.append(self._acct(f"A{k:05d}", "A", a))
                self.agent_area.append(a)
        self.agent_area = np.array(self.agent_area)
        self.agent_local = {acct: i for i, acct in enumerate(self.agents)}
        na = len(self.agents)
        self.agent_onboard_ts = -rng.integers(60, 6 * 365, na) * DAY
        self.agent_float = rng.uniform(150_000, 800_000, na).round(-3)
        self.agents_in_area = {a: [self.agents[i] for i in np.flatnonzero(self.agent_area == a)]
                               for a in range(self.n_areas)}

    def _merchants(self, n):
        rng = self.rng
        cats = list(MERCHANT_CATS)
        p = np.array([MERCHANT_CATS[c][2] for c in cats])
        p /= p.sum()
        area = rng.choice(self.n_areas, n, p=self.area_w)
        cat = rng.choice(len(cats), n, p=p)
        self.merchants = [self._acct(f"M{i + 1:05d}", "M", int(area[i])) for i in range(n)]
        self.merchant_area = area
        self.merchant_cat = np.array([cats[c] for c in cat])
        self.merchant_onboard_ts = -rng.integers(30, 5 * 365, n) * DAY
        self.merchants_in_area = {a: [self.merchants[i] for i in np.flatnonzero(area == a)] for a in range(self.n_areas)}

    # ------------------------------------------------------------------ customers
    _CUST_FIELDS = ("seg", "income", "kyc", "chan", "gender", "ageb", "area", "signup_ts", "hmu", "hsig",
                    "act", "salary_day", "home_agents", "merch", "contacts", "cweights", "device",
                    "operator", "msisdn", "init_bal")

    def _init_customer_store(self):
        for f in self._CUST_FIELDS:
            setattr(self, "c_" + f, [])
        self.n_cust = 0

    def acct_of(self, ci: int) -> int:
        return self.C0 + ci

    def cust_of(self, acct: int) -> int:
        return acct - self.C0

    def is_customer(self, acct: int) -> bool:
        return acct >= self.C0

    def add_customer(self, *, seg, income, kyc, chan, gender, ageb, area, signup_ts, hmu, hsig, act,
                     salary_day=-1, home_agents=None, merch=None, contacts=None, cweights=None,
                     device=None, operator=0, init_bal=0.0, msisdn_special=None) -> int:
        ci = self.n_cust
        acct = self._acct(f"W{ci + 1:07d}", "C", int(area))
        if home_agents is None:
            pool = self.agents_in_area.get(int(area)) or self.agents
            k = min(len(pool), int(self.rng.integers(1, 4)))
            home_agents = list(self.rng.choice(pool, k, replace=False))
        if merch is None:
            pool = self.merchants_in_area.get(int(area)) or self.merchants
            k = min(len(pool), int(self.rng.integers(2, 7)))
            merch = list(self.rng.choice(pool, k, replace=False))
        vals = dict(seg=seg, income=float(income), kyc=int(kyc), chan=int(chan), gender=gender, ageb=int(ageb),
                    area=int(area), signup_ts=int(signup_ts), hmu=float(hmu), hsig=float(hsig), act=float(act),
                    salary_day=int(salary_day), home_agents=[int(a) for a in home_agents],
                    merch=[int(m) for m in merch], contacts=list(contacts or []), cweights=list(cweights or []),
                    device=self.new_device() if device is None else int(device), operator=int(operator),
                    msisdn=self._msisdn(msisdn_special), init_bal=float(init_bal))
        for f in self._CUST_FIELDS:
            getattr(self, "c_" + f).append(vals[f])
        self.n_cust += 1
        assert acct == self.acct_of(ci)
        return acct

    def _draw_profile(self, seg: str, pop: dict, n: int):
        rng = self.rng
        lo, hi = pop["segments"][seg]["income"]
        income = np.exp(rng.uniform(np.log(lo), np.log(hi), n)).round(-2)
        mu, sd = SEG_HOURS[seg]
        hmu = mu + rng.normal(0, 1.5, n)
        night = rng.random(n) < (0.07 if seg in ("student", "gig_rider") else 0.02)
        hmu[night] = rng.uniform(23.0, 26.5, night.sum())   # night owls (hard negatives for 'odd hour')
        hsig = rng.uniform(1.3, 3.0, n)
        if sd > 3:
            hsig += 0.8
        fem, ages = SEG_DEMO[seg]
        gender = np.where(rng.random(n) < fem, "F", "M")
        ageb = rng.choice(5, n, p=np.array(ages) / sum(ages))
        return income, np.mod(hmu, 24), hsig, gender, ageb

    def _base_customers(self, n, pop):
        rng = self.rng
        segs = self.segments
        p = np.array([pop["segments"][s]["share"] for s in segs], float)
        p /= p.sum()
        seg_idx = rng.choice(len(segs), n, p=p)
        area = rng.choice(self.n_areas, n, p=self.area_w)
        # rural-heavy segments live in rural areas more often
        for i in np.flatnonzero(np.isin(seg_idx, [segs.index("farmer_rural")])):
            if self.area_urban[area[i]] and rng.random() < 0.85:
                d = self.area_div[area[i]]
                rural = np.flatnonzero((self.area_div == d) & ~self.area_urban)
                if len(rural):
                    area[i] = rng.choice(rural)
        act = rng.lognormal(0, 0.55, n)
        act /= act.mean()
        low = rng.random(n) < 0.10
        act[low] *= 0.2                                      # low-activity pool (aged-mule candidates)
        signup_days = np.exp(rng.uniform(np.log(30), np.log(8 * 365), n)).astype(int)
        kyc = np.where(rng.random(n) < pop["kyc2_share"], 2, 1)
        ussd_p = np.where(np.isin(seg_idx, [segs.index(s) for s in ("farmer_rural", "homemaker")]), 0.5, 0.12)
        chan = np.where(rng.random(n) < ussd_p, CH["USSD"], CH["APP"])
        operator = rng.choice(4, n, p=[0.45, 0.30, 0.15, 0.10])
        for si, seg in enumerate(segs):
            idx = np.flatnonzero(seg_idx == si)
            if not len(idx):
                continue
            income, hmu, hsig, gender, ageb = self._draw_profile(seg, pop, len(idx))
            sd_rng = pop["segments"][seg]["salary_days"]
            for j, i in enumerate(idx):
                sal = int(rng.integers(sd_rng[0], sd_rng[1] + 1)) if sd_rng else -1
                k = int(kyc[i])
                if seg in ("small_business", "remittance_family", "salaried") and rng.random() < 0.6:
                    k = 2
                self.add_customer(seg=seg, income=income[j], kyc=k, chan=chan[i], gender=gender[j],
                                  ageb=ageb[j], area=area[i], signup_ts=-int(signup_days[i]) * DAY,
                                  hmu=hmu[j], hsig=hsig[j], act=act[i], salary_day=sal,
                                  operator=operator[i],
                                  init_bal=float(np.round(income[j] * rng.uniform(0.05, 0.6), -1)))

    def _new_legit_wallets(self, pop):
        """Legit signups during the window, so 'new wallet' alone is not a fraud shortcut."""
        rng = self.rng
        n = rng.poisson(pop["new_wallets_per_day"], self.n_days)
        segs = self.segments
        p = np.array([pop["segments"][s]["share"] for s in segs], float)
        p /= p.sum()
        for d, k in enumerate(n):
            for _ in range(int(k)):
                seg = segs[rng.choice(len(segs), p=p)] if rng.random() > 0.12 else "small_business"
                income, hmu, hsig, gender, ageb = self._draw_profile(seg, pop, 1)
                area = rng.choice(self.n_areas, p=self.area_w)
                ts = d * DAY + int(rng.uniform(9, 21) * 3600)
                sd_rng = pop["segments"][seg]["salary_days"]
                self.add_customer(seg=seg, income=income[0], kyc=2 if rng.random() < 0.55 else 1,
                                  chan=CH["APP"] if rng.random() < 0.85 else CH["USSD"], gender=gender[0],
                                  ageb=ageb[0], area=area, signup_ts=ts, hmu=hmu[0], hsig=hsig[0],
                                  act=float(rng.lognormal(0, 0.5)) * 0.8,
                                  salary_day=int(rng.integers(sd_rng[0], sd_rng[1] + 1)) if sd_rng else -1,
                                  operator=int(rng.choice(4, p=[0.45, 0.30, 0.15, 0.10])), init_bal=0.0)

    def _contacts(self):
        """Social graph with area homophily; garment workers keep family in rural areas elsewhere."""
        rng = self.rng
        n = self.n_cust
        area = np.array(self.c_area)
        div = self.area_div[area]
        by_area = {a: np.flatnonzero(area == a) for a in range(self.n_areas)}
        by_div = {d: np.flatnonzero(div == d) for d in range(len(self.divisions))}
        rural_other = np.flatnonzero(~self.area_urban[area])
        contacts = [set() for _ in range(n)]
        for i in range(n):
            k = int(rng.integers(3, 12))
            seg = self.c_seg[i]
            for _ in range(k):
                r = rng.random()
                if seg == "garment_worker" and len(contacts[i]) < 2:
                    pool = rural_other
                elif r < 0.68:
                    pool = by_area[area[i]]
                elif r < 0.88:
                    pool = by_div[div[i]]
                else:
                    pool = None
                j = int(rng.choice(pool)) if pool is not None and len(pool) else int(rng.integers(0, n))
                if j != i:
                    contacts[i].add(j)
        for i in range(n):                                   # reciprocity
            for j in list(contacts[i]):
                if i not in contacts[j] and len(contacts[j]) < 16 and rng.random() < 0.55:
                    contacts[j].add(i)
        for i in range(n):
            c = list(contacts[i])
            rng.shuffle(c)
            w = 1.0 / np.arange(1, len(c) + 1) ** 1.1
            self.c_contacts[i] = [self.acct_of(j) for j in c]
            self.c_cweights[i] = list(w / w.sum())

    def _households(self, pop):
        """Households and shops share phones: legit device sharing (up to 4 wallets per phone)."""
        rng = self.rng
        for i in range(self.n_cust):
            if rng.random() < pop["shared_device_family_share"] / 2 and self.c_contacts[i]:
                for j in [self.cust_of(c) for c in self.c_contacts[i][:int(rng.integers(1, 4))]]:
                    if self.c_area[j] == self.c_area[i] and self.c_chan[j] == CH["APP"]:
                        self.c_device[j] = self.c_device[i]
                        self.c_chan[i] = CH["APP"]
        self.c_hub = list(rng.random(self.n_cust) < pop.get("hub_share", 0.0))
