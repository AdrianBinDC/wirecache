#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "feedparser",
#   "psycopg2-binary",
#   "pyyaml",
#   "python-dotenv",
# ]
# ///
"""
news.py — RSS news aggregator skill for Hermes

Subcommands:
  start               Start PostgreSQL via docker-compose, wait until healthy
  stop                Stop PostgreSQL via docker-compose
  init                Initialize database schema (run once after start)
  fetch               Pull all feeds into PostgreSQL
  query               Filter stories, return JSON to stdout
  purge               Delete stories older than 30 days

  add-feed            Add a feed to feeds.yaml
  remove-feed         Remove a feed from feeds.yaml
  update-feed         Update a feed name or URL
  add-category        Add a category to an existing feed
  remove-category     Remove a category from a feed
  list-feeds          List all feeds (optionally filtered by category)

  add-category-def    Create a new category definition
  remove-category-def Remove a category definition (blocked if feeds use it)
"""

import argparse
import json
import os
import re
import socket
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path

import feedparser
import psycopg2
import psycopg2.extras
import yaml
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Paths & config
# ---------------------------------------------------------------------------

SKILL_DIR  = Path(__file__).parent
FEEDS_YAML = SKILL_DIR / "feeds.yaml"

FETCH_TIMEOUT = 15      # seconds per feed
MAX_WORKERS   = 20      # parallel feed fetches
PURGE_DAYS    = 30      # stories older than this are deleted
MAX_SUMMARY   = 2000    # max summary chars stored

# ---------------------------------------------------------------------------
# Embedded companion files — written to skill directory on first run
# ---------------------------------------------------------------------------

_DOCKER_COMPOSE = """\
services:
  postgres:
    image: postgres:16
    container_name: news_db
    environment:
      POSTGRES_DB:       ${POSTGRES_DB:-news}
      POSTGRES_USER:     ${POSTGRES_USER:-news}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-news}
    ports:
      - "${POSTGRES_PORT:-5432}:5432"
    volumes:
      - news_db_data:/var/lib/postgresql/data
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-news} -d ${POSTGRES_DB:-news}"]
      interval: 10s
      timeout: 5s
      retries: 5

volumes:
  news_db_data:
    driver: local
"""

_SCHEMA_SQL = """\
-- News skill schema
-- Run once via: uv run news.py init

CREATE TABLE IF NOT EXISTS stories (
    id            SERIAL          PRIMARY KEY,
    url           TEXT            UNIQUE NOT NULL,
    title         TEXT,
    summary       TEXT,
    source        TEXT,
    categories    TEXT[],
    published     TIMESTAMPTZ,
    fetched_at    TIMESTAMPTZ     DEFAULT NOW(),

    -- Full-text search vector: auto-maintained from title + summary
    search_vector TSVECTOR        GENERATED ALWAYS AS (
        to_tsvector(
            'english',
            coalesce(title,   '') || ' ' ||
            coalesce(summary, '')
        )
    ) STORED
);

-- Full-text search
CREATE INDEX IF NOT EXISTS stories_search_idx
    ON stories USING GIN (search_vector);

-- Time-range queries
CREATE INDEX IF NOT EXISTS stories_published_idx
    ON stories (published DESC);

-- Category filtering (array containment)
CREATE INDEX IF NOT EXISTS stories_categories_idx
    ON stories USING GIN (categories);

-- Fetch timestamp for purge
CREATE INDEX IF NOT EXISTS stories_fetched_idx
    ON stories (fetched_at);
"""

_ENV_EXAMPLE = """\
# Copy this file to .env and adjust as needed
# These defaults match docker-compose.yml

POSTGRES_DB=news
POSTGRES_USER=news
POSTGRES_PASSWORD=news
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
"""

_FEEDS_YAML = """\
categories:
  - us-news
  - tech
  - mac
  - ai
  - world-news
  - us-politics
  - world-politics

feeds:
  # US News
  - name: AP Top News
    url: https://feeds.apnews.com/rss/apf-topnews
    categories: [us-news, world-news]

  - name: NPR News
    url: https://feeds.npr.org/1001/rss.xml
    categories: [us-news]

  - name: Reuters Top News
    url: https://feeds.reuters.com/reuters/topNews
    categories: [us-news, world-news]

  # Tech
  - name: Ars Technica
    url: https://feeds.arstechnica.com/arstechnica/index
    categories: [tech, ai]

  - name: The Verge
    url: https://www.theverge.com/rss/index.xml
    categories: [tech, mac]

  - name: Wired
    url: https://www.wired.com/feed/rss
    categories: [tech, ai]

  - name: TechCrunch
    url: https://techcrunch.com/feed/
    categories: [tech, ai]

  - name: Hacker News (Top)
    url: https://hnrss.org/frontpage
    categories: [tech, ai]

  # Mac
  - name: MacRumors
    url: https://feeds.macrumors.com/MacRumors-All
    categories: [mac]

  - name: 9to5Mac
    url: https://9to5mac.com/feed/
    categories: [mac, tech]

  - name: Daring Fireball
    url: https://daringfireball.net/feeds/main
    categories: [mac, tech]

  # AI
  - name: MIT Technology Review
    url: https://www.technologyreview.com/feed/
    categories: [ai, tech]

  - name: VentureBeat AI
    url: https://venturebeat.com/ai/feed/
    categories: [ai, tech]

  - name: The Gradient
    url: https://thegradient.pub/rss/
    categories: [ai]

  # World News
  - name: BBC World News
    url: https://feeds.bbci.co.uk/news/world/rss.xml
    categories: [world-news]

  - name: Al Jazeera
    url: https://www.aljazeera.com/xml/rss/all.xml
    categories: [world-news, world-politics]

  - name: The Guardian World
    url: https://www.theguardian.com/world/rss
    categories: [world-news, world-politics]

  # US Politics
  - name: Politico
    url: https://rss.politico.com/politics-news.xml
    categories: [us-politics]

  - name: The Hill
    url: https://thehill.com/rss/syndicator/19109
    categories: [us-politics, us-news]

  - name: Roll Call
    url: https://rollcall.com/feed/
    categories: [us-politics]

  # World Politics
  - name: Foreign Policy
    url: https://foreignpolicy.com/feed/
    categories: [world-politics, world-news]

  - name: The Economist
    url: https://www.economist.com/international/rss.xml
    categories: [world-politics, world-news]
"""

def _bootstrap_files():
    """Write companion files to the skill directory if they don't exist yet."""
    files = {
        "docker-compose.yml": _DOCKER_COMPOSE,
        "schema.sql":         _SCHEMA_SQL,
        ".env.example":       _ENV_EXAMPLE,
        "feeds.yaml":         _FEEDS_YAML,
    }
    created = []
    for filename, content in files.items():
        path = SKILL_DIR / filename
        if not path.exists():
            path.write_text(content)
            created.append(filename)

    # Create .env from .env.example if neither exists
    env_path = SKILL_DIR / ".env"
    if not env_path.exists():
        env_path.write_text(_ENV_EXAMPLE)
        created.append(".env")

    if created:
        print(f"[INFO] created: {', '.join(created)}", file=sys.stderr)


def _info(msg: str, data: dict | None = None):
    """Print status JSON to stderr (never stdout)."""
    if data:
        print(json.dumps(data), file=sys.stderr)
    else:
        print(f"[INFO] {msg}", file=sys.stderr)


def _omit_none(d: dict) -> dict:
    """Remove None values from a dict."""
    return {k: v for k, v in d.items() if v is not None}



HEALTH_TIMEOUT = 60     # max seconds to wait for postgres healthy
HEALTH_INTERVAL = 2     # seconds between health checks

def _compose(cmd, *args):
    """Run a docker-compose command in the skill directory."""
    result = subprocess.run(
        ["docker", "compose", *cmd, *args],
        cwd=SKILL_DIR,
        capture_output=True,
        text=True,
    )
    return result

def cmd_start(args):
    """Bring up PostgreSQL and wait until it is healthy."""
    result = _compose(["up", "-d"])
    if result.returncode != 0:
        print(f"[ERROR] docker compose up failed:\n{result.stderr}", file=sys.stderr)
        sys.exit(1)

    _info("waiting for PostgreSQL to be healthy...")
    deadline = time.time() + HEALTH_TIMEOUT
    while time.time() < deadline:
        check = _compose(["ps", "--format", "json"])
        if check.returncode == 0 and check.stdout.strip():
            try:
                # docker compose ps --format json returns one JSON object per line
                for line in check.stdout.strip().splitlines():
                    svc = json.loads(line)
                    if "postgres" in svc.get("Name", "").lower() or \
                       "postgres" in svc.get("Service", "").lower():
                        health = svc.get("Health", "")
                        if health == "healthy":
                            _info("PostgreSQL is healthy", {"status": "started", "postgres": "healthy"})
                            return
                        elif health in ("unhealthy", ""):
                            pass  # still waiting
            except (json.JSONDecodeError, KeyError):
                pass
        time.sleep(HEALTH_INTERVAL)

    print("[ERROR] timed out waiting for PostgreSQL to become healthy", file=sys.stderr)
    sys.exit(1)

def cmd_stop(args):
    """Stop PostgreSQL (data is preserved in the named volume)."""
    result = _compose(["down"])
    if result.returncode != 0:
        print(f"[ERROR] docker compose down failed:\n{result.stderr}", file=sys.stderr)
        sys.exit(1)
    _info(None, {"status": "stopped"})

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

def get_conn():
    """Return a new psycopg2 connection using .env credentials."""
    return psycopg2.connect(
        dbname   = os.getenv("POSTGRES_DB",       "news"),
        user     = os.getenv("POSTGRES_USER",     "news"),
        password = os.getenv("POSTGRES_PASSWORD", "news"),
        host     = os.getenv("POSTGRES_HOST",     "localhost"),
        port     = int(os.getenv("POSTGRES_PORT", 5432)),
    )

# ---------------------------------------------------------------------------
# YAML helpers
# ---------------------------------------------------------------------------

def load_feeds():
    with open(FEEDS_YAML) as f:
        return yaml.safe_load(f) or {"categories": [], "feeds": []}

def save_feeds(data):
    with open(FEEDS_YAML, "w") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

def category_usage(feeds, exclude_url=None):
    """Return {category: [feed_name, ...]} for feeds, optionally excluding one URL."""
    usage = {}
    for feed in feeds:
        if exclude_url and feed["url"] == exclude_url:
            continue
        for cat in feed.get("categories", []):
            usage.setdefault(cat, []).append(feed["name"])
    return usage

# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------

def cmd_init(args):
    schema = (SKILL_DIR / "schema.sql").read_text()
    conn = get_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(schema)
    finally:
        conn.close()
    _info(None, {"status": "initialized"})

# ---------------------------------------------------------------------------
# fetch
# ---------------------------------------------------------------------------

def _strip_html(text):
    return re.sub(r"<[^>]+>", " ", text or "").strip()

def _parse_date(entry):
    for attr in ("published_parsed", "updated_parsed"):
        val = getattr(entry, attr, None)
        if val:
            try:
                return datetime(*val[:6], tzinfo=timezone.utc)
            except Exception:
                pass
    return None

def _fetch_one(feed):
    """Fetch a single RSS/Atom feed. Returns (stories, error_str|None)."""
    url        = feed["url"]
    name       = feed["name"]
    categories = feed.get("categories", [])
    try:
        parsed = feedparser.parse(
            url,
            agent          = "HermesNewsSkill/1.0",
            request_headers = {"Connection": "close"},
        )
        stories = []
        for entry in parsed.entries:
            link = entry.get("link", "").strip()
            if not link:
                continue
            summary = _strip_html(
                entry.get("summary") or entry.get("description") or ""
            )
            stories.append({
                "url":        link,
                "title":      entry.get("title", "").strip(),
                "summary":    summary[:MAX_SUMMARY],
                "source":     name,
                "categories": categories,
                "published":  _parse_date(entry),
            })
        return stories, None
    except Exception as exc:
        return [], f"{type(exc).__name__}: {exc}"

def cmd_fetch(args):
    socket.setdefaulttimeout(FETCH_TIMEOUT)

    data  = load_feeds()
    feeds = data.get("feeds", [])

    if not feeds:
        print(json.dumps({"fetched": 0, "inserted": 0, "failed": 0}))
        return

    all_stories = []
    failed = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(_fetch_one, feed): feed for feed in feeds}
        for future in as_completed(futures):
            feed = futures[future]
            stories, error = future.result()
            if error:
                failed += 1
                print(
                    f"[ERROR] fetch failed: {feed['url']} — {error}",
                    file=sys.stderr,
                )
            else:
                all_stories.extend(stories)

    inserted = 0
    if all_stories:
        conn = get_conn()
        try:
            with conn:
                with conn.cursor() as cur:
                    for story in all_stories:
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
                            print(
                                f"[ERROR] insert failed: {story['url']} — {exc}",
                                file=sys.stderr,
                            )
        finally:
            conn.close()

    print(json.dumps({"fetched": len(all_stories), "inserted": inserted, "failed": failed}))

# ---------------------------------------------------------------------------
# query
# ---------------------------------------------------------------------------

def cmd_query(args):
    # Resolve time window
    if args.hours:
        hours = args.hours
    elif args.days:
        hours = args.days * 24
    else:
        hours = 24

    since      = datetime.now(timezone.utc) - timedelta(hours=hours)
    conditions = ["published >= %s"]
    params     = [since]

    if args.category:
        conditions.append("%s = ANY(categories)")
        params.append(args.category)

    if args.keyword:
        conditions.append("search_vector @@ plainto_tsquery('english', %s)")
        params.append(args.keyword)

    where = " AND ".join(conditions)
    sql   = f"""
        SELECT url, title, summary, source, categories, published
        FROM   stories
        WHERE  {where}
        ORDER  BY published DESC
    """
    if args.limit:
        sql += f" LIMIT {args.limit}"

    conn = get_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
    finally:
        conn.close()

    stories = [
        _omit_none({
            "title":      row["title"],
            "url":        row["url"],
            "source":     row["source"],
            "categories": row["categories"],
            "published":  row["published"].isoformat() if row["published"] else None,
            "summary":    row["summary"],
        })
        for row in rows
    ]

    print(json.dumps(
        {
            "query":   _omit_none({"category": args.category, "keyword": args.keyword, "hours": hours, "limit": args.limit}),
            "count":   len(stories),
            "stories": stories,
        },
        indent=2,
        default=str,
    ))

# ---------------------------------------------------------------------------
# purge
# ---------------------------------------------------------------------------

def cmd_purge(args):
    cutoff = datetime.now(timezone.utc) - timedelta(days=PURGE_DAYS)
    conn   = get_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM stories WHERE fetched_at < %s", (cutoff,))
                deleted = cur.rowcount
    finally:
        conn.close()
    print(json.dumps({"purged": deleted, "cutoff": cutoff.isoformat()}))

# ---------------------------------------------------------------------------
# Feed CRUD
# ---------------------------------------------------------------------------

def cmd_add_feed(args):
    data  = load_feeds()
    feeds = data.get("feeds", [])

    if any(f["url"] == args.url for f in feeds):
        print(json.dumps({"error": f"Feed already exists: {args.url}"}))
        sys.exit(1)

    categories = [c.strip() for c in args.categories.split(",") if c.strip()]
    if not categories:
        print(json.dumps({"error": "At least one category is required."}))
        sys.exit(1)

    known    = data.get("categories", [])
    new_cats = [c for c in categories if c not in known]
    if new_cats:
        data["categories"] = known + new_cats

    feeds.append({"name": args.name, "url": args.url, "categories": categories})
    data["feeds"] = feeds
    save_feeds(data)
    print(json.dumps({"status": "added", "name": args.name, "url": args.url, "categories": categories}))


def cmd_remove_feed(args):
    data  = load_feeds()
    feeds = data.get("feeds", [])

    target = next((f for f in feeds if f["url"] == args.url), None)
    if not target:
        print(json.dumps({"error": f"Feed not found: {args.url}"}))
        sys.exit(1)

    remaining   = [f for f in feeds if f["url"] != args.url]
    usage_after = category_usage(remaining)
    would_empty = [c for c in target.get("categories", []) if c not in usage_after]

    if would_empty:
        print(json.dumps({
            "error": f"Cannot remove — would empty categories: {would_empty}",
            "tip":   "Assign these categories to another feed first.",
        }))
        sys.exit(1)

    data["feeds"] = remaining
    save_feeds(data)
    print(json.dumps({"status": "removed", "url": args.url}))


def cmd_update_feed(args):
    data  = load_feeds()
    feeds = data.get("feeds", [])

    feed = next((f for f in feeds if f["url"] == args.url), None)
    if not feed:
        print(json.dumps({"error": f"Feed not found: {args.url}"}))
        sys.exit(1)

    if args.name:
        feed["name"] = args.name

    if args.new_url:
        if any(f["url"] == args.new_url for f in feeds if f["url"] != args.url):
            print(json.dumps({"error": f"URL already exists: {args.new_url}"}))
            sys.exit(1)
        feed["url"] = args.new_url

    save_feeds(data)
    print(json.dumps({"status": "updated", "feed": feed}))


def cmd_add_category_to_feed(args):
    data  = load_feeds()
    feeds = data.get("feeds", [])

    feed = next((f for f in feeds if f["url"] == args.url), None)
    if not feed:
        print(json.dumps({"error": f"Feed not found: {args.url}"}))
        sys.exit(1)

    known = data.get("categories", [])
    if args.category not in known:
        data["categories"] = known + [args.category]

    if args.category not in feed.get("categories", []):
        feed.setdefault("categories", []).append(args.category)

    save_feeds(data)
    print(json.dumps({"status": "category added", "feed": feed["name"], "category": args.category}))


def cmd_remove_category_from_feed(args):
    data  = load_feeds()
    feeds = data.get("feeds", [])

    feed = next((f for f in feeds if f["url"] == args.url), None)
    if not feed:
        print(json.dumps({"error": f"Feed not found: {args.url}"}))
        sys.exit(1)

    if args.category not in feed.get("categories", []):
        print(json.dumps({"error": f"Feed does not have category: {args.category}"}))
        sys.exit(1)

    if len(feed["categories"]) == 1:
        print(json.dumps({"error": "Cannot remove the last category from a feed. Add another first."}))
        sys.exit(1)

    others_with_cat = [
        f["name"] for f in feeds
        if f["url"] != args.url and args.category in f.get("categories", [])
    ]
    if not others_with_cat:
        print(json.dumps({
            "error": f"Cannot remove — would empty category '{args.category}'.",
            "tip":   "Add another feed to this category first.",
        }))
        sys.exit(1)

    feed["categories"].remove(args.category)
    save_feeds(data)
    print(json.dumps({"status": "category removed", "feed": feed["name"], "category": args.category}))


def cmd_list_feeds(args):
    data  = load_feeds()
    feeds = data.get("feeds", [])

    if args.category:
        feeds = [f for f in feeds if args.category in f.get("categories", [])]

    print(json.dumps(
        {"categories": data.get("categories", []), "count": len(feeds), "feeds": feeds},
        indent=2,
    ))

# ---------------------------------------------------------------------------
# Category definition CRUD
# ---------------------------------------------------------------------------

def cmd_add_category_def(args):
    data = load_feeds()
    if args.name in data.get("categories", []):
        print(json.dumps({"error": f"Category already exists: {args.name}"}))
        sys.exit(1)
    data.setdefault("categories", []).append(args.name)
    save_feeds(data)
    print(json.dumps({"status": "category created", "category": args.name}))


def cmd_remove_category_def(args):
    data = load_feeds()
    if args.name not in data.get("categories", []):
        print(json.dumps({"error": f"Category not found: {args.name}"}))
        sys.exit(1)

    in_use = [f["name"] for f in data.get("feeds", []) if args.name in f.get("categories", [])]
    if in_use:
        print(json.dumps({
            "error": f"Category '{args.name}' is still used by: {in_use}",
            "tip":   "Remove this category from all feeds before deleting it.",
        }))
        sys.exit(1)

    data["categories"].remove(args.name)
    save_feeds(data)
    print(json.dumps({"status": "category removed", "category": args.name}))

# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def build_parser():
    parser = argparse.ArgumentParser(
        prog        = "news.py",
        description = "Hermes news aggregator skill",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # --- lifecycle ---
    sub.add_parser("start", help="Start PostgreSQL via docker-compose, wait until healthy")
    sub.add_parser("stop",  help="Stop PostgreSQL via docker-compose")

    # --- core ---
    sub.add_parser("init",  help="Initialize database schema")
    sub.add_parser("fetch", help="Pull all feeds into PostgreSQL")
    sub.add_parser("purge", help="Delete stories older than 30 days")

    q = sub.add_parser("query", help="Query stories")
    q.add_argument("--category", help="Filter by category name")
    q.add_argument("--keyword",  help="Full-text keyword search")
    q.add_argument("--limit",    type=int, help="Max number of stories to return")
    g = q.add_mutually_exclusive_group()
    g.add_argument("--hours", type=int, help="Stories from last N hours (default 24)")
    g.add_argument("--days",  type=int, help="Stories from last N days")

    # --- feed CRUD ---
    af = sub.add_parser("add-feed", help="Add a feed to the registry")
    af.add_argument("--url",        required=True)
    af.add_argument("--name",       required=True)
    af.add_argument("--categories", required=True, help="Comma-separated categories")

    rf = sub.add_parser("remove-feed", help="Remove a feed")
    rf.add_argument("--url", required=True)

    uf = sub.add_parser("update-feed", help="Update feed name or URL")
    uf.add_argument("--url",     required=True, help="Current URL")
    uf.add_argument("--name",    help="New display name")
    uf.add_argument("--new-url", help="New URL")

    ac = sub.add_parser("add-category", help="Add a category to a feed")
    ac.add_argument("--url",      required=True)
    ac.add_argument("--category", required=True)

    rc = sub.add_parser("remove-category", help="Remove a category from a feed")
    rc.add_argument("--url",      required=True)
    rc.add_argument("--category", required=True)

    lf = sub.add_parser("list-feeds", help="List feeds in the registry")
    lf.add_argument("--category", help="Filter by category")

    # --- category def CRUD ---
    acd = sub.add_parser("add-category-def", help="Create a new category definition")
    acd.add_argument("name")

    rcd = sub.add_parser("remove-category-def", help="Remove a category definition")
    rcd.add_argument("name")

    return parser


def _is_postgres_running():
    """Check if PostgreSQL is already accepting connections."""
    try:
        conn = get_conn()
        conn.close()
        return True
    except Exception:
        return False

def _ensure_ready():
    """Auto-start PostgreSQL and initialize schema if needed."""
    if not _is_postgres_running():
        cmd_start(None)

    # One-time schema init
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM stories LIMIT 0")
        conn.close()
    except Exception:
        cmd_init(None)

def main():
    _bootstrap_files()          # materialise companion files if missing
    load_dotenv(SKILL_DIR / ".env")  # reload now that .env is guaranteed to exist

    parser = build_parser()
    args   = parser.parse_args()

    # Commands that need the database auto-start PostgreSQL and init schema
    _db_commands = {"init", "fetch", "query", "purge"}

    dispatch = {
        "start":              cmd_start,
        "stop":               cmd_stop,
        "init":               cmd_init,
        "fetch":              cmd_fetch,
        "query":              cmd_query,
        "purge":              cmd_purge,
        "add-feed":           cmd_add_feed,
        "remove-feed":        cmd_remove_feed,
        "update-feed":        cmd_update_feed,
        "add-category":       cmd_add_category_to_feed,
        "remove-category":    cmd_remove_category_from_feed,
        "list-feeds":         cmd_list_feeds,
        "add-category-def":   cmd_add_category_def,
        "remove-category-def": cmd_remove_category_def,
    }

    if args.command in _db_commands and args.command != "start":
        _ensure_ready()

    dispatch[args.command](args)


if __name__ == "__main__":
    main()
