"""Package the two federated-learning results next to the models, for the analyst Model tab (/api/v1/model).

    python -m src.fl.summary        # reports/federated_*.json -> artifacts/portable/federated.json

Three results: on-device slip costs (src/fl/ondevice.py), the cross-silo fraud model (src/fl/fedgbdt.py) and the
amount habits (src/fl/amounts.py).
"""
from __future__ import annotations

import json

from src.common.config import ROOT

KEEP_CROSSSILO = ("method", "silos", "trees", "depth", "learning_rate", "bins", "export_gap", "comparison", "bands", "planted",
                  "shared_with_server", "never_shared", "limits", "seconds", "adopted")


def write() -> dict:
    rep = ROOT / "reports"
    out = {}
    f = rep / "federated_ondevice.json"
    if f.exists():
        out["ondevice"] = json.loads(f.read_text(encoding="utf-8"))
    f = rep / "federated_crosssilo.json"
    if f.exists():
        c = json.loads(f.read_text(encoding="utf-8"))
        out["crosssilo"] = {k: c[k] for k in KEEP_CROSSSILO if k in c}
    f = rep / "federated_amounts.json"
    if f.exists():
        out["amounts"] = json.loads(f.read_text(encoding="utf-8"))
    f = ROOT / "artifacts" / "portable" / "slip_costs.json"
    if f.exists():
        out["slip_costs"] = json.loads(f.read_text(encoding="utf-8"))
    dest = ROOT / "artifacts" / "portable" / "federated.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(f"[federated] summary -> {dest} ({', '.join(out) or 'nothing yet'})")
    return out


if __name__ == "__main__":
    write()
