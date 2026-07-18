"""Logging setup — stderr + optional file; stdout stays clean for CLI output."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from wirecache.config import DATA_DIR

LOG = logging.getLogger("wirecache")

_DEFAULT_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S"


def setup_logging(
    *,
    level: str | None = None,
    log_file: str | Path | None = None,
    verbose: bool = False,
    quiet: bool = False,
) -> logging.Logger:
    """
    Configure the wirecache logger once.

    Priority for level: quiet > verbose > level arg > WIRECACHE_LOG_LEVEL > INFO.
    File: log_file arg > WIRECACHE_LOG_FILE > data/wirecache.log (created if parent exists).
    """
    if quiet:
        resolved = logging.WARNING
    elif verbose:
        resolved = logging.DEBUG
    else:
        name = (level or os.getenv("WIRECACHE_LOG_LEVEL") or "INFO").upper()
        resolved = getattr(logging, name, logging.INFO)

    file_path: Path | None
    if log_file is not None:
        file_path = Path(log_file) if log_file else None
    else:
        env_file = os.getenv("WIRECACHE_LOG_FILE")
        if env_file == "":
            file_path = None
        elif env_file:
            file_path = Path(env_file)
        else:
            file_path = DATA_DIR / "wirecache.log"

    root = logging.getLogger("wirecache")
    root.handlers.clear()
    root.setLevel(resolved)
    root.propagate = False

    formatter = logging.Formatter(_DEFAULT_FORMAT, datefmt=_DATE_FORMAT)

    stderr = logging.StreamHandler(sys.stderr)
    stderr.setLevel(resolved)
    stderr.setFormatter(formatter)
    root.addHandler(stderr)

    if file_path is not None:
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            fh = logging.FileHandler(file_path, encoding="utf-8")
            fh.setLevel(resolved)
            fh.setFormatter(formatter)
            root.addHandler(fh)
        except OSError as exc:
            root.warning("could not open log file %s: %s", file_path, exc)

    return root
