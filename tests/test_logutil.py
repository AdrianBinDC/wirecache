"""Logging setup."""

import logging
from pathlib import Path

from wirecache.logutil import setup_logging


def test_setup_logging_stderr_and_file(tmp_path: Path):
    log_path = tmp_path / "test.log"
    log = setup_logging(level="DEBUG", log_file=log_path, verbose=False, quiet=False)
    log.info("hello wirecache")
    assert log_path.exists()
    text = log_path.read_text()
    assert "hello wirecache" in text
    assert "INFO" in text


def test_quiet_sets_warning_level(tmp_path: Path):
    log = setup_logging(log_file=tmp_path / "q.log", quiet=True)
    assert log.level == logging.WARNING


def test_empty_log_file_disables_file_handler(tmp_path: Path):
    log = setup_logging(log_file="", level="INFO")
    assert not any(isinstance(h, logging.FileHandler) for h in log.handlers)
