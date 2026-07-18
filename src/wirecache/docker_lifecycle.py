"""Docker Compose PostgreSQL lifecycle."""

from __future__ import annotations

import json
import logging
import subprocess
import sys
import time

from wirecache.config import HEALTH_INTERVAL, HEALTH_TIMEOUT, ROOT

log = logging.getLogger("wirecache.docker")


def _compose(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["docker", "compose", *cmd],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


def start() -> dict:
    """Bring up PostgreSQL and wait until healthy."""
    log.info("starting PostgreSQL via docker compose")
    result = _compose(["up", "-d"])
    if result.returncode != 0:
        log.error("docker compose up failed:\n%s", result.stderr)
        sys.exit(1)

    log.info("waiting for PostgreSQL to become healthy (timeout=%ss)", HEALTH_TIMEOUT)
    deadline = time.time() + HEALTH_TIMEOUT
    while time.time() < deadline:
        check = _compose(["ps", "--format", "json"])
        if check.returncode == 0 and check.stdout.strip():
            try:
                for line in check.stdout.strip().splitlines():
                    svc = json.loads(line)
                    name = (svc.get("Name") or "").lower()
                    service = (svc.get("Service") or "").lower()
                    if "postgres" in name or "postgres" in service:
                        if svc.get("Health") == "healthy":
                            log.info("PostgreSQL is healthy")
                            return {"status": "started", "postgres": "healthy"}
            except (json.JSONDecodeError, KeyError):
                pass
        time.sleep(HEALTH_INTERVAL)

    log.error("timed out waiting for PostgreSQL to become healthy")
    sys.exit(1)


def stop() -> dict:
    log.info("stopping PostgreSQL")
    result = _compose(["down"])
    if result.returncode != 0:
        log.error("docker compose down failed:\n%s", result.stderr)
        sys.exit(1)
    return {"status": "stopped"}


def ensure_ready(store) -> None:
    """Auto-start Postgres and init schema if needed."""
    if not store.is_reachable():
        log.info("PostgreSQL not reachable; starting")
        start()
    if not store.schema_ready():
        log.info("schema missing; initializing")
        store.init_schema()
        log.info("schema initialized")
