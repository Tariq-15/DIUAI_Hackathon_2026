"""Run the whole thing end to end.

    python -m src.pipeline                      # full: generate -> validate -> features -> train -> agents -> evaluate -> export -> demo
    python -m src.pipeline --scale 0.1 --trials 0 --out-root runs/small     # quick smoke run in its own folder
    python -m src.pipeline --from train         # resume from a stage
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from src.common.config import load_config

STAGES = ["generate", "validate", "features", "train", "agents", "evaluate", "export", "demo"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=None)
    ap.add_argument("--scale", type=float, default=None)
    ap.add_argument("--trials", type=int, default=None, help="Optuna trials (default from config)")
    ap.add_argument("--from", dest="start", default="generate", choices=STAGES)
    ap.add_argument("--to", dest="stop", default="demo", choices=STAGES)
    ap.add_argument("--out-root", default=None, help="write data/artifacts/reports under this folder instead")
    ap.add_argument("--skip-repro", action="store_true", help="skip validation T14")
    ap.add_argument("--no-ablation", action="store_true")
    a = ap.parse_args()
    cfg = load_config(a.config, scale=a.scale)
    if a.out_root:
        root = Path(a.out_root)
        for k, sub in (("data_dir", "data/generated"), ("sample_dir", "data/sample"), ("features_dir", "data/features"),
                       ("artifacts_dir", "artifacts"), ("reports_dir", "reports")):
            cfg["paths"][k] = str(root / sub)
    todo = STAGES[STAGES.index(a.start): STAGES.index(a.stop) + 1]
    t0 = time.time()
    for st in todo:
        ts = time.time()
        print(f"\n===== {st} =====", flush=True)
        if st == "generate":
            from src.datagen.generate import build, write
            out = build(cfg)
            write(out, cfg)
        elif st == "validate":
            from src.datagen.generate import load
            from src.validation.checks import Checker
            from src.validation.run_checks import to_markdown
            from src.common.config import resolve, save_json
            res = Checker(load(cfg), cfg).run(skip_repro=a.skip_repro, cfg_path=a.config)
            rep = resolve(cfg, "reports_dir")
            save_json(res, rep / "data_validation.json")
            (rep / "data_validation.md").write_text(to_markdown(res), encoding="utf-8")
            for r in res:
                print(f"{r['id']:>4} {'PASS' if r['passed'] else 'FAIL'}  {r['name']}")
            if not all(r["passed"] for r in res):
                print("validation failed: fix the generator before training", file=sys.stderr)
                sys.exit(1)
        elif st == "features":
            from src.features.build import build as fbuild
            from src.features.spec import ALL_FEATURES, FEATURE_GROUPS
            from src.common.config import resolve, save_json
            df = fbuild(cfg)
            d = resolve(cfg, "features_dir")
            df.to_parquet(d / "features.parquet", index=False)
            save_json(dict(groups=FEATURE_GROUPS, all_features=ALL_FEATURES), d / "feature_spec.json")
        elif st == "train":
            from src.models.train import train
            train(cfg, trials=a.trials)
        elif st == "agents":
            from src.agents.agent_watch import run
            run(cfg)
        elif st == "evaluate":
            from src.models.evaluate import evaluate
            evaluate(cfg, ablate=not a.no_ablation)
        elif st == "export":
            from src.serve.export_state import export
            export(cfg)
        elif st == "demo":                              # product layer: alerts, networks, personas for the UI
            from src.serve.demo_world import build as build_world
            build_world(cfg)
        print(f"----- {st} done in {time.time() - ts:.0f}s", flush=True)
    print(f"\nall stages done in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
