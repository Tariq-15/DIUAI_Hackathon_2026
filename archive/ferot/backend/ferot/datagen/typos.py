"""How people mistype an 11-digit mobile number, and how far apart two numbers are.

The phone keypad layout drives both: a slip to a neighbouring key is the most common mistake,
so it is both the most likely typo to generate and the cheapest edit to explain.
"""

from __future__ import annotations

import numpy as np

KEYPAD_NEIGHBOURS: dict[str, set[str]] = {
    "1": {"2", "4"},
    "2": {"1", "3", "5"},
    "3": {"2", "6"},
    "4": {"1", "5", "7"},
    "5": {"2", "4", "6", "8"},
    "6": {"3", "5", "9"},
    "7": {"4", "8"},
    "8": {"5", "7", "9", "0"},
    "9": {"6", "8"},
    "0": {"8"},
}

PROTECTED_PREFIX = 3  # the "010" operator prefix is rarely mistyped; typos land in the last 8 digits


def _substitute(digits: list[str], rng: np.random.Generator) -> None:
    i = int(rng.integers(PROTECTED_PREFIX, len(digits)))
    old = digits[i]
    if rng.random() < 0.7:
        digits[i] = str(rng.choice(sorted(KEYPAD_NEIGHBOURS[old])))
    else:
        digits[i] = str(rng.choice([d for d in "0123456789" if d != old]))


def apply_typo(number: str, rng: np.random.Generator, mix: dict[str, float]) -> str:
    """Return a different number produced by one realistic typing mistake."""
    kinds = ["substitution", "transposition", "double_substitution"]
    probs = np.array([mix.get(k, 0.0) for k in kinds], dtype=float)
    probs = probs / probs.sum()
    for _ in range(20):
        digits = list(number)
        kind = kinds[int(rng.choice(3, p=probs))]
        if kind == "transposition":
            i = int(rng.integers(PROTECTED_PREFIX, len(digits) - 1))
            digits[i], digits[i + 1] = digits[i + 1], digits[i]
        elif kind == "double_substitution":
            _substitute(digits, rng)
            _substitute(digits, rng)
        else:
            _substitute(digits, rng)
        candidate = "".join(digits)
        if candidate != number:
            return candidate
    raise ValueError(f"could not produce a typo for {number}")


def keypad_distance(a: str, b: str) -> float:
    """Damerau-Levenshtein distance where a neighbouring-key substitution costs 0.6, not 1.

    An adjacent transposition costs 0.8. Lower means "more likely to be a slip of the finger".
    """
    n, m = len(a), len(b)
    d = [[0.0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        d[i][0] = float(i)
    for j in range(m + 1):
        d[0][j] = float(j)
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            if a[i - 1] == b[j - 1]:
                sub = 0.0
            elif b[j - 1] in KEYPAD_NEIGHBOURS.get(a[i - 1], set()):
                sub = 0.6
            else:
                sub = 1.0
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + sub)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1] and a[i - 1] != a[i - 2]:
                d[i][j] = min(d[i][j], d[i - 2][j - 2] + 0.8)
    return d[n][m]


def changed_positions(a: str, b: str) -> list[int]:
    """Positions where two equal-length numbers differ (used to highlight digits in the UI)."""
    if len(a) != len(b):
        return []
    return [i for i, (x, y) in enumerate(zip(a, b)) if x != y]
