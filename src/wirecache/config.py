"""Paths, env loading, and constants."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from dotenv import load_dotenv


def _resolve_root() -> Path:
    if env := os.getenv("WIRECACHE_ROOT"):
        return Path(env).resolve()

    pkg = Path(__file__).resolve().parent
    # Source layout: <root>/src/wirecache/config.py
    if pkg.parent.name == "src":
        candidate = pkg.parent.parent
        if (candidate / "pyproject.toml").exists():
            return candidate

    cwd = Path.cwd()
    if (cwd / "feeds.example.yaml").exists() or (cwd / "feeds.yaml").exists():
        return cwd

    return cwd


ROOT = _resolve_root()

FEEDS_YAML = ROOT / "feeds.yaml"
FEEDS_EXAMPLE = ROOT / "feeds.example.yaml"
ENV_PATH = ROOT / ".env"
ENV_EXAMPLE = ROOT / ".env.example"
SCHEMA_SQL = ROOT / "schema.sql"
COMPOSE_FILE = ROOT / "docker-compose.yml"
DATA_DIR = ROOT / "data"
LAST_FETCH_PATH = DATA_DIR / "last_fetch.json"

FETCH_TIMEOUT = 15
MAX_WORKERS = 20
DEFAULT_PURGE_DAYS = 30
MAX_SUMMARY = 500
HEALTH_TIMEOUT = 60
HEALTH_INTERVAL = 2
USER_AGENT = "Wirecache/1.0"


def bootstrap() -> list[str]:
    """Ensure user-local files exist. Never overwrites existing files."""
    created: list[str] = []

    if not FEEDS_YAML.exists() and FEEDS_EXAMPLE.exists():
        shutil.copy(FEEDS_EXAMPLE, FEEDS_YAML)
        created.append("feeds.yaml")

    if not ENV_PATH.exists() and ENV_EXAMPLE.exists():
        shutil.copy(ENV_EXAMPLE, ENV_PATH)
        created.append(".env")

    DATA_DIR.mkdir(exist_ok=True)

    if created:
        print(f"[INFO] created: {', '.join(created)}", file=sys.stderr)

    return created


def load_env() -> None:
    load_dotenv(ENV_PATH)


def pg_settings() -> dict:
    return {
        "dbname": os.getenv("POSTGRES_DB", "news"),
        "user": os.getenv("POSTGRES_USER", "news"),
        "password": os.getenv("POSTGRES_PASSWORD", "news"),
        "host": os.getenv("POSTGRES_HOST", "localhost"),
        "port": int(os.getenv("POSTGRES_PORT", "5432")),
    }
