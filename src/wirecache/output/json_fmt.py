"""JSON output (default agent contract)."""

from __future__ import annotations

import json
from typing import Any


def render(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, default=str)
