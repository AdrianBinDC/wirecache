"""Registry invariants."""

from pathlib import Path

import pytest
import yaml

from wirecache.feeds.registry import Registry, RegistryError


@pytest.fixture
def registry(tmp_path: Path) -> Registry:
    path = tmp_path / "feeds.yaml"
    path.write_text(
        yaml.dump(
            {
                "categories": ["tech", "ai"],
                "feeds": [
                    {
                        "name": "Alpha",
                        "url": "https://example.com/a",
                        "categories": ["tech", "ai"],
                    },
                    {
                        "name": "Beta",
                        "url": "https://example.com/b",
                        "categories": ["tech"],
                    },
                ],
            },
            default_flow_style=False,
        )
    )
    return Registry(path)


def test_add_feed(registry: Registry):
    result = registry.add_feed("https://example.com/c", "Gamma", ["ai"])
    assert result["status"] == "added"
    assert registry.list_feeds()["count"] == 3


def test_cannot_remove_feed_that_empties_category(registry: Registry):
    with pytest.raises(RegistryError, match="would empty"):
        registry.remove_feed("https://example.com/a")  # only feed with ai


def test_remove_feed_ok_when_category_shared(registry: Registry):
    registry.add_feed("https://example.com/c", "Gamma", ["ai"])
    result = registry.remove_feed("https://example.com/a")
    assert result["status"] == "removed"


def test_cannot_remove_last_category_from_feed(registry: Registry):
    with pytest.raises(RegistryError, match="last category"):
        registry.remove_category_from_feed("https://example.com/b", "tech")


def test_merge_skips_duplicates(registry: Registry):
    result = registry.merge_feeds(
        [
            {"name": "Alpha", "url": "https://example.com/a", "categories": ["tech"]},
            {"name": "New", "url": "https://example.com/new", "categories": ["ai"]},
        ]
    )
    assert result["added"] == 1
    assert result["skipped"] == 1
