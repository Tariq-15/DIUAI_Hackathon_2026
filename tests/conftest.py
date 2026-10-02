"""Shared tiny world (scale 0.05, ~500 customers) built once per test session in a temp folder."""
from __future__ import annotations

import pytest

from src.common.config import load_config


@pytest.fixture(scope="session")
def tiny_cfg(tmp_path_factory):
    root = tmp_path_factory.mktemp("prohori")
    cfg = load_config(scale=0.05)
    for k, sub in (("data_dir", "data/generated"), ("sample_dir", "data/sample"), ("features_dir", "data/features"),
                   ("artifacts_dir", "artifacts"), ("reports_dir", "reports")):
        cfg["paths"][k] = str(root / sub)
    cfg["model"]["optuna_trials"] = 0
    return cfg


@pytest.fixture(scope="session")
def tiny_data(tiny_cfg):
    from src.datagen.generate import build, write
    out = build(tiny_cfg, verbose=False)
    write(out, tiny_cfg, sample=False)
    return out


@pytest.fixture(scope="session")
def tiny_features(tiny_cfg, tiny_data):
    from src.common.config import resolve
    from src.features.build import build
    df = build(tiny_cfg, data=tiny_data, verbose=False)
    df.to_parquet(resolve(tiny_cfg, "features_dir") / "features.parquet", index=False)
    return df


@pytest.fixture(scope="session")
def tiny_bundle(tiny_cfg, tiny_features):
    from src.models.train import train
    bundle, report = train(tiny_cfg, trials=0, verbose=False)
    return bundle, report
