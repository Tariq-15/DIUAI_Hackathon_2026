"""
src/datagen/config_loader.py
============================
Module 1 – Load config.yaml and expose a typed namespace.
All caps, fees, volumes and class-mix values are read from here;
nothing is hard-coded in the rest of the generator.
"""
import os
import yaml
from types import SimpleNamespace


def _as_namespace(d):
    """Recursively convert dict → SimpleNamespace for dot-access.
    Dicts whose keys are integers (e.g. kyc_caps: {1: …}) are kept as
    plain dicts (with str keys) because SimpleNamespace only takes str keys.
    """
    if isinstance(d, dict):
        # Check if any key is a non-string (e.g. int from YAML)
        if any(not isinstance(k, str) for k in d):
            # Store as plain dict with str keys, values still recursed
            return {str(k): _as_namespace(v) for k, v in d.items()}
        return SimpleNamespace(**{k: _as_namespace(v) for k, v in d.items()})
    if isinstance(d, list):
        return [_as_namespace(i) for i in d]
    return d


def load_config(path: str = None) -> SimpleNamespace:
    """Load config.yaml from *path* (defaults to repo root config.yaml)."""
    if path is None:
        # Walk up from this file's location to find config.yaml
        here = os.path.dirname(__file__)
        for _ in range(5):
            candidate = os.path.join(here, "config.yaml")
            if os.path.exists(candidate):
                path = candidate
                break
            here = os.path.dirname(here)
        else:
            raise FileNotFoundError("config.yaml not found in any parent directory.")

    with open(path, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)

    cfg = _as_namespace(raw)

    # ── Convenience derived values ──────────────────────────────────────────
    from datetime import datetime, timedelta
    cfg.sim_start_dt = datetime.strptime(cfg.sim_start, "%Y-%m-%d")
    cfg.sim_end_dt   = cfg.sim_start_dt + timedelta(days=cfg.sim_days - 1)

    # Eid window as datetime objects
    cfg.eid_start_dt = cfg.sim_start_dt + timedelta(days=cfg.eid_start_day - 1)
    cfg.eid_end_dt   = cfg.sim_start_dt + timedelta(days=cfg.eid_end_day - 1)

    return cfg


# ── Quick smoke-test ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    cfg = load_config()
    print("Config loaded OK")
    print(f"  Simulation: {cfg.sim_start} … {cfg.sim_end_dt.date()}")
    print(f"  Target rows: {cfg.target_txn_rows:,}")
    print(f"  Fraud rate : {cfg.fraud_rate:.1%}")
    print(f"  KYC-1 daily send cap: {cfg.kyc_caps['1'].daily_send_limit:,} Tk")
