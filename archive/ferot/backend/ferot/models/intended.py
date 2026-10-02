"""M3 intended-number matcher: which number did the customer probably mean to type?

Compares the disputed recipient with every number the sender paid before the transfer, using a
keypad-weighted edit distance, and prefers frequent, recent contacts.
"""

from __future__ import annotations

import math

import numpy as np

from ferot.datagen.typos import changed_positions, keypad_distance
from ferot.features.ledger import Ledger

MAX_DISTANCE = 2.0


def intended_number(ledger: Ledger, sender: str, recipient: str, before_minute: int) -> dict:
    idx = ledger.outgoing(sender, before_minute - 120 * 1440, before_minute - 1)
    idx = idx[ledger.type[idx] == "send_money"]
    if len(idx) == 0:
        return {"found": False, "score": 0.0, "distance": None, "candidate": None, "count": 0, "positions": []}
    receivers = ledger.receiver[idx]
    minutes = ledger.minute[idx]
    best = None
    for number in np.unique(receivers):
        if number == recipient:
            continue
        d = keypad_distance(recipient, str(number))
        if d > MAX_DISTANCE:
            continue
        mask = receivers == number
        count = int(mask.sum())
        days_ago = (before_minute - int(minutes[mask].max())) / 1440
        score = math.exp(-1.5 * d) * (1 + math.log1p(count)) * math.exp(-days_ago / 60)
        if best is None or score > best["score"]:
            best = {"found": True, "score": round(score, 4), "distance": round(d, 2), "candidate": str(number),
                    "count": count, "positions": changed_positions(str(number), recipient)}
    return best or {"found": False, "score": 0.0, "distance": None, "candidate": None, "count": 0, "positions": []}
