"""Human-readable text output."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _relative_time(iso: str | None) -> str:
    if not iso:
        return "unknown time"
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - dt
        seconds = int(delta.total_seconds())
        if seconds < 0:
            return "just now"
        if seconds < 3600:
            mins = max(1, seconds // 60)
            return f"{mins}m ago"
        if seconds < 86400:
            hours = seconds // 3600
            return f"{hours}h ago"
        days = seconds // 86400
        return f"{days}d ago"
    except ValueError:
        return iso


def _window_label(query: dict) -> str:
    if "since" in query:
        return f"since {query['since']}"
    if "days" in query:
        return f"last {query['days']} day(s)"
    hours = query.get("hours", 24)
    return f"last {hours} hour(s)"


def render(payload: dict[str, Any]) -> str:
    query = payload.get("query") or {}
    stories = payload.get("stories") or []
    count = payload.get("count", len(stories))

    parts = [f"Filters: {_describe_filters(query)}", f"Window: {_window_label(query)}", f"Count: {count}", ""]

    if not stories:
        parts.append("No stories matched.")
        return "\n".join(parts)

    for i, s in enumerate(stories, 1):
        title = s.get("title") or "(no title)"
        source = s.get("source") or "unknown"
        when = _relative_time(s.get("published"))
        summary = (s.get("summary") or "").strip()
        if len(summary) > 200:
            summary = summary[:197] + "..."
        url = s.get("url") or ""

        parts.append(f"{i}. {title}")
        parts.append(f"   {source} · {when}")
        if summary:
            parts.append(f"   {summary}")
        if url:
            parts.append(f"   {url}")
        parts.append("")

    return "\n".join(parts).rstrip() + "\n"


def _describe_filters(query: dict) -> str:
    bits = []
    cats = query.get("categories") or query.get("category")
    if cats:
        if isinstance(cats, list):
            bits.append("categories=" + ",".join(cats))
        else:
            bits.append(f"category={cats}")
    if query.get("keyword"):
        bits.append(f"keyword={query['keyword']!r}")
    if query.get("source"):
        bits.append(f"source={query['source']!r}")
    if query.get("limit"):
        bits.append(f"limit={query['limit']}")
    return ", ".join(bits) if bits else "(none)"
