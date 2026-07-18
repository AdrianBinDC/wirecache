"""OPML parsing."""

from pathlib import Path

from wirecache.feeds.opml import parse_opml
from wirecache.feeds.registry import Registry


SAMPLE_OPML = """\
<?xml version="1.0" encoding="UTF-8"?>
<opml version="2.0">
  <head><title>Test</title></head>
  <body>
    <outline text="Tech" title="Tech">
      <outline type="rss" text="Example" title="Example"
               xmlUrl="https://example.com/feed.xml" />
    </outline>
    <outline type="rss" text="Orphan" xmlUrl="https://example.com/orphan.xml" />
  </body>
</opml>
"""


def test_parse_opml_folders_and_leaves(tmp_path: Path):
    path = tmp_path / "feeds.opml"
    path.write_text(SAMPLE_OPML)
    feeds = parse_opml(path, default_category="imported")
    assert len(feeds) == 2

    by_url = {f["url"]: f for f in feeds}
    assert by_url["https://example.com/feed.xml"]["categories"] == ["tech"]
    assert by_url["https://example.com/orphan.xml"]["categories"] == ["imported"]


def test_import_into_registry(tmp_path: Path):
    opml_path = tmp_path / "feeds.opml"
    opml_path.write_text(SAMPLE_OPML)
    reg_path = tmp_path / "feeds.yaml"
    reg_path.write_text("categories: []\nfeeds: []\n")
    registry = Registry(reg_path)

    from wirecache.feeds.opml import import_opml

    result = import_opml(opml_path, registry)
    assert result["added"] == 2
    assert registry.list_feeds()["count"] == 2
