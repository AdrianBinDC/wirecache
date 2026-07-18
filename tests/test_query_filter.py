"""QueryFilter SQL building (no database)."""

from datetime import datetime, timezone

from wirecache.store.stories import QueryFilter


def test_default_window_is_24h():
    filt = QueryFilter()
    sql, params = filt.build_sql()
    assert "published >=" in sql
    assert len(params) == 1
    assert isinstance(params[0], datetime)


def test_single_category():
    filt = QueryFilter(categories=["ai"])
    sql, params = filt.build_sql()
    assert "%s = ANY(categories)" in sql
    assert "ai" in params


def test_multi_category_uses_overlap():
    filt = QueryFilter(categories=["ai", "tech"])
    sql, params = filt.build_sql()
    assert "categories && %s" in sql
    assert ["ai", "tech"] in params


def test_since_exclusive_of_hours():
    since = datetime(2026, 7, 1, tzinfo=timezone.utc)
    filt = QueryFilter(since=since, hours=6)  # since wins via resolve_since
    assert filt.resolve_since() == since
    meta = filt.meta()
    assert "since" in meta
    assert "hours" not in meta


def test_limit_parameterized():
    filt = QueryFilter(limit=5)
    sql, params = filt.build_sql()
    assert "LIMIT %s" in sql
    assert params[-1] == 5


def test_keyword_and_source():
    filt = QueryFilter(keyword="CUDA", source="The Verge")
    sql, params = filt.build_sql()
    assert "plainto_tsquery" in sql
    assert "source = %s" in sql
    assert "CUDA" in params
    assert "The Verge" in params
