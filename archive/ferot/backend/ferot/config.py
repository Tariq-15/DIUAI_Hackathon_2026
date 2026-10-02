"""Paths, settings and YAML config loading.

Settings come from environment variables (see `.env.example`). A local `.env` file at the repo
root is read if present; real environment variables always win.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(os.environ.get("FEROT_ROOT", Path(__file__).resolve().parents[2]))
CONFIG_DIR = ROOT / "config"
BACKEND_DIR = ROOT / "backend"
SOP_DIR = ROOT / "sop"


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


_load_dotenv(ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    seed: int
    customers: int
    days: int
    llm_provider: str
    anthropic_api_key: str | None
    extract_model: str
    draft_model: str
    db_path: Path
    data_dir: Path
    artifact_dir: Path
    cors_origins: list[str]


@lru_cache
def settings() -> Settings:
    key = os.environ.get("ANTHROPIC_API_KEY") or None
    if key == "your-key-here":
        key = None
    return Settings(
        seed=int(os.environ.get("FEROT_SEED", "42")),
        customers=int(os.environ.get("FEROT_CUSTOMERS", "4000")),
        days=int(os.environ.get("FEROT_DAYS", "90")),
        llm_provider=os.environ.get("FEROT_LLM_PROVIDER", "offline").lower(),
        anthropic_api_key=key,
        extract_model=os.environ.get("FEROT_LLM_EXTRACT_MODEL", "claude-opus-5-5"),
        draft_model=os.environ.get("FEROT_LLM_DRAFT_MODEL", "claude-opus-5-5"),
        db_path=Path(os.environ.get("FEROT_DB_PATH", BACKEND_DIR / "ferot.db")),
        data_dir=Path(os.environ.get("FEROT_DATA_DIR", BACKEND_DIR / "data")),
        artifact_dir=Path(os.environ.get("FEROT_ARTIFACT_DIR", BACKEND_DIR / "artifacts")),
        cors_origins=[o for o in os.environ.get("FEROT_CORS_ORIGINS", "http://localhost:5173").split(",") if o],
    )


@lru_cache
def load_yaml(name: str) -> dict:
    with open(CONFIG_DIR / name, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def limits() -> dict:
    return load_yaml("limits.yaml")


def assumptions() -> dict:
    return load_yaml("assumptions.yaml")


def policy_rules() -> dict:
    return load_yaml("policy_rules.yaml")


def holidays() -> dict:
    return load_yaml("holidays_bd.yaml")
