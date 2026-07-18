"""Parallel RSS/Atom fetch."""

from __future__ import annotations

import logging
import re
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import feedparser

from wirecache.config import FETCH_TIMEOUT, MAX_SUMMARY, MAX_WORKERS, USER_AGENT

log = logging.getLogger("wirecache.fetch")

# Reject feedparser garbage like year 0001
MIN_PUBLISHED = datetime(1990, 1, 1, tzinfo=timezone.utc)


@dataclass
class FeedFailure:
    url: str
    name: str
    error: str


@dataclass
class FetchResult:
    stories: list[dict] = field(default_factory=list)
    failures: list[FeedFailure] = field(default_factory=list)

    @property
    def fetched(self) -> int:
        return len(self.stories)

    @property
    def failed(self) -> int:
        return len(self.failures)


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text or "").strip()


def normalize_published(dt: datetime | None) -> datetime | None:
    """Drop absurd timestamps some feeds emit (e.g. 0001-01-01)."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    if dt < MIN_PUBLISHED:
        return None
    # More than a day in the future is almost always bad metadata
    if dt > datetime.now(timezone.utc) + timedelta(days=1):
        return None
    return dt


def _parse_date(entry) -> datetime | None:
    for attr in ("published_parsed", "updated_parsed"):
        val = getattr(entry, attr, None)
        if val:
            try:
                return normalize_published(datetime(*val[:6], tzinfo=timezone.utc))
            except (TypeError, ValueError):
                pass
    return None


def _fetch_one(feed: dict) -> tuple[list[dict], FeedFailure | None]:
    url = feed["url"]
    name = feed["name"]
    categories = feed.get("categories", [])
    try:
        parsed = feedparser.parse(
            url,
            agent=USER_AGENT,
            request_headers={"Connection": "close"},
        )
        # feedparser rarely raises; treat bozo with no entries as soft failure
        if not parsed.entries and getattr(parsed, "bozo", False):
            exc = getattr(parsed, "bozo_exception", None)
            if exc is not None:
                return [], FeedFailure(url=url, name=name, error=f"{type(exc).__name__}: {exc}")

        stories = []
        for entry in parsed.entries:
            link = (entry.get("link") or "").strip()
            if not link:
                continue
            summary = _strip_html(entry.get("summary") or entry.get("description") or "")
            stories.append({
                "url": link,
                "title": (entry.get("title") or "").strip(),
                "summary": summary[:MAX_SUMMARY],
                "source": name,
                "categories": categories,
                "published": _parse_date(entry),
            })
        return stories, None
    except Exception as exc:
        return [], FeedFailure(url=url, name=name, error=f"{type(exc).__name__}: {exc}")


def fetch_all(feeds: list[dict], max_workers: int = MAX_WORKERS) -> FetchResult:
    """Fetch all feeds in parallel. Returns stories + per-feed failures."""
    socket.setdefaulttimeout(FETCH_TIMEOUT)
    result = FetchResult()

    if not feeds:
        log.warning("no feeds in registry; nothing to fetch")
        return result

    log.info("fetching %d feeds (workers=%d, timeout=%ss)", len(feeds), max_workers, FETCH_TIMEOUT)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_fetch_one, feed): feed for feed in feeds}
        for future in as_completed(futures):
            feed = futures[future]
            stories, failure = future.result()
            if failure:
                result.failures.append(failure)
                log.warning("feed failed name=%s url=%s error=%s", failure.name, failure.url, failure.error)
            else:
                result.stories.extend(stories)
                log.debug("feed ok name=%s stories=%d", feed.get("name"), len(stories))

    log.info(
        "fetch complete stories=%d failures=%d",
        result.fetched,
        result.failed,
    )
    return result
