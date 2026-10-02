"""Prohori: synthetic MFS world + fraud ML pipeline."""
import sys

for _s in (sys.stdout, sys.stderr):           # Bangla reason codes on Windows consoles (cp1252)
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
