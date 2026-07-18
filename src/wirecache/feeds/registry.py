"""YAML feed registry with category invariants."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from wirecache.config import FEEDS_YAML


class RegistryError(Exception):
    """User-facing registry mutation error."""

    def __init__(self, message: str, tip: str | None = None):
        super().__init__(message)
        self.message = message
        self.tip = tip

    def as_dict(self) -> dict:
        d: dict[str, Any] = {"error": self.message}
        if self.tip:
            d["tip"] = self.tip
        return d


def category_usage(feeds: list[dict], exclude_url: str | None = None) -> dict[str, list[str]]:
    """Return {category: [feed_name, ...]}, optionally excluding one URL."""
    usage: dict[str, list[str]] = {}
    for feed in feeds:
        if exclude_url and feed["url"] == exclude_url:
            continue
        for cat in feed.get("categories", []):
            usage.setdefault(cat, []).append(feed["name"])
    return usage


class Registry:
    """Load/save feeds.yaml and enforce non-empty category invariants."""

    def __init__(self, path: Path | None = None):
        self.path = path or FEEDS_YAML

    def load(self) -> dict:
        if not self.path.exists():
            return {"categories": [], "feeds": []}
        with open(self.path) as f:
            return yaml.safe_load(f) or {"categories": [], "feeds": []}

    def save(self, data: dict) -> None:
        with open(self.path, "w") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    def list_feeds(self, category: str | None = None) -> dict:
        data = self.load()
        feeds = data.get("feeds", [])
        if category:
            feeds = [f for f in feeds if category in f.get("categories", [])]
        return {
            "categories": data.get("categories", []),
            "count": len(feeds),
            "feeds": feeds,
        }

    def add_feed(self, url: str, name: str, categories: list[str]) -> dict:
        data = self.load()
        feeds = data.get("feeds", [])

        if any(f["url"] == url for f in feeds):
            raise RegistryError(f"Feed already exists: {url}")

        if not categories:
            raise RegistryError("At least one category is required.")

        known = data.get("categories", [])
        new_cats = [c for c in categories if c not in known]
        if new_cats:
            data["categories"] = known + new_cats

        feeds.append({"name": name, "url": url, "categories": categories})
        data["feeds"] = feeds
        self.save(data)
        return {"status": "added", "name": name, "url": url, "categories": categories}

    def remove_feed(self, url: str) -> dict:
        data = self.load()
        feeds = data.get("feeds", [])

        target = next((f for f in feeds if f["url"] == url), None)
        if not target:
            raise RegistryError(f"Feed not found: {url}")

        remaining = [f for f in feeds if f["url"] != url]
        usage_after = category_usage(remaining)
        would_empty = [c for c in target.get("categories", []) if c not in usage_after]

        if would_empty:
            raise RegistryError(
                f"Cannot remove — would empty categories: {would_empty}",
                tip="Assign these categories to another feed first.",
            )

        data["feeds"] = remaining
        self.save(data)
        return {"status": "removed", "url": url}

    def update_feed(
        self,
        url: str,
        name: str | None = None,
        new_url: str | None = None,
    ) -> dict:
        data = self.load()
        feeds = data.get("feeds", [])

        feed = next((f for f in feeds if f["url"] == url), None)
        if not feed:
            raise RegistryError(f"Feed not found: {url}")

        if name:
            feed["name"] = name

        if new_url:
            if any(f["url"] == new_url for f in feeds if f["url"] != url):
                raise RegistryError(f"URL already exists: {new_url}")
            feed["url"] = new_url

        self.save(data)
        return {"status": "updated", "feed": feed}

    def add_category_to_feed(self, url: str, category: str) -> dict:
        data = self.load()
        feeds = data.get("feeds", [])

        feed = next((f for f in feeds if f["url"] == url), None)
        if not feed:
            raise RegistryError(f"Feed not found: {url}")

        known = data.get("categories", [])
        if category not in known:
            data["categories"] = known + [category]

        if category not in feed.get("categories", []):
            feed.setdefault("categories", []).append(category)

        self.save(data)
        return {"status": "category added", "feed": feed["name"], "category": category}

    def remove_category_from_feed(self, url: str, category: str) -> dict:
        data = self.load()
        feeds = data.get("feeds", [])

        feed = next((f for f in feeds if f["url"] == url), None)
        if not feed:
            raise RegistryError(f"Feed not found: {url}")

        if category not in feed.get("categories", []):
            raise RegistryError(f"Feed does not have category: {category}")

        if len(feed["categories"]) == 1:
            raise RegistryError("Cannot remove the last category from a feed. Add another first.")

        others = [
            f["name"]
            for f in feeds
            if f["url"] != url and category in f.get("categories", [])
        ]
        if not others:
            raise RegistryError(
                f"Cannot remove — would empty category '{category}'.",
                tip="Add another feed to this category first.",
            )

        feed["categories"].remove(category)
        self.save(data)
        return {"status": "category removed", "feed": feed["name"], "category": category}

    def add_category_def(self, name: str) -> dict:
        data = self.load()
        if name in data.get("categories", []):
            raise RegistryError(f"Category already exists: {name}")
        data.setdefault("categories", []).append(name)
        self.save(data)
        return {"status": "category created", "category": name}

    def remove_category_def(self, name: str) -> dict:
        data = self.load()
        if name not in data.get("categories", []):
            raise RegistryError(f"Category not found: {name}")

        in_use = [f["name"] for f in data.get("feeds", []) if name in f.get("categories", [])]
        if in_use:
            raise RegistryError(
                f"Category '{name}' is still used by: {in_use}",
                tip="Remove this category from all feeds before deleting it.",
            )

        data["categories"].remove(name)
        self.save(data)
        return {"status": "category removed", "category": name}

    def merge_feeds(self, feeds: list[dict], ensure_categories: bool = True) -> dict:
        """Add feeds that are not already present by URL. Returns import stats."""
        data = self.load()
        existing_urls = {f["url"] for f in data.get("feeds", [])}
        added = 0
        skipped = 0
        known = list(data.get("categories", []))

        for feed in feeds:
            if feed["url"] in existing_urls:
                skipped += 1
                continue
            cats = feed.get("categories") or []
            if ensure_categories:
                for c in cats:
                    if c not in known:
                        known.append(c)
            data.setdefault("feeds", []).append(feed)
            existing_urls.add(feed["url"])
            added += 1

        data["categories"] = known
        self.save(data)
        return {"status": "imported", "added": added, "skipped": skipped}
