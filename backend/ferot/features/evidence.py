"""Evidence builder and model features for one dispute, computed as of the complaint time.

Nothing here reads a wallet's true type (mule, fraudster...). Features come only from behaviour in
the ledger before the complaint, plus what the customer wrote.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from ferot import config
from ferot.features.ledger import Ledger
from ferot.models.extract import CUES, Extraction
from ferot.models.intended import intended_number

FEATURES = [
    "n_prior_to_recipient", "first_ever", "intended_found", "intended_score", "intended_distance",
    "log_minutes_to_complaint", "transfer_hour", "recipient_age_days", "recipient_distinct_senders_7d",
    "recipient_new_sender_share_7d", "recipient_outflow_share_since", "minutes_to_first_outflow",
    "recipient_passthrough_30d", "recipient_inbound_30d", "prior_complainants_on_recipient", "return_flow",
    "claimant_prior_claims", "claimant_age_days", "claimant_kyc_full", "claimant_ussd", "tech_failure",
    "log_amount", "recoverable_share_now", "remaining_cashout_limit",
] + [f"cue_{k}" for k in CUES]

TEXT_FEATURES = [f"cue_{k}" for k in CUES]
GRAPH_FEATURES = ["recipient_distinct_senders_7d", "recipient_new_sender_share_7d", "recipient_passthrough_30d",
                  "prior_complainants_on_recipient", "return_flow", "recipient_inbound_30d"]

FEATURE_LABELS = {
    "n_prior_to_recipient": "earlier transfers to this number",
    "first_ever": "first-ever transfer to this number",
    "intended_found": "a frequent contact differs by one keypad slip",
    "intended_score": "strength of the typo match",
    "intended_distance": "keypad distance to the closest contact",
    "log_minutes_to_complaint": "time from transfer to complaint",
    "transfer_hour": "hour of the transfer",
    "recipient_age_days": "age of the receiving wallet",
    "recipient_distinct_senders_7d": "unrelated senders to the receiving wallet in 7 days",
    "recipient_new_sender_share_7d": "share of first-time senders to the receiving wallet",
    "recipient_outflow_share_since": "share of the money moved out before the complaint",
    "minutes_to_first_outflow": "minutes until the money started moving",
    "recipient_passthrough_30d": "how fast the receiving wallet usually passes money on",
    "recipient_inbound_30d": "incoming transfers to the receiving wallet in 30 days",
    "prior_complainants_on_recipient": "other customers who complained about this wallet",
    "return_flow": "the recipient already sent the same amount back",
    "claimant_prior_claims": "earlier claims by this customer",
    "claimant_age_days": "age of the customer's account",
    "claimant_kyc_full": "customer has full KYC",
    "claimant_ussd": "customer uses USSD",
    "tech_failure": "system log shows a failed credit",
    "log_amount": "amount",
    "recoverable_share_now": "share of the money still in the receiving wallet",
    "remaining_cashout_limit": "receiving wallet's remaining daily cash-out limit",
}
for _k in CUES:
    FEATURE_LABELS[f"cue_{_k}"] = f"complaint mentions '{_k.replace('_', '/')}'"


class CaseHistory:
    """Earlier complaints, used for 'how many others complained about this wallet' features."""

    def __init__(self, cases: pd.DataFrame | None = None):
        cols = ["claimant", "recipient", "complaint_minute"]
        self.df = cases[cols].copy() if cases is not None and len(cases) else pd.DataFrame(columns=cols)

    def add(self, claimant: str, recipient: str, minute: int) -> None:
        self.df.loc[len(self.df)] = [claimant, recipient, minute]

    def counts(self, claimant: str, recipient: str, before: int) -> tuple[int, int]:
        d = self.df[self.df["complaint_minute"] < before]
        on_recipient = d.loc[(d["recipient"] == recipient) & (d["claimant"] != claimant), "claimant"].nunique()
        by_claimant = int((d["claimant"] == claimant).sum())
        return int(on_recipient), by_claimant


@dataclass
class Evidence:
    features: dict
    facts: dict
    trail: list[dict]
    intended: dict
    recoverable_now: float


def build_evidence(ledger: Ledger, claimant: str, trx_id: str, complaint_minute: int,
                   extraction: Extraction, history: CaseHistory) -> Evidence:
    row = ledger.row(trx_id)
    recipient = str(row["receiver"])
    t0 = int(row["minute"])
    amount = float(row["amount"])
    lim = config.limits()

    prior = ledger.outgoing(claimant, t0 - 180 * 1440, t0 - 1)
    n_prior = int(np.sum((ledger.receiver[prior] == recipient) & (ledger.type[prior] == "send_money")))
    intended = intended_number(ledger, claimant, recipient, t0)

    inbound_7d = ledger.incoming(recipient, complaint_minute - 7 * 1440, complaint_minute)
    inbound_7d = inbound_7d[ledger.type[inbound_7d] == "send_money"]
    senders = ledger.sender[inbound_7d]
    distinct = len(set(senders))
    new_share = 0.0
    if distinct:
        older = ledger.incoming(recipient, complaint_minute - 120 * 1440, complaint_minute - 7 * 1440)
        known = set(ledger.sender[older])
        new_share = sum(1 for s in set(senders) if s not in known) / distinct

    out_since = ledger.outgoing(recipient, t0 + 1, complaint_minute)
    out_since = out_since[np.isin(ledger.type[out_since], ["cash_out", "send_money", "payment"])]
    outflow = float(ledger.amount[out_since].sum()) if len(out_since) else 0.0
    first_out = int(ledger.minute[out_since].min() - t0) if len(out_since) else 99999

    in_30 = ledger.incoming(recipient, t0 - 30 * 1440, t0 - 1)
    out_30 = ledger.outgoing(recipient, t0 - 30 * 1440, t0 - 1)
    cash_30 = out_30[ledger.type[out_30] == "cash_out"]
    passthrough = float(ledger.amount[cash_30].sum()) / max(float(ledger.amount[in_30].sum()), 1.0)

    return_idx = ledger.outgoing(recipient, t0 + 1, complaint_minute)
    return_flow = int(any((ledger.receiver[i] == claimant) and abs(ledger.amount[i] - amount) <= 0.01 * amount
                          for i in return_idx))

    on_recipient, by_claimant = history.counts(claimant, recipient, complaint_minute)
    rinfo, cinfo = ledger.wallet_info(recipient), ledger.wallet_info(claimant)
    failed = int(row["status"] == "failed_credit" or trx_id in ledger.failed_trx)

    balance_now = ledger.balance_at(recipient, complaint_minute)
    recoverable = 0.0 if failed else float(min(amount, max(balance_now, 0.0)))
    day_start = (complaint_minute // 1440) * 1440
    cash_today = ledger.outgoing(recipient, day_start, complaint_minute)
    cash_today = cash_today[ledger.type[cash_today] == "cash_out"]
    remaining_limit = max(lim["cash_out_agent"]["daily_max"] - float(ledger.amount[cash_today].sum()), 0.0)

    features = {
        "n_prior_to_recipient": n_prior,
        "first_ever": int(n_prior == 0),
        "intended_found": int(intended["found"]),
        "intended_score": intended["score"],
        "intended_distance": intended["distance"] if intended["distance"] is not None else 9.0,
        "log_minutes_to_complaint": math.log1p(max(complaint_minute - t0, 0)),
        "transfer_hour": t0 % 1440 // 60,
        "recipient_age_days": (complaint_minute - rinfo.get("opened_minute", complaint_minute)) / 1440,
        "recipient_distinct_senders_7d": distinct,
        "recipient_new_sender_share_7d": round(new_share, 3),
        "recipient_outflow_share_since": round(min(outflow / max(amount, 1.0), 3.0), 3),
        "minutes_to_first_outflow": min(first_out, 99999),
        "recipient_passthrough_30d": round(min(passthrough, 3.0), 3),
        "recipient_inbound_30d": int(len(in_30)),
        "prior_complainants_on_recipient": on_recipient,
        "return_flow": return_flow,
        "claimant_prior_claims": by_claimant,
        "claimant_age_days": (complaint_minute - cinfo.get("opened_minute", complaint_minute)) / 1440,
        "claimant_kyc_full": int(cinfo.get("kyc_level") == "full"),
        "claimant_ussd": int(cinfo.get("channel") == "ussd"),
        "tech_failure": failed,
        "log_amount": math.log1p(amount),
        "recoverable_share_now": round(recoverable / max(amount, 1.0), 3),
        "remaining_cashout_limit": remaining_limit,
        "complaint_hour": complaint_minute % 1440 // 60,
    }
    for k in CUES:
        features[f"cue_{k}"] = int(extraction.cues.get(k, False))

    trail = _money_trail(ledger, recipient, t0, complaint_minute, trx_id)
    facts = {
        "trx_id": trx_id, "sender": claimant, "recipient": recipient, "amount": amount,
        "transfer_ts": ledger.ts(t0), "complaint_ts": ledger.ts(complaint_minute), "status": str(row["status"]),
        "earlier_transfers_to_recipient": n_prior, "recipient_balance_now": round(balance_now, 2),
        "recoverable_now": round(recoverable, 2), "outflow_since_transfer": round(outflow, 2),
        "return_flow": bool(return_flow), "other_complainants_on_recipient": on_recipient,
        "claimant_prior_claims": by_claimant, "remaining_cashout_limit_today": remaining_limit,
        "involves_agent": False,
    }
    return Evidence(features=features, facts=facts, trail=trail, intended=intended, recoverable_now=recoverable)


def _money_trail(ledger: Ledger, recipient: str, t0: int, until: int, trx_id: str) -> list[dict]:
    """The disputed transfer plus where the money went next (one onward hop), up to the complaint."""
    disputed = ledger.by_trx[trx_id]
    steps = [_step(ledger, disputed, hop=0)]
    first = ledger.outgoing(recipient, t0 + 1, min(until, t0 + 48 * 60))
    for i in first[:8]:
        steps.append(_step(ledger, i, hop=1))
        nxt = str(ledger.receiver[i])
        if ledger.type[i] == "send_money":
            for j in ledger.outgoing(nxt, int(ledger.minute[i]) + 1, min(until, int(ledger.minute[i]) + 24 * 60))[:3]:
                steps.append(_step(ledger, j, hop=2))
    return steps


def _step(ledger: Ledger, i: int, hop: int) -> dict:
    return {
        "hop": hop, "trx_id": str(ledger.tx.at[i, "trx_id"]), "type": str(ledger.type[i]),
        "from": str(ledger.sender[i]), "to": str(ledger.receiver[i]), "amount": float(ledger.amount[i]),
        "ts": ledger.ts(int(ledger.minute[i])), "to_kind": ledger.owner_type(str(ledger.receiver[i]))
        if ledger.owner_type(str(ledger.receiver[i])) in ("agent", "merchant") else "wallet",
    }
