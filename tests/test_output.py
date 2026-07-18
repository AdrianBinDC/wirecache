"""Output formatters."""

from wirecache.output import render

SAMPLE = {
    "query": {"categories": ["ai"], "hours": 24, "limit": 2},
    "count": 2,
    "stories": [
        {
            "title": "New GPU Ships",
            "url": "https://example.com/1",
            "source": "The Verge",
            "categories": ["ai", "tech"],
            "published": "2026-07-18T10:00:00+00:00",
            "summary": "A new accelerator is available for researchers.",
        },
        {
            "title": "Model Update",
            "url": "https://example.com/2",
            "source": "Ars Technica",
            "published": "2026-07-18T08:00:00+00:00",
            "summary": "Weights released under open license.",
        },
    ],
}


def test_json_has_stories():
    out = render(SAMPLE, "json")
    assert '"count": 2' in out
    assert "New GPU Ships" in out


def test_text_includes_url_and_header():
    out = render(SAMPLE, "text")
    assert "Count: 2" in out
    assert "https://example.com/1" in out
    assert "1. New GPU Ships" in out


def test_voice_has_no_urls_or_markdown():
    out = render(SAMPLE, "voice")
    assert "https://" not in out
    assert "**" not in out
    assert "The Verge" in out
    assert "briefing" in out
    assert "AI" in out


def test_voice_is_natural_prose_not_numbered():
    out = render(SAMPLE, "voice")
    assert "1." not in out
    assert "2." not in out
    assert "Two " not in out  # no leading story count
    assert "Six " not in out
    assert out.startswith("Here's an AI briefing")
    assert out.rstrip().endswith("That's the briefing for now.")


def test_voice_empty():
    out = render({"query": {"categories": ["ai"], "hours": 24}, "count": 0, "stories": []}, "voice")
    assert "no ai stories" in out.lower()
