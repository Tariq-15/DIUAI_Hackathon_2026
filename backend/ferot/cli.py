"""Command line: build the synthetic world, train the models, run the simulation.

    python -m ferot.cli data       # generate the synthetic ledger and cases
    python -m ferot.cli train      # train M4/M5 and write metrics
    python -m ferot.cli simulate   # queue simulation (first-come-first-served vs Ferot)
    python -m ferot.cli build      # all of the above
"""

from __future__ import annotations

import argparse
import json
import time

from ferot import config


def cmd_data() -> None:
    from ferot.datagen.complaints import attach_complaints
    from ferot.datagen.generator import build_world

    s = config.settings()
    t = time.time()
    world = build_world()
    world.cases = attach_complaints(world.cases, s.seed)
    world.save(s.data_dir)
    print(f"[data] {len(world.wallets)} wallets, {len(world.transactions)} transactions, "
          f"{len(world.cases)} cases -> {s.data_dir} ({time.time() - t:.1f}s)")


def cmd_train() -> None:
    from ferot.models.train import train_all

    t = time.time()
    metrics = train_all()
    print(json.dumps(metrics["summary"], indent=2))
    print(f"[train] done ({time.time() - t:.1f}s)")


def cmd_simulate() -> None:
    from ferot.sim.queue_sim import run_and_save

    t = time.time()
    result = run_and_save()
    print(json.dumps(result["summary"], indent=2))
    print(f"[simulate] done ({time.time() - t:.1f}s)")


def main() -> None:
    parser = argparse.ArgumentParser(prog="ferot")
    parser.add_argument("command", choices=["data", "train", "simulate", "build"])
    args = parser.parse_args()
    if args.command in ("data", "build"):
        cmd_data()
    if args.command in ("train", "build"):
        cmd_train()
    if args.command in ("simulate", "build"):
        cmd_simulate()


if __name__ == "__main__":
    main()
