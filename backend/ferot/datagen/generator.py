"""Synthetic MFS ledger with planted dispute cases and known ground truth (rule R16).

The same seed always produces the same world. Nothing here is real: every phone number uses the
010 prefix, which is outside Bangladesh's active mobile prefixes, and every person is invented.

Output tables
  wallets        one row per wallet (customers, agents, merchants, mules, fraudsters, ...)
  transactions   the ledger, with sender and receiver balances after each transaction
  system_events  debit/credit failures for technical-failure cases
  cases          one row per dispute: true type, claimant, disputed transaction, complaint time
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from ferot import config
from ferot.datagen.typos import apply_typo

DISTRICTS = ["Dhaka", "Chattogram", "Rajshahi", "Khulna", "Sylhet", "Barishal", "Rangpur",
             "Mymensingh", "Gazipur", "Narayanganj", "Cumilla", "Bogura"]
AGE_BANDS = ["18-24", "25-34", "35-44", "45-54", "55+"]
HOUR_WEIGHTS = np.array([1, 1, 1, 1, 1, 2, 4, 6, 8, 9, 10, 10, 10, 10, 10, 10, 10, 10, 10, 9, 8, 6, 4, 2], float)
HOUR_WEIGHTS /= HOUR_WEIGHTS.sum()
UNLIMITED_TYPES = {"agent", "merchant", "employer", "remit_hub", "mno", "system"}
SYSTEM_WALLET = "01000000000"  # upay settlement account used for automatic reversals
TX_COLUMNS = ["minute", "seq", "type", "sender", "receiver", "amount", "channel", "status",
              "source_wallet", "protected", "tag"]

# Golden-path wallets used in the demo (fixed so the demo is repeatable).
RAHIM, RAHIM_BROTHER, RAHIM_WRONG = "01055501234", "01012345678", "01012345687"
SHIRIN, SHIRIN_MULE = "01077700111", "01099988877"


@dataclass
class World:
    wallets: pd.DataFrame
    transactions: pd.DataFrame
    system_events: pd.DataFrame
    cases: pd.DataFrame
    start: pd.Timestamp
    days: int

    def save(self, directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        self.wallets.to_parquet(directory / "wallets.parquet", index=False)
        self.transactions.to_parquet(directory / "transactions.parquet", index=False)
        self.system_events.to_parquet(directory / "system_events.parquet", index=False)
        self.cases.to_parquet(directory / "cases.parquet", index=False)
        (directory / "meta.txt").write_text(f"{self.start.isoformat()}\n{self.days}\n", encoding="utf-8")

    @classmethod
    def load(cls, directory: Path) -> "World":
        start, days = (directory / "meta.txt").read_text(encoding="utf-8").split()
        return cls(
            wallets=pd.read_parquet(directory / "wallets.parquet"),
            transactions=pd.read_parquet(directory / "transactions.parquet"),
            system_events=pd.read_parquet(directory / "system_events.parquet"),
            cases=pd.read_parquet(directory / "cases.parquet"),
            start=pd.Timestamp(start),
            days=int(days),
        )


class _Builder:
    def __init__(self, seed: int, n_customers: int, days: int):
        self.rng = np.random.default_rng(seed)
        self.a = config.assumptions()
        self.lim = config.limits()
        self.start = pd.Timestamp(self.a["generator"]["start_date"])
        self.days = days
        self.total_minutes = days * 1440
        self.n_customers = n_customers
        self.numbers: set[str] = set()
        self.wallets: dict[str, dict] = {}
        self.txns: list[tuple] = []
        self.events: list[dict] = []
        self.cases: list[dict] = []
        self.contacts: dict[str, tuple[list[str], np.ndarray]] = {}
        self.seq = 0
        self.case_seq = 0

    # ---------- helpers ----------
    def new_number(self) -> str:
        while True:
            num = f"010{int(self.rng.integers(0, 10**8)):08d}"
            if num not in self.numbers:
                self.numbers.add(num)
                return num

    def add_wallet(self, owner_type: str, number: str | None = None, **attrs) -> str:
        number = number or self.new_number()
        self.numbers.add(number)
        row = {
            "wallet_no": number, "owner_type": owner_type, "persona": attrs.get("persona", ""),
            "district": attrs.get("district", str(self.rng.choice(DISTRICTS))),
            "age_band": attrs.get("age_band", str(self.rng.choice(AGE_BANDS, p=[0.18, 0.32, 0.25, 0.15, 0.10]))),
            "kyc_level": attrs.get("kyc_level", "full" if self.rng.random() < 0.8 else "limited"),
            "language": attrs.get("language", "bn"), "channel": attrs.get("channel", "app"),
            "opened_minute": int(attrs.get("opened_minute", -int(self.rng.integers(60, 1800)) * 1440)),
            "behaviour": attrs.get("behaviour", ""), "ring": int(attrs.get("ring", -1)),
            "initial_balance": float(attrs.get("initial_balance", 0.0)),
        }
        self.wallets[number] = row
        return number

    def tx(self, minute: int, typ: str, sender: str, receiver: str, amount: float, *, channel="app",
           status="success", source="primary", protected=False, tag="") -> None:
        self.seq += 1
        self.txns.append((int(minute), self.seq, typ, sender, receiver, float(amount), channel, status,
                          source, protected, tag))

    def amount(self, median: float, sigma: float = 0.6, lo: float = 10, hi: float | None = None) -> float:
        hi = hi or self.lim["send_money"]["per_txn_max"]
        value = float(np.exp(self.rng.normal(math.log(median), sigma)))
        return float(min(max(round(value / 10) * 10, lo), hi))

    def waking_minute(self, day: int) -> int:
        hour = int(self.rng.choice(24, p=HOUR_WEIGHTS))
        return day * 1440 + hour * 60 + int(self.rng.integers(0, 60))

    def case_id(self) -> str:
        self.case_seq += 1
        return f"FC-{self.case_seq:05d}"

    # ---------- population ----------
    def build_population(self) -> None:
        g, personas = self.a["generator"], self.a["personas"]
        names = list(personas)
        shares = np.array([personas[p]["share"] for p in names], float)
        shares /= shares.sum()
        langs = list(self.a["languages"])
        lang_p = np.array([self.a["languages"][k] for k in langs], float)
        lang_p /= lang_p.sum()

        self.agents = [self.add_wallet("agent", persona="agent") for _ in range(g["agents"])]
        self.merchants = [self.add_wallet("merchant", persona="merchant") for _ in range(g["merchants"])]
        self.employers = [self.add_wallet("employer", persona="employer") for _ in range(20)]
        self.remit_hubs = [self.add_wallet("remit_hub", persona="remittance") for _ in range(3)]
        self.mno = self.add_wallet("mno", persona="recharge")
        self.add_wallet("system", number=SYSTEM_WALLET, persona="system")

        self.customers: list[str] = []
        for _ in range(self.n_customers):
            persona = str(names[int(self.rng.choice(len(names), p=shares))])
            ussd = self.rng.random() < self.a["ussd_share"]
            num = self.add_wallet(
                "customer", persona=persona, language=str(self.rng.choice(langs, p=lang_p)),
                channel="ussd" if ussd else "app",
                initial_balance=self.amount(personas[persona]["amount_median"] * 1.5, 0.7, 50, 40000))
            self.customers.append(num)

        lo, hi = g["contacts_per_customer"]
        pool = np.array(self.customers)
        for c in self.customers:
            k = int(self.rng.integers(lo, hi + 1))
            picks = [str(x) for x in self.rng.choice(pool, size=k + 1, replace=False) if x != c][:k]
            self.contacts[c] = (picks, self.rng.dirichlet(np.ones(len(picks)) * 0.7))

    # ---------- everyday activity ----------
    def build_background(self) -> None:
        personas = self.a["personas"]
        weeks = self.days / 7
        for c in self.customers:
            w = self.wallets[c]
            p = personas[w["persona"]]
            chan = w["channel"]
            contacts, weights = self.contacts[c]
            for _ in range(int(self.rng.poisson(p["sends_per_week"] * weeks))):
                to = contacts[int(self.rng.choice(len(contacts), p=weights))]
                self.tx(self.waking_minute(int(self.rng.integers(0, self.days))), "send_money", c, to,
                        self.amount(p["amount_median"]), channel=chan)
            for _ in range(int(self.rng.poisson(0.8 * weeks))):
                self.tx(self.waking_minute(int(self.rng.integers(0, self.days))), "cash_in",
                        str(self.rng.choice(self.agents)), c, self.amount(2500, 0.6, 50, 25000), channel=chan)
            for _ in range(int(self.rng.poisson(1.0 * weeks))):
                day = int(self.rng.integers(0, self.days))
                dom = (self.start + pd.Timedelta(days=day)).day
                src = "primary"
                if dom <= 10 and w["persona"] == "salaried":
                    src = "salary"
                elif dom <= 10 and w["persona"] == "remittance_receiver":
                    src = "remittance"
                self.tx(self.waking_minute(day), "cash_out", c, str(self.rng.choice(self.agents)),
                        self.amount(2000, 0.6, 50, 25000), channel=chan, source=src)
            for _ in range(int(self.rng.poisson(1.5 * weeks))):
                self.tx(self.waking_minute(int(self.rng.integers(0, self.days))), "payment", c,
                        str(self.rng.choice(self.merchants)), self.amount(400, 0.7, 10, 20000), channel=chan)
            for _ in range(int(self.rng.poisson(1.5 * weeks))):
                self.tx(self.waking_minute(int(self.rng.integers(0, self.days))), "recharge", c, self.mno,
                        float(self.rng.choice([20, 30, 50, 100, 200])), channel=chan)
            month_starts = [d for d in range(self.days) if (self.start + pd.Timedelta(days=d)).day == 1]
            if w["persona"] == "salaried":
                employer = str(self.rng.choice(self.employers))
                for d0 in month_starts:
                    day = d0 + int(self.rng.integers(0, 7))
                    if day < self.days:
                        self.tx(day * 1440 + 600, "salary", employer, c,
                                float(self.rng.integers(120, 350) * 100), source="salary")
            if w["persona"] == "remittance_receiver":
                for d0 in month_starts:
                    for _ in range(int(self.rng.integers(1, 3))):
                        day = d0 + int(self.rng.integers(0, 25))
                        if day < self.days:
                            self.tx(self.waking_minute(day), "remittance", str(self.rng.choice(self.remit_hubs)), c,
                                    float(self.rng.integers(80, 400) * 100), source="remittance")

    # ---------- planted dispute cases ----------
    def _case_minute(self, split_day_range: tuple[int, int]) -> int:
        lo, hi = split_day_range
        return self.waking_minute(int(self.rng.integers(lo, hi)))

    def _recipient_behaviour(self, recipient: str, minute: int, amount: float, behaviour: str) -> None:
        agent = str(self.rng.choice(self.agents))
        if behaviour == "fast_mover":
            self.tx(minute + int(self.rng.integers(5, 60)), "cash_out", recipient, agent,
                    round(amount * self.rng.uniform(0.8, 1.0), -1), protected=True)
        elif behaviour == "opportunist":
            self.tx(minute + int(self.rng.integers(60, 480)), "cash_out", recipient, agent,
                    round(amount * self.rng.uniform(0.6, 1.0), -1), protected=True)
        else:  # unaware: routine spending a day or two later
            if self.rng.random() < 0.5:
                self.tx(minute + int(self.rng.integers(1440, 2880)), "payment", recipient,
                        str(self.rng.choice(self.merchants)), round(amount * self.rng.uniform(0.05, 0.3), -1))

    def _light_background(self, wallet: str) -> None:
        """Ordinary activity for an account that only appears as an accidental recipient."""
        for _ in range(int(self.rng.poisson(6))):
            self.tx(self.waking_minute(int(self.rng.integers(0, self.days))), "cash_in",
                    str(self.rng.choice(self.agents)), wallet, self.amount(1500, 0.6, 50, 20000))
        for _ in range(int(self.rng.poisson(5))):
            self.tx(self.waking_minute(int(self.rng.integers(0, self.days))), "payment", wallet,
                    str(self.rng.choice(self.merchants)), self.amount(400, 0.7, 10, 5000))
        for _ in range(int(self.rng.poisson(3))):
            self.tx(self.waking_minute(int(self.rng.integers(0, self.days))), "send_money", wallet,
                    str(self.rng.choice(self.customers)), self.amount(1000, 0.6))

    def _record_case(self, **kw) -> dict:
        row = {"case_id": self.case_id(), "variant": "", "intended_number": "", "behaviour": "",
               "involves_agent": False, "golden": "", **kw}
        self.cases.append(row)
        return row

    def _pick_contact(self, sender: str) -> str:
        contacts, weights = self.contacts[sender]
        return contacts[int(np.argmax(weights))]

    def plant_genuine(self, minute: int, sender: str | None = None, contact: str | None = None,
                      wrong: str | None = None, amount: float | None = None, behaviour: str | None = None,
                      n_prior: int | None = None, delay: int | None = None, golden: str = "") -> None:
        sender = sender or str(self.rng.choice(self.customers))
        contact = contact or self._pick_contact(sender)
        mix = self.a["recipient_behaviour"]
        kinds = ["unaware", "opportunist", "fast_mover"]
        behaviour = behaviour or str(self.rng.choice(kinds, p=np.array([mix[k] for k in kinds]) / sum(mix[k] for k in kinds)))
        if wrong is None:
            for _ in range(10):
                wrong = apply_typo(contact, self.rng, self.a["typos"])
                if wrong not in self.wallets or self.wallets[wrong]["owner_type"] == "customer":
                    break
        if wrong not in self.wallets:
            self.add_wallet("customer", number=wrong, persona="day_laborer", behaviour=behaviour,
                            initial_balance=self.amount(800, 0.8, 0, 20000))
            self._light_background(wrong)
        sw = self.wallets[sender]
        amount = amount or self.amount(self.a["personas"][sw["persona"]]["amount_median"] * 1.4)
        n_prior = n_prior if n_prior is not None else int(self.rng.integers(2, 13))
        for k in range(n_prior):
            self.tx(minute - int(self.rng.integers(2, 80)) * 1440 // max(1, (k % 3) + 1) - k * 97, "send_money",
                    sender, contact, round(amount * self.rng.uniform(0.6, 1.3), -1), protected=True,
                    channel=sw["channel"])
        tag = f"case{self.case_seq + 1}"
        self.tx(minute, "send_money", sender, wrong, amount, protected=True, tag=tag, channel=sw["channel"])
        if golden == "rahim":
            self.tx(minute + 35, "payment", wrong, str(self.rng.choice(self.merchants)), 800.0, protected=True)
        else:
            self._recipient_behaviour(wrong, minute, amount, behaviour)
        delay = delay if delay is not None else int(min(max(np.exp(self.rng.normal(math.log(25), 1.0)), 3), 4320))
        self._record_case(case_type="genuine_wrong_send", claimant=sender, recipient=wrong, amount=amount,
                          tag=tag, transfer_minute=minute, complaint_minute=minute + delay,
                          intended_number=contact, behaviour=behaviour, golden=golden)

    def plant_scam(self, minute: int, ring: int, variant: str, victim: str | None = None,
                   amount: float | None = None, delay: int | None = None, mule: str | None = None,
                   golden: str = "") -> None:
        if victim is None:
            victim = str(self.rng.choice(self.customers, p=self.victim_weights))
        members = self.rings[ring]
        mule = mule or str(self.rng.choice(members))
        amount = amount or self.amount(4000, 0.6, 500, 15000)
        tag = f"case{self.case_seq + 1}"
        self.tx(minute, "send_money", victim, mule, amount, protected=True, tag=tag,
                channel=self.wallets[victim]["channel"])
        agents = self.ring_agents[ring]
        if self.rng.random() < 0.6 or len(members) == 1:
            self.tx(minute + int(self.rng.integers(5, 40)), "cash_out", mule, str(self.rng.choice(agents)),
                    round(amount * self.rng.uniform(0.9, 1.0), -1), protected=True)
        else:
            nxt = str(self.rng.choice([m for m in members if m != mule]))
            hop = minute + int(self.rng.integers(2, 20))
            self.tx(hop, "send_money", mule, nxt, amount, protected=True, tag="keep")
            self.tx(hop + int(self.rng.integers(5, 30)), "cash_out", nxt, str(self.rng.choice(agents)),
                    round(amount * self.rng.uniform(0.9, 1.0), -1), protected=True)
        delay = delay if delay is not None else int(min(max(np.exp(self.rng.normal(math.log(360), 1.0)), 10), 5760))
        self._record_case(case_type="scam_victim", claimant=victim, recipient=mule, amount=amount, tag=tag,
                          transfer_minute=minute, complaint_minute=minute + delay, variant=variant, golden=golden)

    def plant_double_recovery(self, minute: int, fraudster: str) -> None:
        victim = str(self.rng.choice(self.customers))
        amount = self.amount(3000, 0.6, 500, 10000)
        tag = f"case{self.case_seq + 1}"
        self.tx(minute, "send_money", fraudster, victim, amount, protected=True, tag=tag)
        back = minute + int(self.rng.integers(10, 120))
        self.tx(back, "send_money", victim, fraudster, amount, protected=True, tag="keep")
        self.tx(back + int(self.rng.integers(10, 90)), "cash_out", fraudster, str(self.rng.choice(self.agents)),
                round(amount * 0.95, -1), protected=True)
        self._record_case(case_type="double_recovery", claimant=fraudster, recipient=victim, amount=amount, tag=tag,
                          transfer_minute=minute, complaint_minute=back + int(self.rng.integers(20, 600)))

    def plant_false_claim(self, minute: int) -> None:
        sender = str(self.rng.choice(self.customers))
        contact = self._pick_contact(sender)
        amount = self.amount(self.a["personas"][self.wallets[sender]["persona"]]["amount_median"] * 1.5)
        for k in range(int(self.rng.integers(3, 10))):
            self.tx(minute - int(self.rng.integers(3, 85)) * 1440 + k, "send_money", sender, contact,
                    round(amount * self.rng.uniform(0.5, 1.2), -1), protected=True)
        tag = f"case{self.case_seq + 1}"
        self.tx(minute, "send_money", sender, contact, amount, protected=True, tag=tag)
        self._record_case(case_type="false_claim", claimant=sender, recipient=contact, amount=amount, tag=tag,
                          transfer_minute=minute,
                          complaint_minute=minute + int(self.rng.integers(2, 10)) * 1440 + int(self.rng.integers(0, 600)))

    def plant_technical(self, minute: int) -> None:
        sender = str(self.rng.choice(self.customers))
        contact = self._pick_contact(sender)
        amount = self.amount(2500)
        tag = f"case{self.case_seq + 1}"
        self.tx(minute, "send_money", sender, contact, amount, status="failed_credit", protected=True, tag=tag)
        self.events.append({"tag": tag, "minute": minute, "event": "debit_ok"})
        self.events.append({"tag": tag, "minute": minute + 1, "event": "credit_fail"})
        if self.rng.random() < 0.3:
            self.tx(minute + int(self.rng.integers(120, 1440)), "reversal", SYSTEM_WALLET, sender, amount,
                    status="reversal", protected=True, tag=tag + "r")
            self.events.append({"tag": tag, "minute": minute + 2, "event": "reversal_scheduled"})
        self._record_case(case_type="technical_failure", claimant=sender, recipient=contact, amount=amount, tag=tag,
                          transfer_minute=minute, complaint_minute=minute + int(self.rng.integers(10, 300)))

    def build_cases(self) -> None:
        c = self.a["cases"]
        sp = self.a["splits"]
        total = c["total"]
        mix = c["mix"]
        held_out = c.get("held_out_scam_variant", "job_offer")

        w = np.array([2.0 if (self.wallets[c]["channel"] == "ussd" or self.wallets[c]["age_band"] in ("45-54", "55+"))
                      else 1.0 for c in self.customers])
        self.victim_weights = w / w.sum()
        mr = self.a["mule_rings"]
        self.rings: list[list[str]] = []
        self.ring_agents: list[list[str]] = []
        for r in range(mr["count"]):
            size = int(self.rng.integers(mr["size"][0], mr["size"][1] + 1))
            opened = -int(self.rng.integers(1, mr["account_age_days_max"])) * 1440
            members = [self.add_wallet("mule", ring=r, opened_minute=opened, kyc_level="limited",
                                       persona="mule", initial_balance=0.0) for _ in range(size)]
            self.rings.append(members)
            self.ring_agents.append([str(x) for x in self.rng.choice(self.agents, size=2, replace=False)])
        fraudsters = [self.add_wallet("fraudster", persona="fraudster", kyc_level="limited",
                                      opened_minute=-int(self.rng.integers(10, 200)) * 1440,
                                      initial_balance=self.amount(3000, 0.5, 500, 10000)) for _ in range(40)]

        day_lo = 3
        windows = {"train": (day_lo, sp["train_days"][1]), "valid": tuple(sp["valid_days"]),
                   "test": (sp["test_days"][0], self.days - 1)}

        def window_for(i: int, n: int) -> tuple[int, int]:
            # spread each type over the three splits roughly by their length
            frac = i / max(n, 1)
            if frac < 0.62:
                return windows["train"]
            if frac < 0.80:
                return windows["valid"]
            return windows["test"]

        n_gen = int(total * mix["genuine_wrong_send"])
        for i in range(n_gen):
            self.plant_genuine(self._case_minute(window_for(i, n_gen)))
        n_scam = int(total * mix["scam_victim"])
        variants = ["fake_sms", "impersonation", "prize"]
        for i in range(n_scam):
            win = window_for(i, n_scam)
            pool = variants + ([held_out] if win == windows["test"] else [])
            self.plant_scam(self._case_minute(win), int(self.rng.integers(0, len(self.rings))),
                            str(self.rng.choice(pool)))
        n_dbl = int(total * mix["double_recovery"])
        for i in range(n_dbl):
            self.plant_double_recovery(self._case_minute(window_for(i, n_dbl)), str(self.rng.choice(fraudsters)))
        n_false = int(total * mix["false_claim"])
        for i in range(n_false):
            self.plant_false_claim(self._case_minute(window_for(i, n_false)))
        n_tech = int(total * mix["technical_failure"])
        for i in range(n_tech):
            self.plant_technical(self._case_minute(window_for(i, n_tech)))
        self.plant_golden_path()

    def plant_golden_path(self) -> None:
        """Two fixed cases for the demo: Rahim's typo and Shirin's scam."""
        self.add_wallet("customer", number=RAHIM, persona="small_merchant", language="banglish",
                        district="Rajshahi", age_band="35-44", initial_balance=12000.0)
        self.add_wallet("customer", number=RAHIM_BROTHER, persona="salaried", language="bn",
                        district="Rajshahi", initial_balance=3000.0)
        self.add_wallet("customer", number=RAHIM_WRONG, persona="day_laborer", district="Khulna",
                        behaviour="unaware", initial_balance=0.0)
        self.contacts[RAHIM] = ([RAHIM_BROTHER], np.array([1.0]))
        day = self.days - 3
        self.plant_genuine(day * 1440 + 14 * 60 + 2, sender=RAHIM, contact=RAHIM_BROTHER, wrong=RAHIM_WRONG,
                           amount=5000.0, behaviour="unaware", n_prior=11, delay=23, golden="rahim")

        ring = 0
        self.add_wallet("mule", number=SHIRIN_MULE, ring=ring, opened_minute=(self.days - 25) * 1440,
                        kyc_level="limited", persona="mule", initial_balance=0.0)
        self.rings[ring].append(SHIRIN_MULE)
        for k in range(14):  # 14 earlier victims of the same wallet
            self.plant_scam((self.days - 20 + k // 2) * 1440 + 600 + 37 * k, ring, "fake_sms", mule=SHIRIN_MULE)
        self.add_wallet("customer", number=SHIRIN, persona="remittance_receiver", language="bn",
                        channel="ussd", district="Sylhet", age_band="55+", initial_balance=9000.0)
        self.plant_scam((self.days - 2) * 1440 + 11 * 60 + 15, ring, "fake_sms", victim=SHIRIN, amount=3000.0,
                        delay=95, mule=SHIRIN_MULE, golden="shirin")

    # ---------- ledger with balances and limits ----------
    def finalize(self) -> World:
        wallets = pd.DataFrame(list(self.wallets.values()))
        tx = pd.DataFrame(self.txns, columns=TX_COLUMNS)
        tx = tx[(tx["minute"] >= 0) & (tx["minute"] < self.total_minutes)]
        tx = tx.sort_values(["minute", "seq"]).reset_index(drop=True)

        owner = dict(zip(wallets["wallet_no"], wallets["owner_type"]))
        owner_of = owner.get
        balance = dict(zip(wallets["wallet_no"], wallets["initial_balance"]))
        send_cap = self.lim["send_money"]["daily_max"]
        cash_cap = self.lim["cash_out_agent"]["daily_max"]
        fees = self.lim["fees"]["cash_out_agent"]

        # reserve each day's protected (case) volume first, so background activity never pushes a
        # wallet over upay's daily limits (R17)
        reserved: dict[tuple[str, int, str], float] = {}
        prot_idx = tx.index[tx["protected"] & tx["type"].isin(["send_money", "cash_out"])]
        # disputed transfers and the double-recovery "return" are kept whole; supporting history is
        # trimmed if it would break a daily limit
        keep_first = sorted(prot_idx, key=lambda i: 0 if tx.at[i, "tag"] else 1)
        for i in keep_first:
            s_, m, t, amt = tx.at[i, "sender"], tx.at[i, "minute"], tx.at[i, "type"], tx.at[i, "amount"]
            if owner_of(s_) in UNLIMITED_TYPES:
                continue
            key = (s_, m // 1440, t)
            cap = send_cap if t == "send_money" else cash_cap
            if not tx.at[i, "tag"]:
                amt = min(amt, max(cap - reserved.get(key, 0.0), 0.0))
                tx.at[i, "amount"] = amt
            reserved[key] = reserved.get(key, 0.0) + amt
        tx = tx[tx["amount"] > 0].reset_index(drop=True)
        used: dict[tuple[str, int, str], float] = {}

        out_amount, out_status, out_fee, s_bal, r_bal = [], [], [], [], []
        topups: list[tuple] = []
        for row in tx.itertuples(index=False):
            amt = row.amount
            status = row.status
            s_unl = owner.get(row.sender) in UNLIMITED_TYPES
            r_unl = owner.get(row.receiver) in UNLIMITED_TYPES
            fee = 0.0
            if row.type in ("send_money", "cash_out") and not s_unl:
                key = (row.sender, row.minute // 1440, row.type)
                cap = send_cap if row.type == "send_money" else cash_cap
                if not row.protected:
                    room = cap - reserved.get(key, 0.0) - used.get(key, 0.0)
                    amt = min(amt, max(room, 0.0))
                used[key] = used.get(key, 0.0) + (amt if not row.protected else 0.0)
            if row.type == "cash_out" and not s_unl:
                fee = round(amt * fees.get(row.source_wallet, fees["primary"]), 2)
            if not s_unl:
                need = amt + fee
                if balance.get(row.sender, 0.0) < need:
                    if row.protected:
                        top = math.ceil((need - balance.get(row.sender, 0.0)) / 100) * 100
                        balance[row.sender] = balance.get(row.sender, 0.0) + top
                        topups.append((row.minute - 1, row.sender, top))
                    else:
                        rate = fees.get(row.source_wallet, fees["primary"]) if row.type == "cash_out" else 0.0
                        amt = math.floor(max(balance.get(row.sender, 0.0) - 1, 0) / (1 + rate) / 10) * 10
                        fee = round(amt * rate, 2)
                if amt <= 0:
                    status = "dropped"
            if status != "dropped":
                if not s_unl:
                    balance[row.sender] = round(balance.get(row.sender, 0.0) - amt - fee, 2)
                if not r_unl and status not in ("failed_credit",):
                    balance[row.receiver] = round(balance.get(row.receiver, 0.0) + amt, 2)
            out_amount.append(amt)
            out_status.append(status)
            out_fee.append(fee)
            s_bal.append(balance.get(row.sender, 0.0) if not s_unl else np.nan)
            r_bal.append(balance.get(row.receiver, 0.0) if not r_unl else np.nan)

        tx = tx.assign(amount=out_amount, status=out_status, fee=out_fee,
                       sender_balance_after=s_bal, receiver_balance_after=r_bal)
        if topups:
            agent = self.agents[0]
            extra = pd.DataFrame([{"minute": m, "seq": 0, "type": "cash_in", "sender": agent, "receiver": w,
                                   "amount": float(a), "channel": "app", "status": "success",
                                   "source_wallet": "primary", "protected": True, "tag": "", "fee": 0.0,
                                   "sender_balance_after": np.nan, "receiver_balance_after": np.nan}
                                  for m, w, a in topups])
            tx = pd.concat([tx, extra], ignore_index=True)
        tx = tx[tx["status"] != "dropped"].sort_values(["minute", "seq"]).reset_index(drop=True)
        tx = self._recompute_balances(tx, wallets, owner)
        tx["trx_id"] = [f"TX{int(x):08X}" for x in self.rng.permutation(len(tx)) + 0x1A2B3C]
        tx["ts"] = self.start + pd.to_timedelta(tx["minute"], unit="m")

        tag_to_trx = dict(zip(tx.loc[tx["tag"] != "", "tag"], tx.loc[tx["tag"] != "", "trx_id"]))
        cases = pd.DataFrame(self.cases)
        cases["disputed_trx_id"] = cases["tag"].map(tag_to_trx)
        cases = cases[cases["disputed_trx_id"].notna() & (cases["complaint_minute"] < self.total_minutes)].copy()
        cases["complaint_ts"] = self.start + pd.to_timedelta(cases["complaint_minute"], unit="m")
        cases["transfer_ts"] = self.start + pd.to_timedelta(cases["transfer_minute"], unit="m")
        sp = self.a["splits"]
        day = cases["complaint_minute"] // 1440
        cases["split"] = np.where(day < sp["train_days"][1], "train", np.where(day < sp["valid_days"][1], "valid", "test"))
        types = sorted(cases["case_type"].unique())
        noisy = cases["case_type"].copy()
        flip = (self.rng.random(len(cases)) < self.a["cases"]["label_noise"]) & (cases["golden"] == "")
        noisy[flip] = [str(self.rng.choice([t for t in types if t != v])) for v in cases.loc[flip, "case_type"]]
        cases["label_train"] = noisy
        lw = wallets.set_index("wallet_no")
        cases["language"] = cases["claimant"].map(lw["language"]).fillna("bn")
        cases["channel"] = np.where(cases["claimant"].map(lw["channel"]) == "ussd", "call",
                                    np.where(self.rng.random(len(cases)) < 0.3, "call", "app"))
        events = pd.DataFrame(self.events) if self.events else pd.DataFrame(columns=["tag", "minute", "event"])
        events["trx_id"] = events["tag"].map(tag_to_trx)
        wallets["opened_ts"] = self.start + pd.to_timedelta(wallets["opened_minute"], unit="m")
        return World(wallets=wallets, transactions=tx.drop(columns=["seq"]), system_events=events,
                     cases=cases.reset_index(drop=True), start=self.start, days=self.days)

    @staticmethod
    def _recompute_balances(tx: pd.DataFrame, wallets: pd.DataFrame, owner: dict) -> pd.DataFrame:
        """Second pass so top-up cash-ins are reflected in every later balance."""
        balance = dict(zip(wallets["wallet_no"], wallets["initial_balance"]))
        s_bal, r_bal = [], []
        for row in tx.itertuples(index=False):
            s_unl = owner.get(row.sender) in UNLIMITED_TYPES
            r_unl = owner.get(row.receiver) in UNLIMITED_TYPES
            if not s_unl:
                balance[row.sender] = round(balance.get(row.sender, 0.0) - row.amount - row.fee, 2)
            if not r_unl and row.status != "failed_credit":
                balance[row.receiver] = round(balance.get(row.receiver, 0.0) + row.amount, 2)
            s_bal.append(balance.get(row.sender) if not s_unl else np.nan)
            r_bal.append(balance.get(row.receiver) if not r_unl else np.nan)
        return tx.assign(sender_balance_after=s_bal, receiver_balance_after=r_bal)


def build_world(seed: int | None = None, customers: int | None = None, days: int | None = None) -> World:
    s = config.settings()
    b = _Builder(seed if seed is not None else s.seed, customers or s.customers, days or s.days)
    b.build_population()
    b.build_background()
    b.build_cases()
    return b.finalize()
