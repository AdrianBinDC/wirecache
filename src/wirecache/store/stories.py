"""PostgreSQL story store: insert, query, purge, stats."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

import psycopg2
import psycopg2.extras

from wirecache.config import SCHEMA_SQL, DEFAULT_PURGE_DAYS, pg_settings
from wirecache.fetch.rss import MIN_PUBLISHED

log = logging.getLogger("wirecache.store")


@dataclass
class QueryFilter:
    """Filters for story queries. Time: use since, or hours/days (default 24h)."""

    categories: list[str] = field(default_factory=list)
    keyword: str | None = None
    source: str | None = None
    since: datetime | None = None
    hours: int | None = None
    days: int | None = None
    limit: int | None = None

    def resolve_since(self) -> datetime:
        if self.since is not None:
            return self.since if self.since.tzinfo else self.since.replace(tzinfo=timezone.utc)
        if self.hours is not None:
            return datetime.now(timezone.utc) - timedelta(hours=self.hours)
        if self.days is not None:
            return datetime.now(timezone.utc) - timedelta(days=self.days)
        return datetime.now(timezone.utc) - timedelta(hours=24)

    def meta(self) -> dict[str, Any]:
        """Query metadata for output (omit unset fields)."""
        m: dict[str, Any] = {}
        if self.categories:
            m["categories"] = self.categories
        if self.keyword:
            m["keyword"] = self.keyword
        if self.source:
            m["source"] = self.source
        if self.since is not None:
            m["since"] = self.resolve_since().isoformat()
        elif self.days is not None:
            m["days"] = self.days
        elif self.hours is not None:
            m["hours"] = self.hours
        else:
            m["hours"] = 24
        if self.limit is not None:
            m["limit"] = self.limit
        return m

    def build_sql(self) -> tuple[str, list[Any]]:
        """Return (sql, params) for the filtered story query."""
        since = self.resolve_since()
        conditions = ["published >= %s"]
        params: list[Any] = [since]

        if self.categories:
            if len(self.categories) == 1:
                conditions.append("%s = ANY(categories)")
                params.append(self.categories[0])
            else:
                conditions.append("categories && %s")
                params.append(self.categories)

        if self.keyword:
            conditions.append("search_vector @@ plainto_tsquery('english', %s)")
            params.append(self.keyword)

        if self.source:
            conditions.append("source = %s")
            params.append(self.source)

        where = " AND ".join(conditions)
        sql = f"""
            SELECT url, title, summary, source, categories, published
            FROM   stories
            WHERE  {where}
            ORDER  BY published DESC NULLS LAST
        """
        if self.limit is not None:
            sql += " LIMIT %s"
            params.append(self.limit)

        return sql, params


class StoryStore:
    def connect(self):
        return psycopg2.connect(**pg_settings())

    def is_reachable(self) -> bool:
        try:
            conn = self.connect()
            conn.close()
            return True
        except Exception:
            return False

    def init_schema(self) -> None:
        schema = SCHEMA_SQL.read_text()
        conn = self.connect()
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(schema)
        finally:
            conn.close()

    def schema_ready(self) -> bool:
        try:
            conn = self.connect()
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1 FROM stories LIMIT 0")
                return True
            finally:
                conn.close()
        except Exception:
            return False

    def insert_many(self, stories: list[dict]) -> int:
        """Insert stories; skip duplicate URLs. Returns inserted count."""
        if not stories:
            return 0

        inserted = 0
        errors = 0
        conn = self.connect()
        try:
            with conn:
                with conn.cursor() as cur:
                    for story in stories:
                        try:
                            cur.execute(
                                """
                                INSERT INTO stories
                                    (url, title, summary, source, categories, published)
                                VALUES (%s, %s, %s, %s, %s, %s)
                                ON CONFLICT (url) DO NOTHING
                                """,
                                (
                                    story["url"],
                                    story["title"],
                                    story["summary"],
                                    story["source"],
                                    story["categories"],
                                    story["published"],
                                ),
                            )
                            if cur.rowcount:
                                inserted += 1
                        except Exception as exc:
                            errors += 1
                            log.warning("insert failed url=%s error=%s", story.get("url"), exc)
        finally:
            conn.close()
        log.info("inserted %d of %d stories (%d insert errors)", inserted, len(stories), errors)
        return inserted

    def query(self, filt: QueryFilter) -> list[dict]:
        sql, params = filt.build_sql()
        log.debug("query meta=%s", filt.meta())
        conn = self.connect()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()
        finally:
            conn.close()
        log.info("query returned %d stories", len(rows))

        stories = []
        for row in rows:
            item = {
                "title": row["title"],
                "url": row["url"],
                "source": row["source"],
                "categories": row["categories"],
                "published": row["published"].isoformat() if row["published"] else None,
                "summary": row["summary"],
            }
            stories.append({k: v for k, v in item.items() if v is not None})
        return stories

    def purge(self, days: int = DEFAULT_PURGE_DAYS) -> dict:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        conn = self.connect()
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM stories WHERE fetched_at < %s", (cutoff,))
                    deleted = cur.rowcount
        finally:
            conn.close()
        log.info("purged %d stories older than %d days (cutoff=%s)", deleted, days, cutoff.isoformat())
        return {"purged": deleted, "cutoff": cutoff.isoformat(), "days": days}

    def stats(self) -> dict:
        conn = self.connect()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT
                        COUNT(*) AS story_count,
                        MIN(published) FILTER (WHERE published >= %s)
                            AS oldest_published,
                        MAX(published) FILTER (WHERE published >= %s)
                            AS newest_published,
                        MAX(fetched_at) AS last_fetched_at
                    FROM stories
                    """,
                    (MIN_PUBLISHED, MIN_PUBLISHED),
                )
                row = cur.fetchone() or {}
        finally:
            conn.close()

        def iso(v):
            return v.isoformat() if v is not None else None

        return {
            "story_count": row.get("story_count", 0),
            "oldest_published": iso(row.get("oldest_published")),
            "newest_published": iso(row.get("newest_published")),
            "last_fetched_at": iso(row.get("last_fetched_at")),
        }
