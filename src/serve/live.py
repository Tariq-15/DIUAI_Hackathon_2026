"""The live demo world behind the customer app and the analyst copilot.

Start-up:
  1. load the trained bundle and the feature store replayed to the end of the 60 days (demo_state.joblib)
  2. move the clock to 09:30 the next morning and STAGE the playbook scenarios as ordinary synthetic
     events (they enter the same feature store the model reads):
       - collector wallet: opened 2 days ago, 14 strangers paid it in the last 3 hours, part cashed out
       - SIM-swap takeover: Salma's SIM replaced, a 'gang phone' linked to 3 young wallets logs in
       - fake online seller: 6 first-time buyers since last night, one already reported it to 16268
  3. rebuild the 24-hour graph snapshot from the recent edges plus the staged ones
Every transfer the app sends is then scored live by the real model (nothing is pre-recorded).

On top of the model, two plain rules can add a one-tap check (NUDGE), never a block: a likely keypad slip from
someone the customer pays often (src/serve/recipient.py), and an amount far above the customer's own habit
(src/serve/habits.py, thresholds learned with federated analytics in src/fl/amounts.py). Mobile recharges are not
scored by the model (it was not trained on them); they get the amount-habit check and a rapid-recharge rule.

Policy, in plain code: bands come from the bundle's policy; on top of it an analyst's flag gives any
later transfer to that wallet the strongest warning. Prohori only warns: no transfer is held and nothing waits
for a person at upay. The customer cancels or sends after every warning (one tap for a NUDGE, the PIN again for
STEP_UP and HOLD); analysts see the same alerts afterwards. Every decision lands in a hash-chained audit log.
"""
from __future__ import annotations

import copy
import gc
import gzip
import hashlib
import json
import pickle
import re
import threading
import time
from datetime import date
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from src.common.config import ROOT
from src.models.explain import bn as bn_num
from . import complaints as cmp
from . import copilot
from . import recipient as rcheck
from .habits import Habits
from src.features.graph import graph_snapshot, nx
from .scorer import RiskEngine, kind_of

DAY, HOUR, MIN = 86_400, 3_600, 60
LIVE_START = 60 * DAY + 9 * HOUR + 30 * MIN          # 31 May 2026, 09:30: the morning after the 60 days
CONTACT_NAMES = {"rahim": [("মা", "Mother"), ("ছোট ভাই", "Younger brother"), ("করিম (রুমমেট)", "Karim (roommate)"),
                           ("নাসির ভাই", "Nasir bhai")],
                 "salma": [("স্বামী", "Husband"), ("পাইকার রফিক", "Rafiq (wholesaler)"), ("বোন", "Sister"),
                           ("দোকানের কর্মচারী", "Shop assistant")]}
PERSONA_NAMES = {"rahim": ("রহিম", "Rahim", "গার্মেন্টস কর্মী, খুলনা", "Garment worker, Khulna"),
                 "salma": ("সালমা", "Salma", "দোকান মালিক, খুলনা", "Shop owner, Khulna")}
STAGED = {"collector": "W9000001", "mule1": "W9000011", "mule2": "W9000012", "mule3": "W9000013", "seller": "W9000020"}
GANG_PHONE, COLLECTOR_PHONE = "DV9000099", "DV9000001"
SELLER = dict(buyers=6, gap_min=75, reported=True, cashout=False, age_days=20)
# HOLD is the name of the top score band (>= 80). It no longer holds the transfer: it is the strongest warning.
CHOICES = {"NUDGE": ("cancel", "confirm"), "STEP_UP": ("cancel", "confirm_pin"), "HOLD": ("cancel", "confirm_pin")}
CASE_LABELS = {"genuine_wrong_send": "Genuine wrong send (keypad slip)", "likely_scam_victim": "Likely scam victim",
               "needs_review": "Wrong send: needs review", "needs_details": "No matching transfer: ask for details"}
SCAM_EVIDENCE = {"reported", "many_senders", "new_recipient", "chain", "collector_cashout", "network_pattern", "shared_device"}
COMPLAINT_STEPS_BN = ["গৃহীত", "পর্যালোচনা চলছে", "পদক্ষেপ নেওয়া হয়েছে", "নিষ্পত্তি"]
RECHARGE = dict(min=10.0, max=1000.0, biller="B009", burst_window=HOUR, burst_count=3)   # synthetic limits

FEATURE_LABELS = {
    "cp_age_days": "Recipient wallet age (days)", "cp_in_uniq_24h": "Different senders to recipient, 24 h",
    "cp_in_new_24h": "First-time senders to recipient, 24 h", "cp_in_cnt_1h": "Payments into recipient, last hour",
    "cp_in_amt_24h": "Money into recipient, 24 h (log)", "cp_out_cnt_24h": "Recipient's outgoing transfers, 24 h",
    "cp_cashout_24h": "Recipient's cash-outs, 24 h", "cp_n_prior": "Recipient's past activity (log)",
    "cp_device_n_wallets": "Wallets on the recipient's phone", "cp_complaints": "16268 reports on recipient",
    "cp_woke_gap_days": "Recipient dormant gap (days)", "cp_kind": "Recipient type", "pair_first": "First transfer to this recipient",
    "pair_n_prior": "Earlier transfers to this recipient (log)", "pair_reverse": "Recipient has paid the sender before",
    "amount": "Amount (Tk)", "log_amount": "Amount (log)", "amount_z": "Amount vs own history (z)",
    "amount_vs_max": "Amount / largest earlier transfer", "drain_ratio": "Share of balance sent",
    "cust_bal_log": "Sender balance (log)", "hour": "Hour of day", "is_night": "Night (00-06)", "hour_surprise": "Unusual hour for this sender",
    "dow": "Day of week", "is_weekend": "Weekend", "channel": "Channel (app/USSD)", "f_type": "Transaction type",
    "is_round_100": "Round amount (100)", "is_round_1000": "Round amount (1,000)", "cust_age_days": "Sender account age (days)",
    "cust_kyc2": "Sender full KYC", "cust_n_prior_out": "Sender's past transfers (log)", "cust_out_cnt_1h": "Sender transfers, last hour",
    "cust_out_cnt_24h": "Sender transfers, 24 h", "cust_out_amt_24h": "Sender money out, 24 h (log)",
    "cust_new_cp_24h": "New recipients today", "cust_uniq_cp_1h": "Different recipients, last hour",
    "hours_since_last": "Hours since sender's last transaction", "cust_fail_24h": "Failed attempts, 24 h",
    "cust_woke_gap_days": "Sender dormant gap (days)", "is_new_device": "New phone", "device_age_hours": "Hours this phone has been on the account",
    "cust_n_devices": "Phones used by the sender", "device_n_wallets": "Wallets on this phone", "channel_switch": "Unusual channel",
    "is_new_area": "New area", "hrs_since_sim_swap": "Hours since SIM swap", "hrs_since_pin_reset": "Hours since PIN reset",
    "hrs_since_dev_change": "Hours since phone change", "cust_in_amt_2h": "Money received, last 2 h (log)",
    "mins_since_last_in": "Minutes since money came in", "passthrough_ratio": "Received money passed straight on",
    "chain_depth": "Hops in a fast money chain", "cust_in_uniq_24h": "Different payers to sender, 24 h",
    "cust_in_new_24h": "First-time payers to sender, 24 h", "ag_co_cnt_24h": "Agent cash-outs, 24 h",
    "ag_co_amt_24h": "Agent cash-out volume, 24 h (log)", "ag_co_ratio_7d": "Agent volume vs its week",
    "ag_co_new_wallet_share_24h": "Agent share from young wallets", "ag_night_co_24h": "Agent night cash-outs",
    "cust_complaints": "16268 reports on sender", "g_cust_in_deg": "Graph: sender in-degree", "g_cust_out_deg": "Graph: sender out-degree",
    "g_cust_pagerank": "Graph: sender PageRank", "g_cust_ff_comp": "Graph: sender fast-flow ring size",
    "g_cust_nbr_complained": "Graph: reported neighbours of sender", "g_cp_in_deg": "Graph: recipient in-degree",
    "g_cp_out_deg": "Graph: recipient out-degree", "g_cp_pagerank": "Graph: recipient PageRank",
    "g_cp_ff_comp": "Graph: recipient fast-flow ring size", "g_cp_two_hop_in": "Graph: wallets two hops upstream",
    "g_cp_nbr_complained": "Graph: reported neighbours of recipient",
}


def _clean(v):
    if isinstance(v, (np.floating, float)):
        return None if np.isnan(v) else round(float(v), 4)
    if isinstance(v, (np.integer,)):
        return int(v)
    return v


class LiveWorld:
    def __init__(self, artifacts_dir: str | Path | None = None, seller: dict | None = None):
        self.dir = Path(artifacts_dir) if artifacts_dir else ROOT / "artifacts"
        self.seller_cfg = dict(SELLER, **(seller or {}))
        self.lock = threading.RLock()
        self._base_world = joblib.load(self.dir / "demo_world.joblib")
        self.habits = Habits(self.dir)
        self.reset()

    @classmethod
    def from_snapshot(cls, path: str | Path, bundle: dict) -> "LiveWorld":
        """Start from a world staged earlier (portable.save_world): no re-staging and no model pickles on disk.
        Used by the in-browser build; a demo reset reloads the same snapshot."""
        self = cls.__new__(cls)
        self.dir = Path(path).parent
        self.lock = threading.RLock()
        self.seller_cfg = dict(SELLER)
        self._snapshot_path, self._bundle, self.engine = Path(path), bundle, None
        self.habits = Habits(self.dir)
        self.reset()
        return self

    def snapshot(self) -> dict:
        """Everything a fresh, staged world needs, without the model (that is saved separately)."""
        return dict(state=self.engine.state, now=self.engine.now, edges=self.edges, complained=self.complained,
                    alerts=self.alerts, order=self.order, personas=self.personas, staged_agent=self.staged_agent,
                    habit_extra=self.habits.extra, world={k: v for k, v in self.world.items() if k != "edges"})

    def _restore(self):
        self.engine = self.edges = self.alerts = None
        gc.collect()
        with gzip.open(self._snapshot_path, "rb") as f:
            snap = pickle.load(f)
        self.engine = RiskEngine(self.dir, bundle=self._bundle, state=snap["state"])
        self.engine.now = snap["now"]
        self.world, self.start = snap["world"], self.engine.start
        self.edges, self.complained = snap["edges"], snap["complained"]
        self.alerts, self.order, self.personas = snap["alerts"], snap["order"], snap["personas"]
        self.staged_agent = snap["staged_agent"]
        self.habits.reset(snap.get("habit_extra"))
        self.flagged, self.audit, self.n_live = {}, [], 0
        self._lookups()
        self.t0, self.wall0 = LIVE_START, time.time()
        self._audit("system", "system", "demo.reset", detail={"clock": self.iso(LIVE_START), "from": "staged snapshot"})

    def _lookups(self):
        """Wallet -> its own number (the first one registered), slip costs, counters for this session."""
        self.msisdn_of = {}
        for m, w in self.engine.state["msisdn"].items():
            self.msisdn_of.setdefault(w, m)
        here = [self.dir / "slip_costs.json", self.dir / "portable" / "slip_costs.json"]
        self.costs = rcheck.load_costs(next((c for c in here if c.exists()), None))
        kit = next((k for k in (self.dir / "test_kit.json", self.dir / "portable" / "test_kit.json") if k.exists()), None)
        self.kit = json.loads(kit.read_text(encoding="utf-8")) if kit else None
        self.typed, self.n_tx, self.n_complaints, self.recharges = {}, 0, 0, []

    # ------------------------------------------------------------------ set-up
    def reset(self):
        with self.lock:
            if getattr(self, "_snapshot_path", None):
                self._restore()
                return
            if getattr(self, "engine", None) is None:
                self.engine = RiskEngine(self.dir)
            else:                                         # keep the model, swap only the feature store (memory)
                self.edges = self.alerts = None
                self.engine.load_state()
            self.world = copy.deepcopy(self._base_world)
            self.start = self.engine.start
            cols = ["ts", "src", "dst", "amount", "type"] + (["txn_id"] if "txn_id" in self.world["edges"] else [])
            self.edges: list[tuple] = [tuple(r) if len(r) == 6 else tuple(r) + (f"H-{i}",)
                                       for i, r in enumerate(self.world["edges"][cols].itertuples(index=False))]
            self.complained = set(self.world["complained"])
            self.alerts: dict[str, dict] = {}
            self.order: list[str] = []
            for a in self.world["alerts"]:
                self.alerts[a["id"]] = dict(a, status="historical", customer_choice=None)
                self.order.append(a["id"])
            self.flagged: dict[str, str] = {}
            self.audit: list[dict] = []
            self.n_live = 0
            self.personas = self._personas()
            self.habits.reset()
            self._stage()
            self._rebuild_graph(LIVE_START)
            self.engine.now = LIVE_START
            self._lookups()
            self._scenarios()
            self.t0, self.wall0 = LIVE_START, time.time()
            self._audit("system", "system", "demo.reset", detail={"clock": self.iso(LIVE_START)})

    def clock(self) -> int:
        return int(self.t0 + (time.time() - self.wall0))

    def iso(self, t: int) -> str:
        return (self.start + pd.Timedelta(seconds=int(t))).isoformat()

    def when(self, t: int) -> str:
        return (self.start + pd.Timedelta(seconds=int(t))).strftime("%H:%M on %d %b %Y")

    def _personas(self) -> dict:
        out = {}
        for key, p in self.world["personas"].items():
            bn_name, en_name, role_bn, role_en = PERSONA_NAMES.get(key, (key, key, "", ""))
            names = CONTACT_NAMES.get(key, [])
            contacts = [dict(c, name=names[i][0] if i < len(names) else f"পরিচিত {i + 1}",
                             name_en=names[i][1] if i < len(names) else f"Contact {i + 1}") for i, c in enumerate(p["contacts"])]
            out[key] = dict(p, key=key, name_bn=bn_name, name_en=en_name, role_bn=role_bn, role_en=role_en, contacts=contacts,
                            scenarios=[])
        return out

    def _register(self, wallet: str, msisdn: str, opened: int, kyc: int = 2):
        st = self.engine.state
        self.engine.store.signup[wallet] = opened
        self.engine.store.kyc[wallet] = kyc
        st["msisdn"][msisdn] = wallet
        st["balances"].setdefault(wallet, 0.0)

    def _commit(self, t, src, dst, amount, typ="SEND_MONEY", device=None, channel="APP", txn_id=None) -> str:
        """A confirmed transfer enters the same feature store, balances and edge list the model reads."""
        self.engine.score(dict(sender_id=src, receiver_id=dst, amount=float(amount), txn_type=typ,
                               device_id=device, channel=channel, ts_sec=int(t)), commit=True)
        txn_id = txn_id or f"S-{len(self.edges)}"
        self.edges.append((int(t), src, dst, float(amount), typ, txn_id))
        if typ == "SEND_MONEY" and src.startswith("W"):
            self.habits.add(src, "send", amount, t)
        return txn_id

    def _stage(self):
        T = LIVE_START
        store, st = self.engine.store, self.engine.state
        rng = np.random.default_rng(7)
        reserved = {p["wallet"] for p in self.personas.values()} | {c["wallet"] for p in self.personas.values() for c in p["contacts"]}
        pool = sorted(w for w, s in store.w.items() if str(w).startswith("W") and s.last_device and s.n_out >= 5
                      and w not in reserved and w not in self.complained and s.complaints == 0)
        people = [str(x) for x in rng.choice(pool, 20, replace=False)]
        agent = (self.world["agents"].get("sc06") or {}).get("agent") or sorted(a for a in store.a)[0]
        C, M1, M2, M3, S = (STAGED[k] for k in ("collector", "mule1", "mule2", "mule3", "seller"))
        self._register(C, "01090000001", T - 2 * DAY - 3 * HOUR, kyc=2)
        self._register(S, "01090000020", T - self.seller_cfg["age_days"] * DAY, kyc=2)
        for i, (m, age) in enumerate(((M1, 9), (M2, 30), (M3, 15))):
            self._register(m, f"0109000001{i + 1}", T - age * DAY, kyc=1)
            ws = store._ws(m)
            ws.devices[GANG_PHONE] = T - age * DAY
            ws.last_device = GANG_PHONE
            store.dev_wallets.setdefault(GANG_PHONE, set()).add(m)
        store._ws(C).last_device = COLLECTOR_PHONE
        store._ws(C).devices[COLLECTOR_PHONE] = T - 2 * DAY - 3 * HOUR
        store.dev_wallets.setdefault(COLLECTOR_PHONE, set()).add(C)

        ev = []                                           # (t, order, fn, args): applied in time order
        # fake online seller: first-time buyers since last night; optionally one already reported it to 16268
        sc = self.seller_cfg
        for i, w in enumerate(people[14:14 + sc["buyers"]]):
            ev.append((T - 9 * HOUR + i * sc["gap_min"] * MIN + int(rng.integers(0, 600)), 1, "txn",
                       (w, S, float(rng.choice([3500, 4000, 4500])), "SEND_MONEY", store.w[w].last_device)))
        if sc["reported"]:
            ev.append((T - 3 * HOUR - 20 * MIN, 1, "complaint", (S,)))
        if sc["cashout"]:
            ev.append((T - 2 * HOUR, 2, "cashout", (S, agent, 0.8)))
        # collector wallet: fourteen strangers in three hours ("job registration fee"), cash-outs at the agent
        for i, w in enumerate(people[:14]):
            ev.append((T - 3 * HOUR + i * 12 * MIN + int(rng.integers(0, 300)), 1, "txn",
                       (w, C, float(rng.choice([1500, 2000, 2500, 3000, 3500, 5000])), "SEND_MONEY", store.w[w].last_device)))
        ev.append((T - 100 * MIN, 2, "cashout", (C, agent, 0.6)))
        ev.append((T - 22 * MIN, 2, "cashout", (C, agent, 0.7)))
        # takeover of Salma's account: SIM swap, the gang phone logs in, PIN reset
        salma = self.personas.get("salma", {}).get("wallet")
        if salma:
            ev.append((T - 55 * MIN, 0, "event", (salma, "SIM_SWAP", None)))
            ev.append((T - 41 * MIN, 0, "event", (salma, "DEVICE_CHANGE", GANG_PHONE)))
            ev.append((T - 39 * MIN, 0, "event", (salma, "PIN_RESET", None)))
        for t, _o, kind, args in sorted(ev, key=lambda e: (e[0], e[1])):
            if kind == "txn":
                src, dst, amt, typ, dev = args
                self._commit(t, src, dst, amt, typ, dev)
            elif kind == "cashout":
                src, ag, share = args
                amt = float(np.floor(share * st["balances"].get(src, 0.0) / 500) * 500)
                if amt >= 500:
                    self._commit(t, src, ag, amt, "CASH_OUT", COLLECTOR_PHONE)
            elif kind == "complaint":
                store.apply_complaint(args[0])
                self.complained.add(args[0])
            elif kind == "event":
                store.apply_event(t, *args)
        self.staged_agent = agent
        # a real slip: someone else's wallet uses Rahim's mother's number with the last two digits swapped
        rahim = self.personas.get("rahim")
        self.typo_number = None
        if rahim and rahim["contacts"]:
            maa = rahim["contacts"][0]["msisdn"]
            i = next((k for k in range(len(maa) - 1, 3, -1) if maa[k] != maa[k - 1]), None)
            if i is not None:
                near = maa[:i - 1] + maa[i] + maa[i - 1] + maa[i + 1:]
                taken = set(people) | reserved
                strangers = [w for w in pool if w not in taken]
                stranger = strangers[int(np.random.default_rng(11).integers(len(strangers)))]
                st["msisdn"][near] = stranger
                self.typo_number = near

    def _scenarios(self):
        r, s = self.personas.get("rahim"), self.personas.get("salma")
        if r:
            maa = r["contacts"][0]
            r["scenarios"] = [
                dict(key="normal", bn="মা-কে ৳৮০০ পাঠানো (স্বাভাবিক)", en="Tk 800 to Mother (usual)", to=maa["msisdn"], name=maa["name"],
                     name_en=maa["name_en"], amount=800),
            ] + ([dict(key="typo", bn="মা-কে ৳৮০০, কিন্তু শেষের দুই ডিজিট উল্টে গেছে (ভুল নম্বর)", en="Tk 800 to Mother, last two digits swapped (wrong number)", to=self.typo_number,
                       name="মা?", name_en="Mother?", amount=800)] if getattr(self, "typo_number", None) else []) + [
                dict(key="collector", bn="নতুন নম্বরে ৳১৫,০০০ (চাকরির জামানত)", en="Tk 15,000 to a new number (job deposit)", to="01090000001", name="চাকরির এজেন্সি", name_en="Job agency", amount=15000),
                dict(key="seller", bn="অনলাইন বিক্রেতাকে ৳৪,৫০০ অগ্রিম", en="Tk 4,500 advance to an online seller", to="01090000020", name="ফোন বিক্রেতা (ফেসবুক পেজ)", name_en="Phone seller (Facebook page)", amount=4500),
            ]
            warn = self._find_warning_example(r, 6000.0)
            if warn:
                r["scenarios"].insert(1, dict(key="warn", bn="পরিচিতের দেওয়া নতুন নম্বরে ৳৬,০০০ ধার", en="Tk 6,000 loan to a new number from a friend", to=warn,
                                              name="নতুন নম্বর", name_en="New number", amount=6000))
        if s:
            sc = s["contacts"][0]
            cap = float(self.world["limits"]["KYC2"]["send_money"]["per_txn"]) if "per_txn" in self.world["limits"]["KYC2"]["send_money"] else 25000.0
            amt = float(min(np.floor(0.9 * self.engine.state["balances"].get(s["wallet"], 0) / 100) * 100, cap))
            s["scenarios"] = [
                dict(key="normal", bn=f"{sc['name']}-কে ৳১,০০০ (স্বাভাবিক)", en=f"Tk 1,000 to {sc['name_en']} (usual)", to=sc["msisdn"], name=sc["name"], name_en=sc["name_en"], amount=1000),
                dict(key="takeover", bn="নতুন ফোন থেকে বড় অঙ্ক পাঠানো (টেকওভার টেস্ট)", en="Large transfer from a new phone (takeover test)", to="01090000011", name="অপরিচিত নম্বর", name_en="Unknown number",
                     amount=amt, device=GANG_PHONE),
            ]

    def _find_warning_example(self, p: dict, amount: float) -> str | None:
        """An ordinary, established wallet the model puts in NUDGE or STEP_UP for this sender: the soft-warning
        demo is found by the model, not invented. Deterministic (fixed seed, sorted candidates)."""
        store, msisdn = self.engine.store, {w: m for m, w in self.engine.state["msisdn"].items()}
        reserved = {c["wallet"] for c in p["contacts"]} | set(STAGED.values()) | {p["wallet"]}
        cands = sorted(w for w, s in store.w.items() if str(w).startswith("W") and s.n_txn > 30 and s.complaints == 0
                       and w not in reserved and w in msisdn)
        rng = np.random.default_rng(3)
        for w in rng.choice(cands, min(250, len(cands)), replace=False):
            r = self.engine.score(dict(sender_id=p["wallet"], receiver_id=str(w), amount=amount, ts_sec=LIVE_START), commit=False)
            if r["band"] in ("NUDGE", "STEP_UP") and r["risk_score"] < 75:
                return msisdn[str(w)]
        return None

    def _rebuild_graph(self, t: int):
        """The same 24-hour snapshot the model was trained with, rebuilt from recent + staged edges.
        Without networkx (the in-browser build) the 09:30 snapshot is kept: training also rebuilt it only hourly."""
        if nx is None:
            return
        rows = [e[:5] for e in self.edges if t - DAY <= e[0] < t]
        if not rows:
            return
        df = pd.DataFrame(rows, columns=["ts", "sender_id", "receiver_id", "amount", "txn_type"])
        df["status"] = "SUCCESS"
        df["sender_type"] = df.sender_id.map(kind_of)
        df["receiver_type"] = df.receiver_id.map(kind_of)
        comp = pd.DataFrame({"reported_wallet_id": sorted(self.complained)})
        self.engine.state["graph"] = graph_snapshot(df, df.ts.to_numpy(), comp, self.start)

    # ------------------------------------------------------------------ audit
    def _audit(self, actor, role, action, alert_id=None, detail=None):
        prev = self.audit[-1]["hash"] if self.audit else "0" * 64
        e = dict(seq=len(self.audit) + 1, at=self.iso(self.clock() if hasattr(self, "t0") else LIVE_START),
                 actor=actor, role=role, action=action, alert_id=alert_id, detail=detail or {}, prev=prev)
        e["hash"] = hashlib.sha256(json.dumps(e, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()
        self.audit.append(e)
        return e

    def verify_audit(self) -> dict:
        prev = "0" * 64
        for e in self.audit:
            body = {k: v for k, v in e.items() if k != "hash"}
            ok = e["prev"] == prev and e["hash"] == hashlib.sha256(
                json.dumps(body, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()
            if not ok:
                return dict(ok=False, broken_at=e["seq"], entries=len(self.audit))
            prev = e["hash"]
        return dict(ok=True, entries=len(self.audit), head=prev)

    # ------------------------------------------------------------------ customer side
    def resolve(self, x: str) -> str | None:
        w = self.engine.resolve_wallet(str(x).strip())
        known = w in self.engine.store.w or w in self.engine.store.signup or w in self.engine.store.onboard
        return w if known else None

    def score(self, persona: str, to: str, amount: float, device: str | None = None) -> dict:
        p = self.personas.get(persona)
        if p is None:
            raise KeyError(f"unknown customer {persona}")
        return self.score_raw(p["wallet"], to, amount, device or p["device"], persona)

    def score_raw(self, sender: str, to: str, amount: float, device: str | None = None, persona: str | None = None,
                  channel: str = "APP") -> dict:
        """The stable risk-score contract: any sender, any recipient (wallet id or 010 number), scored live."""
        with self.lock:
            res, slip, hb, txn, src, dst, t = self._assess(sender, to, amount, device, persona, channel)
            alert_id = txn_id = None
            if res["band"] == "ALLOW":
                txn_id = self._commit_live(txn)
            else:
                alert_id = self._new_alert(persona, txn, res, slip, hb)
            return self._answer(res, slip, hb, src, dst, t, alert_id, txn_id)

    def preview(self, persona: str, to: str, amount: float, device: str | None = None) -> dict:
        """What Prohori would answer for this transfer right now, without sending it or raising an alert."""
        p = self.personas.get(persona)
        if p is None:
            raise KeyError(f"unknown customer {persona}")
        with self.lock:
            res, slip, hb, _txn, src, dst, t = self._assess(p["wallet"], to, amount, device or p["device"], persona, "APP")
            return self._answer(res, slip, hb, src, dst, t, None, None)

    def _assess(self, sender, to, amount, device, persona, channel):
        """Model score, then the plain rules: keypad slip, amount habit, an analyst's flag. Changes nothing."""
        src = self.resolve(sender)
        if src is None:
            raise LookupError("unknown sender wallet")
        dst = self.resolve(to)
        if dst is None:
            raise LookupError("no upay wallet uses this number in the demo data")
        if dst == src:
            raise ValueError("cannot send money to yourself")
        ws = self.engine.store.w.get(src)
        t = max(self.clock(), self.engine.now + 1)
        txn = dict(sender_id=src, receiver_id=dst, amount=float(amount), txn_type="SEND_MONEY",
                   device_id=device or (ws.last_device if ws else None), channel=channel, ts_sec=t)
        res = self.engine.score(txn, commit=False)
        model_flagged = res["band"] != "ALLOW"
        typed = to.strip() if re.fullmatch(r"01\d{9}", to.strip()) else self.msisdn_of.get(dst)
        sent_to = ws.sent_to if ws else {}
        slip = rcheck.check(sent_to, self.msisdn_of, typed, self.costs) if dst not in sent_to else None
        if slip:
            slip["name"] = self._contact_name(persona, slip["msisdn"])
            slip["name_en"] = self._contact_name(persona, slip["msisdn"], "en")
            slip["typed"] = typed
            who = f"{slip['name']} " if slip["name"] else ""
            who_en = f"{slip['name_en']} " if slip["name_en"] else ""
            res["reasons"] = [dict(
                code="wrong_recipient", feature="recipient_check", shap=None,
                en=f"Did you mean {who_en}({slip['msisdn']})? You have sent money there {slip['count']} times; "
                   f"{slip['slip']['en']}",
                bn=f"আপনি কি {who}({slip['msisdn']}) নম্বরে পাঠাতে চেয়েছিলেন? সেখানে আপনি আগে {bn_num(slip['count'])} বার "
                   f"টাকা পাঠিয়েছেন; {slip['slip']['bn']}")] + res["reasons"]
            if res["band"] == "ALLOW":                    # plain rule: a likely slip always gets a one-tap check
                res["band"], res["policy_override"] = "NUDGE", "possible_wrong_recipient"
            if res["band"] == "NUDGE":
                res["customer_message"] = dict(en=f"Check the number: {res['reasons'][0]['en']}.",
                                               bn=f"নম্বরটি দেখে নিন: {res['reasons'][0]['bn']}।")
        hb = self.habits.check(src, "send", amount, t)
        if hb and hb["unusual"]:                          # plain rule: far above the customer's own habit -> one-tap check
            why = self.habits.reason(hb)
            k = (1 if slip else 0) + (1 if model_flagged else 0)      # the model's own top reason stays first
            res["reasons"] = res["reasons"][:k] + [why] + res["reasons"][k:]
            if res["band"] == "ALLOW":
                res["band"], res["policy_override"] = "NUDGE", "unusual_amount"
                res["customer_message"] = dict(en=f"Check the amount: {why['en']}.", bn=f"পরিমাণটি দেখে নিন: {why['bn']}।")
        txn["typed"] = typed
        if dst in self.flagged:                           # an analyst's flag outranks the model: the strongest warning
            res["band"], res["policy_override"] = "HOLD", "recipient_flagged_by_analyst"
            res["customer_message"] = dict(
                en="upay has flagged this number as suspicious. Sending is your decision; if someone is rushing you, "
                   "cancel and call 16268.",
                bn="upay এই নম্বরটিকে সন্দেহজনক হিসেবে চিহ্নিত করেছে। পাঠাবেন কি না, সিদ্ধান্ত আপনার; কেউ তাড়া দিলে বাতিল করুন "
                   "এবং ১৬২৬৮ নম্বরে কল করুন।")
        return res, slip, hb, txn, src, dst, t

    def _answer(self, res, slip, hb, src, dst, t, alert_id, txn_id) -> dict:
        choices = list(CHOICES.get(res["band"], ())) + (["use_suggested"] if slip else [])
        ask = res["band"] != "ALLOW"
        amount_q = bool(hb and hb["unusual"]) and not slip and res.get("policy_override") == "unusual_amount"
        question = (("আপনি কি ঠিক নম্বরে পাঠাচ্ছেন?" if slip else "পরিমাণটি কি ঠিক আছে?" if amount_q
                     else "আপনি কি এই ব্যক্তিকে ব্যক্তিগতভাবে চেনেন?") if ask else None)
        question_en = (("Is this the right number?" if slip else "Is this amount right?" if amount_q
                        else "Do you personally know this person?") if ask else None)
        return dict(
            band=res["band"], risk_score=res["risk_score"], alert_id=alert_id, txn_id=txn_id, receiver_id=dst,
            reasons=[dict(code=r["code"], bn=r["bn"], en=r["en"]) for r in res["reasons"]],
            message=res["customer_message"], choices=choices, suggestion=slip, habit=hb,
            policy_override=res.get("policy_override"), at=self.iso(t),
            balance=round(float(self.engine.state["balances"].get(src, 0.0)), 2), question_bn=question,
            question_en=question_en,
        )

    def _contact_name(self, persona: str | None, msisdn: str, lang: str = "bn") -> str | None:
        p = self.personas.get(persona) if persona else None
        key = "name_en" if lang == "en" else "name"
        return next((c[key] for c in (p or {}).get("contacts", []) if c["msisdn"] == msisdn), None)

    def recipient_lookup(self, persona: str, to: str) -> dict:
        """As the customer types: does a wallet use this number, and is it one slip from someone they pay often?"""
        p = self.personas.get(persona)
        if p is None:
            raise KeyError(f"unknown customer {persona}")
        number = re.sub(r"\D", "", cmp.to_ascii_digits(str(to)))
        dst = self.resolve(number)
        ws = self.engine.store.w.get(p["wallet"])
        sent_to = ws.sent_to if ws else {}
        slip = rcheck.check(sent_to, self.msisdn_of, number, self.costs) if dst not in sent_to else None
        if slip:
            slip["name"] = self._contact_name(persona, slip["msisdn"])
            slip["name_en"] = self._contact_name(persona, slip["msisdn"], "en")
        return dict(number=number, exists=dst is not None, known_contact=self._contact_name(persona, number),
                    known_contact_en=self._contact_name(persona, number, "en"), suggestion=slip,
                    slip_costs=self.costs.get("source"))

    def transfers(self, persona: str, days: int = 7) -> list[dict]:
        """The customer's own recent transfers, newest first, for 'which transfer is this about?'."""
        p = self.personas.get(persona)
        if p is None:
            raise KeyError(f"unknown customer {persona}")
        now = self.clock()
        out = []
        for e in self.edges:
            if e[1] != p["wallet"] or e[4] != "SEND_MONEY" or e[0] < now - days * DAY:
                continue
            number = self.typed.get(e[5]) or self.msisdn_of.get(e[2], "")
            out.append(dict(id=e[5], ts=int(e[0]), at=self.iso(e[0]), to=e[2], amount=e[3], number=number,
                            name=self._contact_name(persona, number), name_en=self._contact_name(persona, number, "en")))
        return sorted(out, key=lambda t: -t["ts"])[:12]

    def _commit_live(self, txn: dict) -> str:
        t = max(self.clock(), self.engine.now + 1)
        self.n_tx += 1
        tid = self._commit(t, txn["sender_id"], txn["receiver_id"], txn["amount"], txn["txn_type"], txn.get("device_id"),
                           txn_id=f"TL-{self.n_tx:04d}")
        if txn.get("typed"):
            self.typed[tid] = txn["typed"]
        self._rebuild_graph(t + 1)
        return tid

    def balance(self, persona: str) -> float:
        p = self.personas[persona]
        return round(float(self.engine.state["balances"].get(p["wallet"], 0.0)), 2)

    def _new_alert(self, persona: str, txn: dict, res: dict, slip: dict | None = None, hb: dict | None = None) -> str:
        self.n_live += 1
        aid = f"L-{self.n_live:04d}"
        feats = self.engine.bundle["features"]
        ev = {k: _clean(v) for k, v in res["evidence"].items()}
        shap = self.engine.last_shap if hasattr(self.engine, "last_shap") else None
        self.alerts[aid] = dict(
            id=aid, source="live", persona=persona, txn_id=aid, ts_sec=txn["ts_sec"], created=self.iso(txn["ts_sec"]),
            sender_id=txn["sender_id"], receiver_id=txn["receiver_id"], txn_type=txn["txn_type"], amount=txn["amount"],
            device_id=txn.get("device_id"), risk_score=res["risk_score"], band=res["band"],
            policy_override=res.get("policy_override"), p_fraud=res["p_fraud"], p_fraud_calibrated=res["p_fraud_calibrated"],
            anomaly=res["anomaly"], graph=res["graph"], reasons=res["reasons"], customer_message=res["customer_message"],
            shap=[dict(feature=f, value=ev.get(f), shap=round(float(v), 4))
                  for f, v in sorted(zip(feats, shap), key=lambda kv: -abs(kv[1]))[:10]] if shap is not None else [],
            evidence=ev, status="awaiting_customer",      # every warning is the customer's to answer, HOLD included
            customer_choice=None, title=None, planted_id=None, truth=None, suggestion=slip, typed=txn.get("typed"),
            kind="presend", habit=hb,
        )
        self.order.insert(0, aid)
        self._audit("prohori-model", "system", f"alert.{res['band'].lower()}", aid,
                    {"risk_score": res["risk_score"], "reasons": [r["code"] for r in res["reasons"]],
                     "policy_override": res.get("policy_override")})
        return aid

    def decide(self, alert_id: str, choice: str, pin: str | None = None) -> dict:
        with self.lock:
            a = self.alerts.get(alert_id)
            if a is None or a["source"] != "live":
                raise KeyError(alert_id)
            if a["customer_choice"] is not None:
                raise ValueError("the customer has already answered this warning")
            if choice == "use_suggested":
                if not a.get("suggestion"):
                    raise ValueError("there is no suggested number for this warning")
                a["customer_choice"], a["status"] = "used_suggested", "changed_to_suggested"
                self._audit("customer", "customer", "customer.used_suggested", alert_id, {"to": a["suggestion"]["msisdn"]})
                return dict(alert_id=alert_id, status=a["status"], suggestion=a["suggestion"],
                            balance=round(float(self.engine.state["balances"].get(a["sender_id"], 0.0)), 2))
            if choice not in CHOICES.get(a["band"], ()):
                raise ValueError(f"'{choice}' is not offered for a {a['band']} warning")
            if choice == "confirm_pin" and not (pin and len(pin) == 4 and pin.isdigit()):
                raise ValueError("enter the 4-digit PIN to confirm")
            a["customer_choice"] = "cancelled" if choice == "cancel" else ("confirmed_pin" if choice == "confirm_pin" else "confirmed")
            if choice == "cancel":
                a["status"] = "cancelled_by_customer"
            elif a.get("kind") == "recharge":
                a["txn_id"] = self._commit_recharge(a["sender_id"], a["recharge"]["number"], a["amount"], a.get("device_id"))
                a["status"] = "sent_after_warning"
            else:
                a["txn_id"] = self._commit_live(dict(sender_id=a["sender_id"], receiver_id=a["receiver_id"], amount=a["amount"],
                                                     txn_type=a["txn_type"], device_id=a.get("device_id"), typed=a.get("typed")))
                a["status"] = "sent_after_warning"
            self._audit("customer", "customer", f"customer.{a['customer_choice']}", alert_id)
            return dict(alert_id=alert_id, status=a["status"],
                        balance=round(float(self.engine.state["balances"].get(a["sender_id"], 0.0)), 2))

    def transfer_status(self, alert_id: str) -> dict:
        """What the customer's phone may know about a warned transfer: its state, never the case file."""
        a = self.alerts.get(alert_id)
        if a is None or a["source"] != "live":
            raise KeyError(alert_id)
        msg = {
            "awaiting_customer": ("আপনার সিদ্ধান্তের অপেক্ষায়। টাকা আপনার ওয়ালেটেই আছে।", "Waiting for your choice. The money is still in your wallet."),
            "cancelled_by_customer": ("আপনি লেনদেনটি বাতিল করেছেন। টাকা আপনার ওয়ালেটে আছে।", "You cancelled. The money is in your wallet."),
            "sent_after_warning": ("সতর্কবার্তা দেখার পর আপনি টাকা পাঠিয়েছেন।", "You sent the money after the warning."),
            "dismissed": ("upay এই সতর্কবার্তাটিকে ভুল সতর্কতা হিসেবে চিহ্নিত করেছে।", "upay marked this warning as a false alarm."),
        }.get(a["status"], ("", ""))
        return dict(alert_id=alert_id, status=a["status"], band=a["band"], message_bn=msg[0], message_en=msg[1],
                    balance=round(float(self.engine.state["balances"].get(a["sender_id"], 0.0)), 2))

    # ------------------------------------------------------------------ mobile recharge: amount habit + rapid-recharge rule
    def recharge(self, persona: str, number: str, amount: float) -> dict:
        """A mobile recharge from the customer's wallet. The fraud model is not trained on recharges, so the check is
        the customer's own recharge habit (thresholds learned with federated analytics) and one plain rule: a third
        recharge within an hour to two or more numbers that are not the customer's own. Either one asks once (NUDGE)."""
        with self.lock:
            p = self.personas.get(persona)
            if p is None:
                raise KeyError(f"unknown customer {persona}")
            number = re.sub(r"\D", "", cmp.to_ascii_digits(str(number or "")))
            if not re.fullmatch(r"01\d{9}", number):
                raise ValueError("enter an 11-digit mobile number starting with 01")
            amount = float(amount)
            if not RECHARGE["min"] <= amount <= RECHARGE["max"]:
                raise ValueError(f"a recharge is Tk {RECHARGE['min']:.0f} to Tk {RECHARGE['max']:,.0f} (synthetic limit)")
            src = p["wallet"]
            if amount > self.engine.state["balances"].get(src, 0.0):
                raise ValueError("not enough balance")
            t = max(self.clock(), self.engine.now + 1)
            own = number == p["msisdn"]
            contact = self._contact_name(persona, number)
            hb = self.habits.check(src, "recharge", amount, t)
            unusual = bool(hb and hb["unusual"])
            reasons = [self.habits.reason(hb)] if unusual else []
            recent = [r for r in self.recharges if r["wallet"] == src and t - r["t"] <= RECHARGE["burst_window"]]
            others = {r["number"] for r in recent if not r["own"]} | (set() if own else {number})
            burst = len(recent) + 1 >= RECHARGE["burst_count"] and len(others) >= 2
            if burst:
                reasons.append(dict(code="recharge_burst",
                                    en=f"Recharge number {len(recent) + 1} in the last hour, to {len(others)} numbers that are not "
                                       "yours: scammers ask victims to recharge the scammers' own numbers",
                                    bn=f"গত এক ঘণ্টায় {bn_num(len(recent) + 1)}তম রিচার্জ, আপনার নয় এমন {bn_num(len(others))}টি নম্বরে: "
                                       "প্রতারকেরা ভুক্তভোগীদের দিয়ে নিজেদের নম্বরে রিচার্জ করিয়ে নেয়"))
            if not own and not contact:
                reasons.append(dict(code="recharge_stranger", en="This number is not yours and not in your saved contacts",
                                    bn="নম্বরটি আপনার নয়, আপনার পরিচিত তালিকাতেও নেই"))
            band = "NUDGE" if unusual or burst else "ALLOW"
            alert_id = txn_id = None
            if band == "ALLOW":
                txn_id = self._commit_recharge(src, number, amount, p["device"], t)
            else:
                self.n_live += 1
                alert_id = f"L-{self.n_live:04d}"
                self.alerts[alert_id] = dict(
                    id=alert_id, source="live", persona=persona, kind="recharge", txn_id=alert_id, ts_sec=t, created=self.iso(t),
                    sender_id=src, receiver_id=number, txn_type="MOBILE_RECHARGE", amount=amount, device_id=p["device"],
                    risk_score=0.0, band="NUDGE", policy_override="unusual_amount" if unusual else "recharge_burst",
                    p_fraud=0.0, p_fraud_calibrated=0.0, anomaly=None, graph=0.0, reasons=reasons, customer_message=None,
                    shap=[], evidence={}, status="awaiting_customer", customer_choice=None,
                    title="Unusual recharge amount for this customer" if unusual else "Rapid recharges to other numbers",
                    planted_id=None, truth=None, suggestion=None, typed=number, habit=hb,
                    recharge=dict(number=number, own=own, contact=contact, burst=burst,
                                  recent=[dict(r, at=self.iso(r["t"])) for r in recent]))
                self.order.insert(0, alert_id)
                self._audit("prohori-rules", "system", "alert.recharge", alert_id,
                            {"reasons": [r["code"] for r in reasons], "amount": amount})
            msg = None
            if band == "NUDGE":
                msg = dict(en="Check before you recharge: " + reasons[0]["en"] + ".", bn="রিচার্জের আগে দেখে নিন: " + reasons[0]["bn"] + "।")
            return dict(band=band, alert_id=alert_id, txn_id=txn_id, number=number, own=own, contact=contact,
                        contact_en=self._contact_name(persona, number, "en"), amount=amount,
                        reasons=[dict(code=r["code"], bn=r["bn"], en=r["en"]) for r in reasons], habit=hb, message=msg,
                        choices=list(CHOICES["NUDGE"]) if band == "NUDGE" else [], at=self.iso(t),
                        question_bn="রিচার্জটি কি আপনি নিজে, জেনে-বুঝে করছেন?" if band == "NUDGE" else None,
                        question_en="Are you making this recharge yourself, knowingly?" if band == "NUDGE" else None,
                        balance=round(float(self.engine.state["balances"].get(src, 0.0)), 2))

    def _commit_recharge(self, src: str, number: str, amount: float, device: str | None, t: int | None = None) -> str:
        """The recharge enters the same feature store (as MOBILE_RECHARGE, like the training replay) and the habit."""
        t = max(t or self.clock(), self.engine.now + 1)
        store, bal, dst = self.engine.store, self.engine.state["balances"], RECHARGE["biller"]
        dow = int((self.start + pd.Timedelta(seconds=t)).dayofweek)
        _f, depth = store.compute(t, "MOBILE_RECHARGE", src, "C", dst, "B", amount, bal.get(src, np.nan), bal.get(dst, np.nan),
                                  device, "APP", None, dow)
        store.update(t, "MOBILE_RECHARGE", src, "C", dst, "B", amount, True, device, "APP", None, depth)
        bal[src] = bal.get(src, 0.0) - amount
        bal[dst] = bal.get(dst, 0.0) + amount
        self.engine.now = max(self.engine.now, t)
        self.habits.add(src, "recharge", amount, t)
        own = any(p["wallet"] == src and p["msisdn"] == number for p in self.personas.values())
        self.recharges.append(dict(wallet=src, number=number, amount=float(amount), t=int(t), own=own))
        self.n_tx += 1
        return f"TR-{self.n_tx:04d}"

    def recharges_of(self, persona: str) -> list[dict]:
        p = self.personas.get(persona)
        if p is None:
            raise KeyError(f"unknown customer {persona}")
        return [dict(r, at=self.iso(r["t"])) for r in reversed(self.recharges) if r["wallet"] == p["wallet"]]

    # ------------------------------------------------------------------ complaints: "I sent it to the wrong person"
    def preview_complaint(self, text: str) -> dict:
        """What the rules read from the customer's words, shown back before they submit (no model, no LLM)."""
        return cmp.extract(text or "")

    def file_complaint(self, persona: str, text: str, problem: str = "wrong_number", transfer_id: str | None = None,
                       consent: bool = False) -> dict:
        with self.lock:
            p = self.personas.get(persona)
            if p is None:
                raise KeyError(f"unknown customer {persona}")
            if not consent:
                raise ValueError("the customer must read and accept the notice first (purpose, retention, who sees it)")
            text = (text or "").strip()
            if not 3 <= len(text) <= 2000:
                raise ValueError("describe what happened in 3 to 2000 characters")
            if problem not in ("wrong_number", "scam", "other"):
                raise ValueError("problem must be wrong_number, scam or other")
            now = max(self.clock(), self.engine.now + 1)
            e = cmp.extract(text)
            m = cmp.match_transfer(e, self.transfers(persona), now, transfer_id)
            t = m["transfer"]
            dst = t["to"] if t else None
            amount = float(t["amount"]) if t else float(e["amount"] or 0.0)
            probe = shap = None
            if dst:                                       # the model's view of the receiving wallet now
                probe = self.engine.score(dict(sender_id=p["wallet"], receiver_id=dst, amount=max(amount, 1.0),
                                               txn_type="SEND_MONEY", device_id=p["device"], channel="APP", ts_sec=now),
                                          commit=False)
                shap = self.engine.last_shap
            ws = self.engine.store.w.get(p["wallet"])
            others = {w: c for w, c in (ws.sent_to if ws else {}).items() if w != dst}
            slip = rcheck.check(others, self.msisdn_of, t["number"], self.costs) if t else None
            if slip:
                slip["name"] = self._contact_name(persona, slip["msisdn"])
                slip["name_en"] = self._contact_name(persona, slip["msisdn"], "en")
                slip["typed"] = t["number"]
            codes = {r["code"] for r in (probe or {}).get("reasons", [])}
            scam_words = any(e["cues"].get(k) for k in cmp.SCAM_CUES)
            looks_scam = bool(probe) and (probe["band"] == "HOLD" or bool(codes & SCAM_EVIDENCE))
            if t is None:
                case = "needs_details"
            elif slip and not (probe and probe["band"] == "HOLD"):
                case = "genuine_wrong_send"
            elif problem == "scam" or scam_words or looks_scam:
                case = "likely_scam_victim"
            else:
                case = "needs_review"
            if problem == "scam" and dst:                 # FRAUD reports (not wrong-send disputes) count against a wallet
                self.engine.store.apply_complaint(dst)
                self.complained.add(dst)
            balance = float(self.engine.state["balances"].get(dst, 0.0)) if dst else 0.0
            self.n_complaints += 1
            cid = f"C-{self.n_complaints:04d}"
            feats = self.engine.bundle["features"]
            ev = {k: _clean(v) for k, v in probe["evidence"].items()} if probe else {}
            self.alerts[cid] = dict(
                id=cid, source="live", kind="complaint", persona=persona, txn_id=t["id"] if t else None,
                ts_sec=t["ts"] if t else now, created=self.iso(now), sender_id=p["wallet"], receiver_id=dst or "",
                txn_type="COMPLAINT", amount=amount, device_id=None, band="COMPLAINT",
                risk_score=probe["risk_score"] if probe else 0.0, policy_override=None,
                p_fraud=probe["p_fraud"] if probe else 0.0, p_fraud_calibrated=probe["p_fraud_calibrated"] if probe else 0.0,
                anomaly=probe["anomaly"] if probe else None, graph=probe["graph"] if probe else 0.0,
                reasons=probe["reasons"] if probe else [], customer_message=None,
                shap=[dict(feature=f, value=ev.get(f), shap=round(float(v), 4))
                      for f, v in sorted(zip(feats, shap), key=lambda kv: -abs(kv[1]))[:10]] if shap is not None else [],
                evidence=ev, status="complaint_received", customer_choice=None, title=CASE_LABELS[case],
                planted_id=None, truth=None, suggestion=None, typed=t["number"] if t else None,
                complaint=dict(text=text, problem=problem, language=e["language"], extraction=e, case_type=case,
                               case_label=CASE_LABELS[case], match=dict(how=m["how"], confidence=m["confidence"], transfer=t,
                                                                         candidates=m["candidates"]),
                               slip=slip, recipient_balance=round(balance, 2), holdable=round(min(amount, balance), 2),
                               probe_band=probe["band"] if probe else None, filed_at=self.iso(now),
                               deadline=cmp.sla_deadline(self._date(now)).isoformat(),
                               consent=dict(accepted=True, version="2026-10-02", purpose="dispute resolution and fraud prevention")),
            )
            self.order.insert(0, cid)
            self._audit("customer", "customer", "complaint.filed", cid,
                        {"problem": problem, "case_type": case, "matched": t["id"] if t else None})
            return self.complaint_status(cid)

    def _date(self, t: int) -> date:
        return (self.start + pd.Timedelta(seconds=int(t))).date()

    def complaint_status(self, cid: str) -> dict:
        """The customer's view: what was understood, which transfer, the deadline and the next step (no verdict)."""
        a = self.alerts.get(cid)
        if a is None or a.get("kind") != "complaint":
            raise KeyError(cid)
        c = a["complaint"]
        step = {"complaint_received": 1, "details_requested": 1, "hold_requested": 2, "recipient_contacted": 2,
                "recipient_flagged": 2, "dismissed": 3, "resolved": 3}.get(a["status"], 1)
        e, t = c["extraction"], c["match"]["transfer"]
        deadline_bn = bn_num(pd.Timestamp(c["deadline"]).strftime("%d/%m/%Y"))
        return dict(
            case_id=cid, status=a["status"], step=step, steps_bn=COMPLAINT_STEPS_BN, deadline=c["deadline"],
            understood=dict(amount=e["amount"], number=e["number"] or (f"…{e['number_last4']}" if e["number_last4"] else None),
                            day_offset=e["day_offset"], hour=e["hour"], language=e["language"]),
            transfer=dict(id=t["id"], amount=t["amount"], number=t["number"], at=t["at"]) if t else None,
            message_bn=(f"আপনার অভিযোগ {cid} গ্রহণ করা হয়েছে। {deadline_bn} তারিখের মধ্যে (১০ কর্মদিবস) আপনাকে জানানো হবে। "
                        "সঠিক নম্বরে পাঠানোর দায়িত্ব প্রেরকের; অর্থ ফেরত পাওয়া প্রাপকের সম্মতি বা আইনি প্রক্রিয়ার উপর নির্ভর করে।"),
            message_en=(f"Your complaint {cid} has been received. We will update you by {c['deadline']} (10 working days). "
                        "The sender is responsible for the number entered; a return depends on the recipient's consent or legal process."),
            steps_en=["Received", "Under review", "Action taken", "Resolved"],
            next_en={"details_requested": "We need more details: which transfer, how much, when.",
                     "hold_requested": "A temporary hold of the disputed amount has been requested.",
                     "recipient_contacted": "The recipient has been asked for consent to return the money.",
                     "recipient_flagged": "The recipient's wallet has been flagged: anyone who sends to it is warned first."
                     }.get(a["status"], "An officer is reviewing it."),
            escalation_en="If you are not satisfied, you can complain to Bangladesh Bank's Customers Interest Protection Centre "
                          "(hotline 16236). upay helpline 16268.",
            next_bn={"details_requested": "আরও তথ্য দরকার: কোন লেনদেন, কত টাকা, কখন।",
                     "hold_requested": "বিরোধকৃত পরিমাণ সাময়িকভাবে আটকানোর অনুরোধ করা হয়েছে।",
                     "recipient_contacted": "প্রাপকের সম্মতি চাওয়া হয়েছে।",
                     "recipient_flagged": "প্রাপকের ওয়ালেট চিহ্নিত করা হয়েছে: সেখানে টাকা পাঠাতে গেলে সবাই আগে সতর্কবার্তা পাবেন।"
                     }.get(a["status"], "একজন কর্মকর্তা দেখছেন।"),
            escalation_bn="সন্তুষ্ট না হলে বাংলাদেশ ব্যাংকের কাস্টমার্স ইন্টারেস্ট প্রটেকশন সেন্টারে (হটলাইন ১৬২৩৬) অভিযোগ করতে পারবেন। উপায় হেল্পলাইন ১৬২৬৮।",
        )

    # ------------------------------------------------------------------ analyst side
    def list_alerts(self, include_allowed: bool = False) -> list[dict]:
        keys = ("id", "source", "created", "sender_id", "receiver_id", "txn_type", "amount", "risk_score", "band",
                "status", "customer_choice", "planted_id", "title", "policy_override")
        out = []
        for aid in self.order:
            a = self.alerts[aid]
            if a["band"] == "ALLOW" and not include_allowed:
                continue
            row = {k: a.get(k) for k in keys}
            row["top_reason"] = (a["reasons"][0]["en"] if a.get("reasons") else None)
            row["truth"] = a.get("truth")
            row["kind"] = a.get("kind", "historical" if a["source"] == "historical" else "presend")
            row["wrong_number"] = bool(a.get("suggestion"))
            row["unusual_amount"] = bool((a.get("habit") or {}).get("unusual"))
            row["case_type"] = a["complaint"]["case_type"] if a.get("kind") == "complaint" else None
            if a.get("kind") == "complaint":
                row["top_reason"] = "“" + a["complaint"]["text"][:90] + ("…" if len(a["complaint"]["text"]) > 90 else "") + "”"
            out.append(row)
        return out

    def network(self, a: dict) -> dict:
        if a["source"] == "historical":
            net = a["network"]
            edges = [dict(e) for e in net["edges"]]
        else:
            t, s, r = a["ts_sec"], a["sender_id"], a["receiver_id"]
            w = [e for e in self.edges if t - DAY <= e[0] <= t + 3 * HOUR]
            into = [e for e in w if e[2] == r]
            out_r = [e for e in w if e[1] == r]
            nxt = {e[2] for e in out_r} - {r}
            hop2 = [e for e in w if e[1] in nxt and e[0] >= t - 2 * HOUR]
            by_s = [e for e in w if (e[1] == s or e[2] == s) and t - 2 * HOUR <= e[0] <= t + 2 * HOUR]
            seen, edges = set(), []
            for e in sorted(into + out_r + hop2 + by_s, key=lambda e: -e[3]):
                k = (e[0], e[1], e[2], e[3])
                if k in seen or len(edges) >= 40:
                    continue
                seen.add(k)
                edges.append(dict(id=f"E{len(edges)}", source=e[1], target=e[2], amount=e[3], type=e[4], ts=int(e[0]), key=False))
            if a.get("kind") == "complaint":
                tid = a.get("txn_id")
                hit = next((e for e in self.edges if e[5] == tid), None) if tid else None
                edges = [x for x in edges if not (hit and x["source"] == hit[1] and x["target"] == hit[2] and x["ts"] == int(hit[0]))]
                if hit:
                    edges.append(dict(id=tid, source=hit[1], target=hit[2], amount=hit[3], type="SEND_MONEY", ts=int(hit[0]),
                                      key=True, attempt=True, status="complained"))
            else:
                status = {"cancelled": "cancelled", "confirmed": "sent", "confirmed_pin": "sent",
                          "used_suggested": "cancelled"}.get(a["customer_choice"], "pending")
                edges.append(dict(id=a["id"], source=s, target=r, amount=a["amount"], type=a["txn_type"], ts=int(t), key=True,
                                  attempt=True, status=status))
            net = dict(roles={})
            dev = a.get("device_id")
            ring = self.engine.store.dev_wallets.get(dev, set()) if dev else set()
            if len(ring) >= 3:
                for wlt in sorted(ring):
                    edges.append(dict(id=f"D-{wlt}", source=dev, target=wlt, amount=0, type="DEVICE", ts=int(t), key=False))
        roles = dict(net.get("roles", {}))
        roles.setdefault(a["sender_id"], "sender")
        roles.setdefault(a["receiver_id"], "recipient")
        store = self.engine.store
        nodes = {}
        for e in edges:
            for n in (e["source"], e["target"]):
                if n in nodes:
                    continue
                kind = "device" if str(n).startswith("DV") else {"W": "customer", "A": "agent", "M": "merchant",
                                                                  "B": "biller", "X": "external"}.get(str(n)[:1], "other")
                opened = store.signup.get(n, store.onboard.get(n))
                ref = a["ts_sec"]
                role = roles.get(n)
                if role is None:
                    if e["target"] == a["receiver_id"] and n == e["source"]:
                        role = "payer"
                    elif kind == "agent":
                        role = "agent"
                    elif kind == "device":
                        role = "device"
                    else:
                        role = "other"
                ws = store.w.get(n)
                nodes[n] = dict(id=n, kind=kind, role=role, flagged=n in self.flagged,
                                age_days=None if opened is None else round((ref - opened) / DAY, 1),
                                reported=n in self.complained or bool(ws and ws.complaints))
        return dict(nodes=list(nodes.values()), edges=edges)

    def _context(self, a) -> dict:
        fr = (self.engine.state.get("metrics") or {}).get("friction") or {}
        allow = (fr.get("legit_txn_share_by_band") or {}).get("ALLOW")
        return dict(when=self.when(a["ts_sec"]), honest_warning_rate_pct=None if allow is None else round(100 * (1 - allow), 2))

    def alert_detail(self, alert_id: str, use_llm: bool = False) -> dict:
        with self.lock:
            a = self.alerts.get(alert_id)
            if a is None:
                raise KeyError(alert_id)
            if a.get("kind") == "complaint" and not a["receiver_id"]:
                net = dict(nodes=[dict(id=a["sender_id"], kind="customer", role="claimant", flagged=False, age_days=None,
                                       reported=False)], edges=[])
            elif a.get("kind") == "recharge":
                net = dict(nodes=[], edges=[])
            else:
                net = self.network(a)
            if a.get("kind") == "complaint":
                rep = copilot.complaint_report(a, net, self._context(a))
            elif a.get("kind") == "recharge":
                rep = copilot.recharge_report(a, self._context(a))
            else:
                rep = copilot.case_report(a, net, self._context(a), use_llm=use_llm)
            out = {k: v for k, v in a.items() if k not in ("network",)}
            out["shap"] = [dict(s, label=FEATURE_LABELS.get(s["feature"], s["feature"])) for s in a.get("shap", [])]
            out["network"] = net
            out["report"] = rep
            out["audit"] = [e for e in self.audit if e.get("alert_id") == alert_id]
            out["flagged_recipient"] = a["receiver_id"] in self.flagged
            return out

    def act(self, alert_id: str, action: str, analyst: str, note: str = "") -> dict:
        with self.lock:
            a = self.alerts.get(alert_id)
            if a is None:
                raise KeyError(alert_id)
            if action not in copilot.ACTIONS:
                raise ValueError(f"unknown action {action}")
            analyst = (analyst or "").strip()
            if not analyst:
                raise PermissionError("an analyst name is required: every action is logged with a name")
            if action == "DISMISS" and len(note.strip()) < 3:
                raise ValueError("say why the alert is a false alarm")
            if action == "FLAG_RECIPIENT":                # later senders get the strongest warning; nothing is blocked
                if not a["receiver_id"]:
                    raise ValueError("no matched transfer: there is no receiving wallet to flag")
                self.flagged[a["receiver_id"]] = alert_id
                if a.get("kind") == "complaint":          # a warned transfer keeps the customer's own choice as its status
                    a["status"] = "recipient_flagged"
            elif action == "DISMISS":
                a["status"] = "dismissed"
            elif action in ("HOLD_DISPUTED_AMOUNT", "ASK_RECIPIENT_CONSENT", "ASK_CUSTOMER_DETAILS"):
                if a.get("kind") != "complaint":
                    raise ValueError("this action is for wrong-send complaints")
                if action == "HOLD_DISPUTED_AMOUNT":
                    if not a["receiver_id"]:
                        raise ValueError("no matched transfer: ask the customer for details first")
                    bal = float(self.engine.state["balances"].get(a["receiver_id"], 0.0))
                    a["hold_amount"] = round(min(a["amount"], bal), 2)       # never more than disputed or available
                    note = (note + " " if note else "") + f"[hold requested: Tk {a['hold_amount']:,.0f}]"
                a["status"] = {"HOLD_DISPUTED_AMOUNT": "hold_requested", "ASK_RECIPIENT_CONSENT": "recipient_contacted",
                               "ASK_CUSTOMER_DETAILS": "details_requested"}[action]
            a.setdefault("actions", []).append(dict(action=action, analyst=analyst, note=note, at=self.iso(self.clock())))
            self._audit(analyst, "analyst", f"analyst.{action.lower()}", alert_id, {"note": note})
            return dict(alert_id=alert_id, status=a["status"], flagged=sorted(self.flagged))

    # ------------------------------------------------------------------ panels
    def agent_watch(self) -> dict:
        ag = self.world["agents"]
        st = self.engine.state.get("agent_watch") or {}
        return dict(series=ag["series"], area=ag["area"], sc06=ag.get("sc06"), register_compromise=ag.get("register_compromise"),
                    threshold=ag.get("threshold"), by_split=ag.get("by_split"), top_last_day=st.get("top_agents_last_day"),
                    staged_agent=self.staged_agent)

    def model_card(self) -> dict:
        m = self.engine.state.get("metrics") or {}
        return dict(comparison=m.get("comparison"), bands=m.get("bands"), impact=m.get("impact"), friction=m.get("friction"),
                    fairness=self.world.get("fairness"), shap_top=self.world.get("shap_top"),
                    per_scenario=self.world.get("per_scenario"), demo=self.engine.state.get("demo"),
                    federated=self.federated())

    def federated(self) -> dict:
        """Results of the two federated-learning runs (src/fl), packaged next to the models by src.fl.summary."""
        for f in (self.dir / "federated.json", self.dir / "portable" / "federated.json"):
            if f.exists():
                return json.loads(f.read_text(encoding="utf-8"))
        return {}

    def customers(self) -> dict:
        return dict(clock=self.iso(self.clock()), limits=self.world["limits"],
                    customers=[dict(key=p["key"], name_bn=p["name_bn"], name_en=p["name_en"], role_bn=p["role_bn"],
                                    role_en=p.get("role_en", ""), msisdn=p["msisdn"], kyc=p["kyc"], balance=self.balance(k),
                                    typical_amount=p["typical_amount"],
                                    contacts=[dict(name=c["name"], name_en=c.get("name_en", c["name"]), msisdn=c["msisdn"],
                                                   sent_before=c["sent_before"]) for c in p["contacts"]],
                                    scenarios=p["scenarios"], habits=self.habits.summary(p["wallet"], self.clock()))
                               for k, p in self.personas.items()],
                    slip_costs=self.costs.get("source"), amount_habits=self.habits.source if self.habits.ok else None,
                    recharge_limits=dict(min=RECHARGE["min"], max=RECHARGE["max"]), test_kit=bool(self.kit))

    def test_kit(self) -> dict:
        """Numbers from the dataset to try on the phone, each with what Prohori said on a fresh demo (src/serve/testkit.py)."""
        if not self.kit:
            raise LookupError("no test kit packaged (python -m src.serve.testkit)")
        return self.kit
