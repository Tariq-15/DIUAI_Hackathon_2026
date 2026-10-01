"""Repository-level rules that protect upay and its customers."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CODE_DIRS = [ROOT / "backend" / "ferot", ROOT / "web" / "src"]


def _code_files():
    for d in CODE_DIRS:
        if d.exists():
            yield from (p for p in d.rglob("*") if p.suffix in {".py", ".ts", ".tsx", ".js"})


def test_no_upay_endpoints():
    """R15: the prototype never calls, scrapes or frames upay's site or APIs."""
    for path in _code_files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        assert not re.search(r"upaybd\.com|api\.upaybd", text), path


def test_no_secrets_committed():
    """R18: no API keys in the code."""
    for path in _code_files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        assert not re.search(r"sk-ant-[A-Za-z0-9_-]{20,}", text), path


def test_no_real_operator_prefixes_in_demo_data():
    """R16: demo numbers use the 010 prefix, never 013-019."""
    for path in (ROOT / "backend" / "ferot" / "datagen").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"\b01[3-9]\d{8}\b", text), path
