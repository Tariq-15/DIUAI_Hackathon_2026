"""M2 transaction matcher: which ledger transaction is the customer complaining about?

Candidates are the claimant's own outgoing transfers in the 7 days before the complaint. Each is
scored on amount, number similarity, stated time and TrxID. A low margin means "ask the agent".
"""

from __future__ import annotations

import math

from ferot.datagen.typos import keypad_distance
from ferot.features.ledger import Ledger
from ferot.models.extract import Extraction

SEND_TYPES = {"send_money", "payment"}


def match_transaction(ledger: Ledger, claimant: str, extraction: Extraction, complaint_minute: int) -> dict:
    idx = ledger.outgoing(claimant, complaint_minute - 7 * 1440, complaint_minute)
    idx = [i for i in idx if ledger.type[i] in SEND_TYPES]
    if not idx:
        return {"trx_id": None, "confidence": 0.0, "candidates": []}
    scored = []
    for i in idx:
        row_amount = float(ledger.amount[i])
        receiver = str(ledger.receiver[i])
        trx_id = str(ledger.tx.at[i, "trx_id"])
        score = 0.0
        if extraction.trx_id and extraction.trx_id == trx_id:
            score += 5.0
        if extraction.amount:
            diff = abs(row_amount - extraction.amount) / max(row_amount, 1)
            score += 1.5 if diff < 0.005 else (0.8 if diff <= 0.12 else 0.0)
        if extraction.number:
            d = keypad_distance(extraction.number, receiver)
            score += 2.0 if d == 0 else (0.8 if d <= 1.0 else 0.0)
        elif extraction.number_last4 and receiver.endswith(extraction.number_last4):
            score += 1.6
        if extraction.hour is not None:
            day = extraction.day_offset or 0
            stated = (complaint_minute // 1440 - day) * 1440 + extraction.hour * 60 + 30
            score += 0.7 * math.exp(-abs(int(ledger.minute[i]) - stated) / 180)
        # recency prior: complaints are usually about the latest transfers
        score += 0.3 * math.exp(-(complaint_minute - int(ledger.minute[i])) / (2 * 1440))
        scored.append((score, i, trx_id))
    scored.sort(reverse=True)
    top = scored[0]
    second = scored[1][0] if len(scored) > 1 else 0.0
    confidence = round(min(1.0, max(0.0, (top[0] - second) / 2.0 + (0.4 if top[0] >= 2.5 else 0.0))), 3)
    return {
        "trx_id": top[2],
        "confidence": confidence,
        "candidates": [{"trx_id": t, "score": round(s, 3), "amount": float(ledger.amount[i]),
                        "receiver": str(ledger.receiver[i]), "ts": ledger.ts(int(ledger.minute[i]))}
                       for s, i, t in scored[:5]],
    }
