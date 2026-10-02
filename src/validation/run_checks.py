"""Run data validation T1-T14 on the generated dataset.

    python -m src.validation.run_checks                # full data in data/generated
    python -m src.validation.run_checks --skip-repro   # skip T14 (re-generates a tiny world twice)

Writes reports/data_validation.{json,md}; exits 1 if any check fails.
"""
from __future__ import annotations

import argparse
import json
import sys

from src.common.config import load_config, resolve, save_json
from src.datagen.generate import load
from .checks import Checker


def to_markdown(res: list[dict]) -> str:
    lines = ["# Data validation (T1-T14)", "", "| Test | Check | Result | Key numbers |", "|---|---|---|---|"]
    for r in res:
        d = r["details"]
        brief = json.dumps({k: v for k, v in d.items() if not isinstance(v, (dict, list)) or len(str(v)) < 90},
                           ensure_ascii=False, default=str)
        if len(brief) > 260:
            brief = brief[:257] + "..."
        lines.append(f"| {r['id']} | {r['name']} | {'PASS' if r['passed'] else '**FAIL**'} | `{brief}` |")
    lines += ["", "Full details: `reports/data_validation.json`."]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=None)
    ap.add_argument("--data", default=None, help="override paths.data_dir")
    ap.add_argument("--skip-repro", action="store_true")
    a = ap.parse_args()
    cfg = load_config(a.config, data_dir=a.data)
    data = load(cfg)
    if a.data:                                     # a scaled dataset: read its own scale from the report
        scale = data["report"].get("scale", 1.0)
        cfg = load_config(a.config, scale=scale, data_dir=a.data)
    res = Checker(data, cfg).run(skip_repro=a.skip_repro, cfg_path=a.config)
    rep = resolve(cfg, "reports_dir")
    save_json(res, rep / "data_validation.json")
    (rep / "data_validation.md").write_text(to_markdown(res), encoding="utf-8")
    for r in res:
        print(f"{r['id']:>4} {'PASS' if r['passed'] else 'FAIL'}  {r['name']}")
        if not r["passed"]:
            print("      ", json.dumps(r["details"], default=str)[:600])
    n_fail = sum(not r["passed"] for r in res)
    print(f"\n{len(res) - n_fail}/{len(res)} checks passed -> {rep / 'data_validation.md'}")
    sys.exit(1 if n_fail else 0)


if __name__ == "__main__":
    main()
