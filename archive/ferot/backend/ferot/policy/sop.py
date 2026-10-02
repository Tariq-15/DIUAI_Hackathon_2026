"""Look up the (mock) operating-procedure sections a recommendation follows.

Sections are `## SOP-XX-NN Title` headings in `sop/*.md`. The agent sees the exact text the rule cites,
so every recommendation can be checked against the written procedure.
"""

from __future__ import annotations

import re
from functools import lru_cache

from ferot import config


@lru_cache
def sections() -> dict[str, dict]:
    out: dict[str, dict] = {}
    if not config.SOP_DIR.exists():
        return out
    for path in sorted(config.SOP_DIR.glob("SOP-*.md")):
        text = path.read_text(encoding="utf-8")
        for m in re.finditer(r"^## (SOP-[A-Z]+-\d+) (.+?)\n(.*?)(?=^## |\Z)", text, flags=re.M | re.S):
            out[m.group(1)] = {"id": m.group(1), "title": m.group(2).strip(), "text": " ".join(m.group(3).split()),
                               "source": path.name}
    return out


def cite(ids: list[str]) -> list[dict]:
    known = sections()
    return [known[i] for i in ids if i in known]
