"""OPML import into the feed registry."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path


def parse_opml(path: Path, default_category: str = "imported") -> list[dict]:
    """
    Parse an OPML file into feed dicts: {name, url, categories}.

    Nested outline folders become category names when they have no xmlUrl.
    Leaf outlines with xmlUrl (or url) become feeds.
    """
    tree = ET.parse(path)
    root = tree.getroot()
    body = root.find("body")
    if body is None:
        return []

    feeds: list[dict] = []

    def walk(node: ET.Element, categories: list[str]) -> None:
        for outline in node.findall("outline"):
            xml_url = (outline.get("xmlUrl") or outline.get("url") or "").strip()
            title = (outline.get("text") or outline.get("title") or "").strip()

            if xml_url:
                cats = categories if categories else [default_category]
                feeds.append({
                    "name": title or xml_url,
                    "url": xml_url,
                    "categories": list(cats),
                })
            else:
                folder = title or default_category
                # Slug-ish category: lowercase, spaces to hyphens
                cat = folder.lower().replace(" ", "-")
                walk(outline, categories + [cat] if cat not in categories else categories)

    walk(body, [])
    return feeds


def import_opml(
    path: Path,
    registry,
    default_category: str = "imported",
) -> dict:
    """Parse OPML and merge into registry. Returns import result dict."""
    feeds = parse_opml(path, default_category=default_category)
    if not feeds:
        return {"status": "imported", "added": 0, "skipped": 0, "parsed": 0}
    result = registry.merge_feeds(feeds)
    result["parsed"] = len(feeds)
    return result
