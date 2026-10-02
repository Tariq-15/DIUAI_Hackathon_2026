"""Wrong-person check before the money leaves: "Did you mean 01076254257 (মা)?"

Merged from Ferot Guard (our Track 06 project): a keypad-weighted edit distance between the number being typed
and the numbers this customer has paid before, preferring frequent contacts. It uses only the sender's own
history, so in the app it runs on the phone and the contact list never leaves the device.

The edit costs say how likely each finger slip is. They start from Ferot's hand-set values (a neighbouring key
0.6, any other digit 1.0, two adjacent digits swapped 0.8) and can be replaced by costs learned on-device with
federated averaging of noisy slip counts (src/fl/ondevice.py writes artifacts/portable/slip_costs.json).
"""
from __future__ import annotations

import json
import math
from pathlib import Path

KEYPAD_NEIGHBOURS: dict[str, set[str]] = {
    "1": {"2", "4"}, "2": {"1", "3", "5"}, "3": {"2", "6"}, "4": {"1", "5", "7"}, "5": {"2", "4", "6", "8"},
    "6": {"3", "5", "9"}, "7": {"4", "8"}, "8": {"5", "7", "9", "0"}, "9": {"6", "8"}, "0": {"8"},
}
MAX_DISTANCE = 1.6          # from Ferot's config/guard.yaml
MIN_EARLIER_SENDS = 2
DIGITS = "0123456789"


def default_costs() -> dict:
    sub = {a: {b: (0.0 if a == b else 0.6 if b in KEYPAD_NEIGHBOURS[a] else 1.0) for b in DIGITS} for a in DIGITS}
    return dict(sub=sub, transposition=0.8, source="hand-set (Ferot Guard)")


def load_costs(path: str | Path | None) -> dict:
    """Federated slip costs if they have been learned, otherwise the hand-set ones."""
    if path and Path(path).exists():
        c = json.loads(Path(path).read_text(encoding="utf-8"))
        return dict(sub=c["sub"], transposition=c["transposition"], source=c.get("source", "federated"))
    return default_costs()


def keypad_distance(intended: str, typed: str, costs: dict) -> float:
    """Damerau-Levenshtein distance from the number meant to the number typed, with slip-specific costs."""
    a, b, sub = intended, typed, costs["sub"]
    n, m = len(a), len(b)
    d = [[0.0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        d[i][0] = float(i)
    for j in range(m + 1):
        d[0][j] = float(j)
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            s = sub.get(a[i - 1], {}).get(b[j - 1], 1.0)
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + s)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1] and a[i - 1] != a[i - 2]:
                d[i][j] = min(d[i][j], d[i - 2][j - 2] + costs["transposition"])
    return d[n][m]


def changed_positions(a: str, b: str) -> list[int]:
    return [i for i, (x, y) in enumerate(zip(a, b)) if x != y] if len(a) == len(b) else []


BN = str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯")


def describe(meant: str, typed: str) -> dict:
    """Which digit went wrong, in plain words: a swap of two neighbours, one wrong key (next to the right one?), or other."""
    pos = changed_positions(meant, typed)
    if len(pos) == 2 and pos[1] == pos[0] + 1 and meant[pos[0]] == typed[pos[1]] and meant[pos[1]] == typed[pos[0]]:
        i = pos[0]
        a, b = meant[i:i + 2], typed[i:i + 2]
        return dict(kind="swap", positions=[i + 1, i + 2], meant=a, typed=b,
                    en=f"digits {i + 1} and {i + 2} are swapped: you typed {b} instead of {a}",
                    bn=f"{str(i + 1).translate(BN)} ও {str(i + 2).translate(BN)} নম্বর ডিজিট উল্টে গেছে: "
                       f"{a.translate(BN)} এর বদলে {b.translate(BN)} লিখেছেন")
    if len(pos) == 1:
        i = pos[0]
        m, t = meant[i], typed[i]
        near = t in KEYPAD_NEIGHBOURS.get(m, set())
        return dict(kind="wrong_key", positions=[i + 1], meant=m, typed=t, neighbour=near,
                    en=f"digit {i + 1}: you typed {t} instead of {m}" + (" (the key next to it)" if near else ""),
                    bn=f"{str(i + 1).translate(BN)} নম্বর ডিজিটে {m.translate(BN)} এর বদলে {t.translate(BN)} লিখেছেন"
                       + (" (পাশের বোতাম)" if near else ""))
    return dict(kind="other", positions=[i + 1 for i in pos], meant=meant, typed=typed,
                en="the number differs by a small typing mistake", bn="নম্বরে ছোট একটি টাইপের ভুল আছে")


def check(sent_to: dict, msisdn_of: dict, typed: str, costs: dict) -> dict | None:
    """The most likely intended number among this sender's frequent contacts, or None.

    sent_to: recipient wallet -> earlier transfers (the sender's own history); msisdn_of: wallet -> number.
    """
    if not typed:
        return None
    best = None
    for wallet, count in sent_to.items():
        if count < MIN_EARLIER_SENDS:
            continue
        number = msisdn_of.get(wallet)
        if not number or number == typed:
            continue
        dist = keypad_distance(number, typed, costs)
        if dist > MAX_DISTANCE:
            continue
        score = math.exp(-1.5 * dist) * (1 + math.log1p(count))
        if best is None or score > best["score"]:
            best = dict(wallet=wallet, msisdn=number, count=int(count), distance=round(dist, 2), score=round(score, 4),
                        positions=changed_positions(number, typed), slip=describe(number, typed))
    return best
