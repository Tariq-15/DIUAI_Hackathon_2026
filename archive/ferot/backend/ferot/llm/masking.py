"""Mask personal data before any text leaves Ferot for an LLM (rules R9, R10).

Phone numbers become <PHONE_1>, <PHONE_2>, ... and TrxIDs become <TRX_1>, ... The mapping stays in
memory on our side and is used to restore values in the model's answer.
"""

from __future__ import annotations

import re

BN_TO_ASCII = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")
PHONE_RE = re.compile(r"(?<!\d)(?:\+?88[\s-]?)?(01\d(?:[\s-]?\d){8})(?!\d)")
TRX_RE = re.compile(r"\bTX[0-9A-F]{8}\b", re.IGNORECASE)


def to_ascii_digits(text: str) -> str:
    return text.translate(BN_TO_ASCII)


def mask_pii(text: str) -> tuple[str, dict[str, str]]:
    text = to_ascii_digits(text)
    mapping: dict[str, str] = {}
    reverse: dict[str, str] = {}

    def _sub(prefix: str, value: str) -> str:
        if value in reverse:
            return reverse[value]
        token = f"<{prefix}_{sum(1 for k in mapping if k.startswith('<' + prefix)) + 1}>"
        mapping[token] = value
        reverse[value] = token
        return token

    text = PHONE_RE.sub(lambda m: _sub("PHONE", re.sub(r"[\s-]", "", m.group(1))), text)
    text = TRX_RE.sub(lambda m: _sub("TRX", m.group(0).upper()), text)
    return text, mapping


def unmask(value, mapping: dict[str, str]):
    """Restore masked tokens inside a string, list or dict returned by the model."""
    if isinstance(value, str):
        for token, original in mapping.items():
            value = value.replace(token, original)
        return value
    if isinstance(value, list):
        return [unmask(v, mapping) for v in value]
    if isinstance(value, dict):
        return {k: unmask(v, mapping) for k, v in value.items()}
    return value
