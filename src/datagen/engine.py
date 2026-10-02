"""Time-ordered ledger simulation.

Normal events come pre-sorted in numpy arrays; fraud scripts push `Ev` objects onto a heap
(with callbacks that schedule the next step from the *current* balance). Every event is
checked against balance and KYC limits before it is written, so balances chain exactly and
no successful transaction ever breaks a cap (validation T3/T4).
"""
from __future__ import annotations

import heapq
import math

import numpy as np

from src.common.config import DAY
from .world import A, CH, T, World

LIMIT_TYPE = {T["SEND_MONEY"]: ("send_money", 0), T["CASH_OUT"]: ("cash_out", 0), T["PAYMENT"]: ("payment", 0),
              T["BILL_PAY"]: ("payment", 0), T["MOBILE_RECHARGE"]: ("payment", 0),
              T["CASH_IN"]: ("cash_in", 1), T["ADD_MONEY"]: ("add_money", 1)}
CUSTOMER_INITIATED = {T["SEND_MONEY"], T["CASH_OUT"], T["PAYMENT"], T["BILL_PAY"], T["MOBILE_RECHARGE"]}
FAIL_NONE, FAIL_FUNDS, FAIL_LIMIT = 0, 1, 2
CTRL = 900                                       # heap-only pseudo event: runs a callback, writes nothing
FAIL_NAMES = ["", "INSUFFICIENT_BALANCE", "LIMIT_EXCEEDED"]


class Ev:
    __slots__ = ("ts", "typ", "src", "dst", "amount", "amount_fn", "device", "channel", "area", "label",
                 "cb", "normal", "topup", "fit", "min_amt", "meta")

    def __init__(self, ts, typ, src, dst, amount=None, amount_fn=None, device=None, channel=None, area=None,
                 label=None, cb=None, normal=False, topup=False, fit=False, min_amt=1.0, meta=None):
        self.ts, self.typ, self.src, self.dst = int(ts), typ, src, dst
        self.amount, self.amount_fn = amount, amount_fn
        self.device, self.channel, self.area = device, channel, area
        self.label, self.cb = label, cb
        self.normal, self.topup, self.fit, self.min_amt, self.meta = normal, topup, fit, min_amt, meta


class Sim:
    def __init__(self, world: World, cfg: dict, rng: np.random.Generator):
        self.w, self.cfg, self.rng = world, cfg, rng
        self.end_ts = cfg["world"]["n_days"] * DAY
        w = world
        self.bal = [0.0] * len(w.ids)
        for i, a in enumerate(w.agents):
            self.bal[a] = float(w.agent_float[i])
        for ci in range(w.n_cust):
            self.bal[w.acct_of(ci)] = w.c_init_bal[ci]
        self.limits = {1: cfg["limits"]["KYC1"], 2: cfg["limits"]["KYC2"]}
        self.fee_rate = cfg["fees"]["cash_out_rate"]
        self.sm_fee_above = cfg["fees"]["send_money_flat_above"]
        self.sm_fee = cfg["fees"]["send_money_fee"]
        start = w.start.astype("datetime64[D]")
        days = start + np.arange(cfg["world"]["n_days"] + 3)
        self.month_of_day = days.astype("datetime64[M]").astype(int).tolist()
        self.lim_state: dict = {}
        self.heap: list = []
        self.seq = 0
        self.labels: list = []
        self._label_idx: dict = {}
        self.cols = {k: [] for k in ("ts", "typ", "src", "dst", "amt", "fee", "fail", "sb0", "sb1", "rb0", "rb1",
                                     "dev", "chan", "area", "label")}
        self.acct_events: list = []            # (ts, acct, code, device, area, channel, label_idx)
        self.suppress_from: dict = {}          # acct -> ts after which its normal activity stops
        self.quiet: dict = {}                  # acct -> [(start, end)]: no normal events (keeps planted demos exact)
        self.protected: set = set()            # planted wallets: gang warm-up traffic never touches them
        self.now = 0

    # ------------------------------------------------------------------ wallet management
    def ensure_account(self, acct: int):
        while len(self.bal) <= acct:
            self.bal.append(0.0)

    def label_id(self, label):
        if label is None:
            return -1
        i = self._label_idx.get(label)
        if i is None:
            i = len(self.labels)
            self.labels.append(label)
            self._label_idx[label] = i
        return i

    def push(self, ev: Ev):
        if ev.ts >= self.end_ts:
            return
        heapq.heappush(self.heap, (ev.ts, self.seq, ev))
        self.seq += 1

    def record_acct_event(self, ts, acct, code, device=-1, area=-1, channel=CH["APP"], label=None):
        self.acct_events.append((int(ts), acct, code, device, area, channel, self.label_id(label)))

    # ------------------------------------------------------------------ limits / fees
    def fee(self, typ, amount):
        if typ == T["CASH_OUT"]:
            return round(amount * self.fee_rate, 2)
        if typ == T["SEND_MONEY"] and amount > self.sm_fee_above:
            return float(self.sm_fee)
        return 0.0

    def allowance(self, cust, ltype, ts):
        w = self.w
        lim = self.limits[w.c_kyc[w.cust_of(cust)]][ltype]
        day = ts // DAY
        month = self.month_of_day[day]
        st = self.lim_state.get((cust, ltype))
        d_amt = d_cnt = m_amt = 0.0
        if st is not None:
            if st[0] == day:
                d_amt, d_cnt = st[1], st[2]
            if st[3] == month:
                m_amt = st[4]
        if d_cnt >= lim["daily_count"]:
            return 0.0
        return float(min(lim["per_txn"], lim["daily_amount"] - d_amt, lim["monthly_amount"] - m_amt))

    def _consume(self, cust, ltype, ts, amount):
        day = ts // DAY
        month = self.month_of_day[day]
        st = self.lim_state.get((cust, ltype))
        if st is None:
            st = [day, 0.0, 0, month, 0.0]
        if st[0] != day:
            st[0], st[1], st[2] = day, 0.0, 0
        if st[3] != month:
            st[3], st[4] = month, 0.0
        st[1] += amount
        st[2] += 1
        st[4] += amount
        self.lim_state[(cust, ltype)] = st

    # ------------------------------------------------------------------ main loop
    def run(self, normal: dict):
        ts_a, typ_a, src_a, dst_a = normal["ts"], normal["typ"], normal["src"], normal["dst"]
        amt_a, area_a, dev_a = normal["amount"], normal["area"], normal["dev"]
        n = len(ts_a)
        ts_l, typ_l, src_l, dst_l = ts_a.tolist(), typ_a.tolist(), src_a.tolist(), dst_a.tolist()
        amt_l, area_l, dev_l = amt_a.tolist(), area_a.tolist(), dev_a.tolist()
        heap = self.heap
        i = 0
        end = self.end_ts
        while True:
            if i < n and (not heap or ts_l[i] <= heap[0][0]):
                ts, typ = ts_l[i], typ_l[i]
                self.now = ts
                if typ >= 100:
                    self._acct_event_normal(ts, typ, src_l[i], dev_l[i], area_l[i])
                else:
                    self.execute(ts, typ, src_l[i], dst_l[i], amt_l[i], None, None,
                                 area_l[i] if area_l[i] >= 0 else None, None, None, True, True, False, 1.0, None)
                i += 1
            elif heap:
                ts, _, ev = heapq.heappop(heap)
                if ts >= end:
                    continue
                self.now = ts
                if ev.typ >= CTRL:                       # control step: decide what happens next
                    ev.cb(self, ev, True, -1, 0.0)
                    continue
                if ev.meta == "warmup" and (ev.dst in self.protected or ev.dst in self.suppress_from):
                    continue
                if ev.typ >= 100:
                    self._acct_event_fraud(ev)
                else:
                    amount = ev.amount
                    if ev.amount_fn is not None:
                        amount = ev.amount_fn(self, ev)
                    if amount is None or amount < ev.min_amt:
                        if ev.cb:
                            ev.cb(self, ev, False, -1, 0.0)
                        continue
                    self.execute(ev.ts, ev.typ, ev.src, ev.dst, float(amount), ev.device, ev.channel, ev.area,
                                 ev.label, ev.cb, ev.normal, ev.topup, ev.fit, ev.min_amt, ev)
            else:
                break

    def _acct_event_normal(self, ts, code, acct, dev, area):
        sf = self.suppress_from.get(acct)
        if sf is not None and ts >= sf:
            return
        w = self.w
        ci = w.cust_of(acct)
        if code == A["DEVICE_CHANGE"] and dev >= 0:
            w.c_device[ci] = dev
        self.record_acct_event(ts, acct, code, dev, area, w.c_chan[ci], None)

    def _acct_event_fraud(self, ev: Ev):
        w = self.w
        if ev.meta == "set_device" and ev.device is not None:
            w.c_device[w.cust_of(ev.src)] = ev.device
        ch = ev.channel if ev.channel is not None else w.c_chan[w.cust_of(ev.src)]
        self.record_acct_event(ev.ts, ev.src, ev.typ, -1 if ev.device is None else ev.device,
                               -1 if ev.area is None else ev.area, ch, ev.label)
        if ev.cb:
            ev.cb(self, ev, True, -1, 0.0)

    # ------------------------------------------------------------------ execution
    def execute(self, ts, typ, src, dst, amount, device, channel, area, label, cb, normal, topup, fit, min_amt, ev):
        w = self.w
        if normal and self.suppress_from:
            sf = self.suppress_from
            if (src in sf and ts >= sf[src]) or (dst in sf and ts >= sf[dst]):
                return -1
        if normal and self.quiet:
            for acct in (src, dst):
                for a, b in self.quiet.get(acct, ()):
                    if a <= ts < b:
                        return -1
        lt = LIMIT_TYPE.get(typ)
        cust = None
        if lt is not None:
            cust = src if lt[1] == 0 else dst
            if not w.is_customer(cust):
                cust = None
        if fit and cust is not None:
            allow = self.allowance(cust, lt[0], ts)
            if typ == T["CASH_OUT"] or typ == T["SEND_MONEY"]:
                allow = min(allow, (self.bal[src] - 10) / (1 + (self.fee_rate if typ == T["CASH_OUT"] else 0)))
            if amount > allow:
                amount = math.floor(allow / 10) * 10
            if amount < min_amt:
                if cb:
                    cb(self, ev, False, -1, 0.0)
                return -1
        fee = self.fee(typ, amount)
        bal = self.bal
        tracked_src = w.kind[src] != "X"
        tracked_dst = w.kind[dst] != "X"
        # --- KYC limit
        if cust is not None and amount > self.allowance(cust, lt[0], ts) + 1e-6:
            return self._record(ts, typ, src, dst, amount, 0.0, FAIL_LIMIT, device, channel, area, label, cb, ev)
        # --- balance
        if tracked_src and bal[src] + 1e-6 < amount + fee:
            kind = w.kind[src]
            if kind == "A":
                self._float_topup(ts, src, amount)
            elif kind == "C" and topup and 8 <= (ts % DAY) / 3600 < 21.5 and self.rng.random() < 0.8:
                if self._cash_in_then_retry(ts, typ, src, dst, amount, fee, device, channel, area, label, cb,
                                            normal, ev):
                    return -1
                return self._record(ts, typ, src, dst, amount, 0.0, FAIL_FUNDS, device, channel, area, label, cb, ev)
            else:
                return self._record(ts, typ, src, dst, amount, 0.0, FAIL_FUNDS, device, channel, area, label, cb, ev)
        return self._record(ts, typ, src, dst, amount, fee, FAIL_NONE, device, channel, area, label, cb, ev,
                            cust=cust, ltype=lt[0] if lt else None)

    def _record(self, ts, typ, src, dst, amount, fee, fail, device, channel, area, label, cb, ev,
                cust=None, ltype=None):
        w, bal, c = self.w, self.bal, self.cols
        tracked_src = w.kind[src] != "X"
        tracked_dst = w.kind[dst] != "X"
        sb0 = bal[src] if tracked_src else math.nan
        rb0 = bal[dst] if tracked_dst else math.nan
        if fail == FAIL_NONE:
            if tracked_src:
                bal[src] = round(bal[src] - amount - fee, 2)
            if tracked_dst:
                bal[dst] = round(bal[dst] + amount, 2)
            if cust is not None:
                self._consume(cust, ltype, ts, amount)
        # device / channel / area resolution
        if device is None or channel is None:
            if typ in CUSTOMER_INITIATED and w.is_customer(src):
                ci = w.cust_of(src)
                device = w.c_device[ci] if device is None else device
                channel = w.c_chan[ci] if channel is None else channel
            elif typ == T["ADD_MONEY"] and w.is_customer(dst):
                ci = w.cust_of(dst)
                device = w.c_device[ci] if device is None else device
                channel = w.c_chan[ci] if channel is None else channel
            elif typ == T["CASH_IN"] and w.kind[src] == "A":
                device = w.agent_local[src] if device is None else device
                channel = CH["AGENT"] if channel is None else channel
            else:
                device = -1 if device is None else device
                channel = CH["SYSTEM"] if channel is None else channel
        if area is None:
            if w.kind[dst] == "A":
                area = w.acct_area[dst]
            elif w.kind[src] == "A":
                area = w.acct_area[src]
            elif w.is_customer(src):
                area = w.acct_area[src]
            elif w.is_customer(dst):
                area = w.acct_area[dst]
            else:
                area = -1
        c["ts"].append(ts); c["typ"].append(typ); c["src"].append(src); c["dst"].append(dst)
        c["amt"].append(amount); c["fee"].append(fee); c["fail"].append(fail)
        c["sb0"].append(sb0); c["sb1"].append(bal[src] if tracked_src else math.nan)
        c["rb0"].append(rb0); c["rb1"].append(bal[dst] if tracked_dst else math.nan)
        c["dev"].append(device); c["chan"].append(channel); c["area"].append(area)
        c["label"].append(self.label_id(label))
        row = len(c["ts"]) - 1
        if cb:
            cb(self, ev, fail == FAIL_NONE, row, amount)
        return row

    def _float_topup(self, ts, agent, need):
        amt = math.ceil((need - self.bal[agent] + 200_000) / 50_000) * 50_000
        self._record(ts, T["FLOAT_TOPUP"], self.w.ext["X_BANK"], agent, float(amt), 0.0, FAIL_NONE,
                     -1, CH["SYSTEM"], self.w.acct_area[agent], None, None, None)

    def _cash_in_then_retry(self, ts, typ, src, dst, amount, fee, device, channel, area, label, cb, normal, ev):
        """Customer is short: walks to their agent, cashes in, retries a few minutes later."""
        w, rng = self.w, self.rng
        ci = w.cust_of(src)
        agent = w.c_home_agents[ci][0]
        need = amount + fee - self.bal[src]
        amt = math.ceil((need + rng.uniform(0, 1500)) / 500) * 500
        allow = self.allowance(src, "cash_in", ts)
        if amt > allow:
            amt = math.floor(allow / 100) * 100
            if amt < need:
                return False
        if self.bal[agent] < amt:
            self._float_topup(ts, agent, amt)
        self.execute(ts, T["CASH_IN"], agent, src, float(amt), None, None, None, None, None, False, False, False, 1, None)
        retry_ts = ts + int(rng.uniform(240, 1800))
        if ev is None:
            ev = Ev(retry_ts, typ, src, dst, amount, device=device, channel=channel, area=area, label=label, cb=cb,
                    normal=normal)
        else:
            ev.ts = retry_ts
        ev.topup = False
        ev.amount, ev.amount_fn = amount, None
        self.push(ev)
        return True
