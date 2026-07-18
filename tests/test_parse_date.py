"""Published-date normalization."""

from datetime import datetime, timezone

from wirecache.fetch.rss import normalize_published


def test_rejects_year_one():
    assert normalize_published(datetime(1, 1, 1, tzinfo=timezone.utc)) is None


def test_keeps_normal_date():
    dt = datetime(2026, 7, 18, 12, 0, tzinfo=timezone.utc)
    assert normalize_published(dt) == dt


def test_naive_gets_utc():
    dt = normalize_published(datetime(2024, 1, 1, 0, 0, 0))
    assert dt is not None
    assert dt.tzinfo is not None
