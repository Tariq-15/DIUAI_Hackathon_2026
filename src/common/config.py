"""Config loading, scaling and path helpers shared by every stage."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
DAY = 86_400


def load_config(path: str | Path | None = None, scale: float | None = None,
                data_dir: str | None = None, seed: int | None = None) -> dict:
    """Load config.yaml. `scale` shrinks entity/case counts for fast test runs."""
    p = Path(path) if path else ROOT / "config.yaml"
    with open(p, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    if scale is not None and abs(scale - 1.0) > 1e-9:
        cfg = scale_config(cfg, scale)
    if data_dir:
        cfg["paths"]["data_dir"] = data_dir
    if seed is not None:
        cfg["seed"] = seed
    cfg["_scale"] = scale or 1.0
    return cfg


def scale_config(cfg: dict, s: float) -> dict:
    cfg = copy.deepcopy(cfg)
    w, pop, fr = cfg["world"], cfg["population"], cfg["fraud"]
    w["n_customers"] = max(300, int(round(w["n_customers"] * s)))
    w["n_agents"] = max(40, int(round(w["n_agents"] * s)))
    w["n_merchants"] = max(40, int(round(w["n_merchants"] * s)))
    pop["new_wallets_per_day"] = max(1, int(round(pop["new_wallets_per_day"] * s)))
    if s < 0.5:
        pop["areas_per_division"] = 2          # keep >= ~2 agents per area at tiny scale
    for key, spec in fr.items():
        if not isinstance(spec, dict):
            continue
        if "cases" in spec:
            spec["cases"] = max(3, int(round(spec["cases"] * s)))
        if "agents" in spec:
            spec["agents"] = max(3, int(round(spec["agents"] * s)))
        if "harvest_agents" in spec:
            spec["harvest_agents"] = max(2, int(round(spec["harvest_agents"] * s)))
    cfg["model"]["optuna_trials"] = min(cfg["model"]["optuna_trials"], 5)
    return cfg


def resolve(cfg: dict, key: str) -> Path:
    p = Path(cfg["paths"][key])
    p = p if p.is_absolute() else ROOT / p
    p.mkdir(parents=True, exist_ok=True)
    return p


def split_of_day(cfg: dict, day0: int) -> str:
    """day0 is 0-based; config split ranges are 1-based inclusive."""
    d = day0 + 1
    s = cfg["splits"]
    if s["train_days"][0] <= d <= s["train_days"][1]:
        return "train"
    if s["val_days"][0] <= d <= s["val_days"][1]:
        return "val"
    return "test"


def split_bounds_sec(cfg: dict) -> dict:
    """Split -> (start_sec, end_sec) relative to simulation start."""
    s = cfg["splits"]
    return {k: ((s[f"{k}_days"][0] - 1) * DAY, s[f"{k}_days"][1] * DAY) for k in ("train", "val", "test")}


def save_json(obj, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False, default=_json_default)


def _json_default(o):
    import numpy as np
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (set, tuple)):
        return list(o)
    return str(o)
