"""Render query (and related) results for json / text / voice."""

from __future__ import annotations

from typing import Any

from wirecache.output import json_fmt, text_fmt, voice_fmt

FORMATS = ("json", "text", "voice")


def render(payload: dict[str, Any], fmt: str = "json") -> str:
    """Render a query payload: {query, count, stories}."""
    if fmt == "json":
        return json_fmt.render(payload)
    if fmt == "text":
        return text_fmt.render(payload)
    if fmt == "voice":
        return voice_fmt.render(payload)
    raise ValueError(f"Unknown format: {fmt}")
