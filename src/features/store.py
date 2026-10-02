"""Stateful streaming feature store.

The same object serves batch replay (training) and online scoring (API): for each
transaction we first `compute()` features from state built ONLY from earlier events, then
`update()` the state. That ordering is the leakage guarantee, and tests/test_features.py
checks it by truncating the future and comparing features.
"""
from __future__ import annotations

import math
from collections import deque

DAY, HOUR = 86_400, 3_600
TYPES = ["SEND_MONEY", "CASH_OUT", "CASH_IN", "PAYMENT", "BILL_PAY", "MOBILE_RECHARGE", "ADD_MONEY", "SALARY",
         "REMITTANCE_IN", "FLOAT_TOPUP"]
TYPE_CODE = {t: i for i, t in enumerate(TYPES)}
OUTGOING = {"SEND_MONEY", "CASH_OUT", "PAYMENT", "BILL_PAY", "MOBILE_RECHARGE"}
INCOMING = {"CASH_IN", "ADD_MONEY", "SALARY", "REMITTANCE_IN"}
MONEY_OUT = {"SEND_MONEY", "CASH_OUT"}                 # money leaving towards people / cash
SCORED_TYPES = ["SEND_MONEY", "CASH_OUT", "PAYMENT", "ADD_MONEY"]
CHANNEL_CODE = {"APP": 0, "USSD": 1, "AGENT": 2, "SYSTEM": 3}
KIND_CODE = {"C": 0, "A": 1, "M": 2, "B": 3, "X": 4}
CAP_H = 720.0
NAN = float("nan")

FEATURE_GROUPS = {
    "transaction": ["f_type", "amount", "log_amount", "hour", "is_night", "dow", "is_weekend", "channel",
                    "is_round_100", "is_round_1000"],
    "behaviour": ["cust_age_days", "cust_kyc2", "cust_bal_log", "drain_ratio", "cust_n_prior_out", "amount_z",
                  "amount_vs_max", "cust_out_cnt_1h", "cust_out_cnt_24h", "cust_out_amt_24h", "cust_new_cp_24h",
                  "cust_uniq_cp_1h", "hours_since_last", "hour_surprise", "cust_fail_24h", "cust_woke_gap_days"],
    "device_session": ["is_new_device", "device_age_hours", "cust_n_devices", "device_n_wallets", "channel_switch",
                       "is_new_area", "hrs_since_sim_swap", "hrs_since_pin_reset", "hrs_since_dev_change"],
    "flow": ["cust_in_amt_2h", "mins_since_last_in", "passthrough_ratio", "chain_depth", "cust_in_uniq_24h",
             "cust_in_new_24h"],
    "counterparty": ["cp_kind", "cp_age_days", "pair_first", "pair_n_prior", "pair_reverse", "cp_in_uniq_24h",
                     "cp_in_new_24h", "cp_in_cnt_1h", "cp_in_amt_24h", "cp_out_cnt_24h", "cp_cashout_24h",
                     "cp_woke_gap_days", "cp_n_prior", "cp_device_n_wallets"],
    "agent": ["ag_co_cnt_24h", "ag_co_amt_24h", "ag_co_ratio_7d", "ag_co_new_wallet_share_24h", "ag_night_co_24h"],
    "complaints": ["cust_complaints", "cp_complaints"],
}
STREAM_FEATURES = [f for g in FEATURE_GROUPS.values() for f in g]


class Win:
    """Sliding window of (ts, key, amount, flag) with O(1) unique counts."""
    __slots__ = ("span", "dq", "total", "keys", "fkeys")

    def __init__(self, span):
        self.span = span
        self.dq = deque()
        self.total = 0.0
        self.keys = {}
        self.fkeys = {}

    def trim(self, t):
        lim = t - self.span
        dq = self.dq
        while dq and dq[0][0] <= lim:
            _, k, a, f = dq.popleft()
            self.total -= a
            c = self.keys[k] - 1
            if c:
                self.keys[k] = c
            else:
                del self.keys[k]
            if f:
                c = self.fkeys[k] - 1
                if c:
                    self.fkeys[k] = c
                else:
                    del self.fkeys[k]

    def add(self, t, k, a, f=False):
        self.dq.append((t, k, a, f))
        self.total += a
        self.keys[k] = self.keys.get(k, 0) + 1
        if f:
            self.fkeys[k] = self.fkeys.get(k, 0) + 1


class WalletState:
    __slots__ = ("n_out", "s_log", "ss_log", "max_out", "hist", "n_hist", "last_ts", "wake_ts", "wake_gap",
                 "devices", "areas", "chan_counts", "out24", "out1", "in24", "in1", "inflows", "fails", "sent_to",
                 "recv_from", "sim_ts", "pin_ts", "dev_ts", "complaints", "n_txn", "last_device", "cashout24")

    def __init__(self):
        self.n_out = 0
        self.s_log = 0.0
        self.ss_log = 0.0
        self.max_out = 0.0
        self.hist = [0] * 24
        self.n_hist = 0
        self.last_ts = None
        self.wake_ts = None
        self.wake_gap = 0.0
        self.devices = {}
        self.areas = set()
        self.chan_counts = {}
        self.out24 = Win(DAY)
        self.out1 = Win(HOUR)
        self.in24 = Win(DAY)
        self.in1 = Win(HOUR)
        self.inflows = deque()                       # (ts, amount, depth) for pass-through, 2 h
        self.fails = deque()
        self.sent_to = {}
        self.recv_from = set()
        self.sim_ts = None
        self.pin_ts = None
        self.dev_ts = None
        self.complaints = 0
        self.n_txn = 0
        self.last_device = None
        self.cashout24 = Win(DAY)


class AgentState:
    __slots__ = ("co24", "co7", "night24", "seen")

    def __init__(self):
        self.co24 = Win(DAY)                         # key = customer, flag = customer younger than 7 days
        self.co7 = Win(7 * DAY)
        self.night24 = Win(DAY)
        self.seen = set()


class FeatureStore:
    def __init__(self, start_ts, signup: dict, kyc: dict, onboard: dict, passthrough_min: int = 120):
        """signup/kyc: customer wallet -> seconds since start / 1|2; onboard: agent/merchant -> seconds."""
        self.start_ts = start_ts
        self.signup, self.kyc, self.onboard = signup, kyc, onboard
        self.pt_win = passthrough_min * 60
        self.w: dict[str, WalletState] = {}
        self.a: dict[str, AgentState] = {}
        self.dev_wallets: dict[str, set] = {}
        self.pop_mu, self.pop_sd = 6.5, 1.1           # prior for log-amount when a wallet has little history

    def _ws(self, k):
        s = self.w.get(k)
        if s is None:
            s = self.w[k] = WalletState()
        return s

    def _as(self, k):
        s = self.a.get(k)
        if s is None:
            s = self.a[k] = AgentState()
        return s

    # ------------------------------------------------------------------ side streams
    def apply_event(self, t, wallet, etype, device):
        s = self._ws(wallet)
        if etype == "SIM_SWAP":
            s.sim_ts = t
        elif etype == "PIN_RESET":
            s.pin_ts = t
        elif etype == "DEVICE_CHANGE":
            s.dev_ts = t
            if device:
                s.devices.setdefault(device, t)
                self.dev_wallets.setdefault(device, set()).add(wallet)

    def apply_complaint(self, wallet):
        self._ws(wallet).complaints += 1

    # ------------------------------------------------------------------ features
    def compute(self, t, typ, src, src_kind, dst, dst_kind, amount, sb0, rb0, device, channel, area, dow):
        outgoing = typ in OUTGOING
        if outgoing and src_kind == "C":
            cust, cp, cp_kind, bal = src, dst, dst_kind, sb0
        elif typ in INCOMING and dst_kind == "C":
            cust, cp, cp_kind, bal = dst, src, src_kind, rb0
        else:
            cust, cp, cp_kind, bal = None, dst, dst_kind, NAN
        hour = int((t % DAY) // HOUR)
        la = math.log1p(amount)
        f = [TYPE_CODE[typ], amount, la, hour, 1 if hour < 6 else 0, dow, 1 if dow in (4, 5) else 0,
             CHANNEL_CODE.get(channel, 3), 1 if amount % 100 == 0 else 0, 1 if amount % 1000 == 0 else 0]
        # ---------------- customer behaviour
        if cust is not None:
            s = self._ws(cust)
            for win in (s.out24, s.out1, s.in24, s.in1, s.cashout24):
                win.trim(t)
            su = self.signup.get(cust)
            age = (t - su) / DAY if su is not None else NAN
            n = s.n_out
            k = 3.0
            mu = (s.s_log + k * self.pop_mu) / (n + k)
            var = (s.ss_log + k * (self.pop_sd ** 2 + self.pop_mu ** 2)) / (n + k) - mu * mu
            z = (la - mu) / math.sqrt(max(var, 0.05)) if outgoing else 0.0
            vs_max = amount / (s.max_out + 1.0) if (outgoing and n) else NAN
            while s.fails and s.fails[0] <= t - DAY:
                s.fails.popleft()
            hs = -math.log((s.hist[hour] + 0.5) / (s.n_hist + 12.0))
            hrs_last = min((t - s.last_ts) / HOUR, CAP_H) if s.last_ts is not None else CAP_H
            woke = s.wake_gap if (s.wake_ts is not None and t - s.wake_ts < 3 * DAY) else 0.0
            if s.last_ts is not None and t - s.last_ts > 7 * DAY:
                woke = (t - s.last_ts) / DAY
            new_cp = len(s.out24.fkeys)
            f += [age, 1 if self.kyc.get(cust) == 2 else 0,
                  math.log1p(bal) if bal == bal and bal >= 0 else NAN,
                  amount / (bal + 1.0) if (outgoing and bal == bal) else 0.0,
                  math.log1p(n), z, vs_max, len(s.out1.dq), len(s.out24.dq), math.log1p(max(s.out24.total, 0)),
                  new_cp, len(s.out1.keys), hrs_last, hs, len(s.fails), woke]
            # ---------------- device / session (only when the customer drives the device)
            if device and channel in ("APP", "USSD"):
                first = s.devices.get(device)
                is_new = 1 if first is None else 0
                dage = 0.0 if first is None else min((t - first) / HOUR, CAP_H)
                dw = self.dev_wallets.get(device)
                ndw = (len(dw) + (0 if dw and cust in dw else 1)) if dw else 1
                top = max(s.chan_counts, key=s.chan_counts.get) if s.chan_counts else channel
                chan_sw = 1 if channel != top else 0
            else:
                is_new, dage, ndw, chan_sw = NAN, NAN, NAN, NAN
            f += [is_new, dage, len(s.devices), ndw, chan_sw,
                  (1 if area not in s.areas else 0) if (area and s.areas) else 0,
                  min((t - s.sim_ts) / HOUR, CAP_H) if s.sim_ts is not None else CAP_H,
                  min((t - s.pin_ts) / HOUR, CAP_H) if s.pin_ts is not None else CAP_H,
                  min((t - s.dev_ts) / HOUR, CAP_H) if s.dev_ts is not None else CAP_H]
            # ---------------- flow / pass-through
            inf = s.inflows
            while inf and inf[0][0] <= t - self.pt_win:
                inf.popleft()
            in2 = sum(x[1] for x in inf)
            last_in = min((t - inf[-1][0]) / 60, 1440.0) if inf else 1440.0
            depth = 0
            if outgoing and typ in MONEY_OUT and in2 >= 0.5 * amount:
                depth = 1 + max(x[2] for x in inf)
            f += [math.log1p(in2), last_in, min(in2 / amount, 5.0) if outgoing else 0.0, depth,
                  len(s.in24.keys), len(s.in24.fkeys)]
            cust_complaints = s.complaints
        else:
            s = None
            f += [NAN] * (len(FEATURE_GROUPS["behaviour"]) + len(FEATURE_GROUPS["device_session"]) +
                          len(FEATURE_GROUPS["flow"]))
            depth = 0
            cust_complaints = NAN
        # ---------------- counterparty
        if cp_kind == "C":
            c = self._ws(cp)
            for win in (c.in24, c.in1, c.out24, c.cashout24):
                win.trim(t)
            su = self.signup.get(cp)
            cp_age = (t - su) / DAY if su is not None else NAN
            if s is not None:
                n_pair = s.sent_to.get(cp, 0) if outgoing else (c.sent_to.get(cust, 0))
                pair_first = 1 if n_pair == 0 else 0
                rev = 1 if (cust in c.sent_to if outgoing else cp in s.sent_to) else 0
            else:
                n_pair, pair_first, rev = 0, 1, 0
            woke = c.wake_gap if (c.wake_ts is not None and t - c.wake_ts < 3 * DAY) else 0.0
            if c.last_ts is not None and t - c.last_ts > 7 * DAY:
                woke = (t - c.last_ts) / DAY
            dw = self.dev_wallets.get(c.last_device) if c.last_device else None
            f += [KIND_CODE["C"], cp_age, pair_first, math.log1p(n_pair), rev, len(c.in24.keys), len(c.in24.fkeys),
                  len(c.in1.dq), math.log1p(max(c.in24.total, 0)), len(c.out24.dq), len(c.cashout24.dq), woke,
                  math.log1p(c.n_txn), len(dw) if dw else 1]
            cp_complaints = c.complaints
        else:
            ob = self.onboard.get(cp)
            cp_age = (t - ob) / DAY if ob is not None else NAN
            if s is not None and cp_kind in ("A", "M"):
                n_pair = s.sent_to.get(cp, 0)
                pair_first = 1 if n_pair == 0 else 0
            else:
                n_pair, pair_first = 0, NAN
            f += [KIND_CODE.get(cp_kind, 4), cp_age, pair_first, math.log1p(n_pair), NAN, NAN, NAN, NAN, NAN, NAN,
                  NAN, NAN, NAN, NAN]
            cp_complaints = NAN
        # ---------------- agent
        if cp_kind == "A" and typ in ("CASH_OUT", "CASH_IN"):
            ag = self._as(cp)
            for win in (ag.co24, ag.co7, ag.night24):
                win.trim(t)
            n24 = len(ag.co24.dq)
            f += [n24, math.log1p(max(ag.co24.total, 0)), ag.co24.total / (ag.co7.total / 7 + 1000.0),
                  (len(ag.co24.fkeys) / len(ag.co24.keys)) if ag.co24.keys else 0.0, len(ag.night24.dq)]
        else:
            f += [NAN] * 5
        f += [cust_complaints, cp_complaints]
        return f, depth

    # ------------------------------------------------------------------ state update
    def update(self, t, typ, src, src_kind, dst, dst_kind, amount, ok, device, channel, area, depth):
        outgoing = typ in OUTGOING
        if not ok:
            if outgoing and src_kind == "C":
                self._ws(src).fails.append(t)
            return
        hour = int((t % DAY) // HOUR)
        for k, kind in ((src, src_kind), (dst, dst_kind)):
            if kind == "C":
                s = self._ws(k)
                if s.last_ts is not None and t - s.last_ts > 7 * DAY:
                    s.wake_ts, s.wake_gap = t, (t - s.last_ts) / DAY
                s.last_ts = t
                s.n_txn += 1
        if src_kind == "C" and outgoing:
            s = self._ws(src)
            la = math.log1p(amount)
            s.n_out += 1
            s.s_log += la
            s.ss_log += la * la
            s.max_out = max(s.max_out, amount)
            s.hist[hour] += 1
            s.n_hist += 1
            new_pair = dst not in s.sent_to
            s.out24.add(t, dst, amount, new_pair)
            s.out1.add(t, dst, amount, new_pair)
            s.sent_to[dst] = s.sent_to.get(dst, 0) + 1
            if typ == "CASH_OUT":
                s.cashout24.add(t, dst, amount)
            if area:
                s.areas.add(area)
            if device and channel in ("APP", "USSD"):
                s.devices.setdefault(device, t)
                s.last_device = device
                self.dev_wallets.setdefault(device, set()).add(src)
                s.chan_counts[channel] = s.chan_counts.get(channel, 0) + 1
            if dst_kind == "C":
                r = self._ws(dst)
                first = src not in r.recv_from
                r.in24.add(t, src, amount, first)
                r.in1.add(t, src, amount, first)
                r.recv_from.add(src)
                r.inflows.append((t, amount, depth))
            elif dst_kind == "A" and typ == "CASH_OUT":
                ag = self._as(dst)
                su = self.signup.get(src)
                young = su is not None and t - su < 7 * DAY
                ag.co24.add(t, src, amount, young)
                ag.co7.add(t, src, amount)
                if hour < 6 or hour >= 23:
                    ag.night24.add(t, src, amount)
        elif dst_kind == "C" and typ in INCOMING:
            r = self._ws(dst)
            r.inflows.append((t, amount, 0))
            r.in24.add(t, src, amount, src not in r.recv_from)
            r.recv_from.add(src)
            if typ == "ADD_MONEY" and device and channel in ("APP", "USSD"):
                r.devices.setdefault(device, t)
                r.last_device = device
                self.dev_wallets.setdefault(device, set()).add(dst)
            if typ == "CASH_IN":
                r.hist[hour] += 1
                r.n_hist += 1
