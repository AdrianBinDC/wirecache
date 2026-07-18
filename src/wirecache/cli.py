"""wirecache CLI — argparse + dispatch only."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from wirecache import docker_lifecycle
from wirecache.config import LAST_FETCH_PATH, DEFAULT_PURGE_DAYS, bootstrap, load_env
from wirecache.feeds.opml import import_opml
from wirecache.feeds.registry import Registry, RegistryError
from wirecache.fetch.rss import fetch_all
from wirecache.output import FORMATS, render
from wirecache.store.stories import QueryFilter, StoryStore


def _print_json(data: dict, *, exit_code: int = 0) -> None:
    print(json.dumps(data, indent=2, default=str))
    if exit_code:
        sys.exit(exit_code)


def _parse_since(value: str) -> datetime:
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    dt = datetime.fromisoformat(raw)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _write_last_fetch(payload: dict) -> None:
    LAST_FETCH_PATH.parent.mkdir(exist_ok=True)
    LAST_FETCH_PATH.write_text(json.dumps(payload, indent=2, default=str))


def _read_last_fetch() -> dict | None:
    if not LAST_FETCH_PATH.exists():
        return None
    try:
        return json.loads(LAST_FETCH_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return None


# --- commands ---

def cmd_start(_args) -> None:
    _print_json(docker_lifecycle.start())


def cmd_stop(_args) -> None:
    _print_json(docker_lifecycle.stop())


def cmd_init(_args) -> None:
    store = StoryStore()
    store.init_schema()
    _print_json({"status": "initialized"})


def cmd_fetch(_args) -> None:
    registry = Registry()
    feeds = registry.load().get("feeds", [])
    result = fetch_all(feeds)

    for failure in result.failures:
        print(
            f"[ERROR] fetch failed: {failure.url} — {failure.error}",
            file=sys.stderr,
        )

    store = StoryStore()
    inserted = store.insert_many(result.stories)

    payload = {
        "fetched": result.fetched,
        "inserted": inserted,
        "failed": result.failed,
        "failures": [
            {"url": f.url, "name": f.name, "error": f.error} for f in result.failures
        ],
        "finished_at": datetime.now(timezone.utc).isoformat(),
    }
    _write_last_fetch(payload)
    print(json.dumps({k: payload[k] for k in ("fetched", "inserted", "failed", "failures")}))


def cmd_query(args) -> None:
    categories = list(args.category or [])
    since = _parse_since(args.since) if args.since else None

    filt = QueryFilter(
        categories=categories,
        keyword=args.keyword,
        source=args.source,
        since=since,
        hours=args.hours,
        days=args.days,
        limit=args.limit,
    )

    store = StoryStore()
    stories = store.query(filt)
    payload = {
        "query": filt.meta(),
        "count": len(stories),
        "stories": stories,
    }
    out = render(payload, args.format)
    print(out, end="" if out.endswith("\n") else "\n")


def cmd_purge(args) -> None:
    store = StoryStore()
    _print_json(store.purge(days=args.days))


def cmd_status(_args) -> None:
    registry = Registry()
    data = registry.load()
    store = StoryStore()

    db_ok = store.is_reachable()
    status: dict = {
        "postgres": "up" if db_ok else "down",
        "feed_count": len(data.get("feeds", [])),
        "categories": data.get("categories", []),
    }

    if db_ok:
        if store.schema_ready():
            status.update(store.stats())
        else:
            status["schema"] = "missing"
    else:
        status["story_count"] = None

    last = _read_last_fetch()
    if last:
        status["last_fetch"] = {
            "finished_at": last.get("finished_at"),
            "fetched": last.get("fetched"),
            "inserted": last.get("inserted"),
            "failed": last.get("failed"),
            "failures": last.get("failures", [])[:10],
        }
    else:
        status["last_fetch"] = None

    _print_json(status)


def cmd_import_opml(args) -> None:
    path = Path(args.path)
    if not path.exists():
        _print_json({"error": f"File not found: {path}"}, exit_code=1)
    registry = Registry()
    result = import_opml(path, registry, default_category=args.category)
    _print_json(result)


def _registry_cmd(fn):
    def wrapper(args):
        registry = Registry()
        try:
            result = fn(registry, args)
            _print_json(result)
        except RegistryError as exc:
            _print_json(exc.as_dict(), exit_code=1)

    return wrapper


@_registry_cmd
def cmd_add_feed(registry: Registry, args) -> dict:
    categories = [c.strip() for c in args.categories.split(",") if c.strip()]
    return registry.add_feed(args.url, args.name, categories)


@_registry_cmd
def cmd_remove_feed(registry: Registry, args) -> dict:
    return registry.remove_feed(args.url)


@_registry_cmd
def cmd_update_feed(registry: Registry, args) -> dict:
    return registry.update_feed(args.url, name=args.name, new_url=args.new_url)


@_registry_cmd
def cmd_add_category(registry: Registry, args) -> dict:
    return registry.add_category_to_feed(args.url, args.category)


@_registry_cmd
def cmd_remove_category(registry: Registry, args) -> dict:
    return registry.remove_category_from_feed(args.url, args.category)


@_registry_cmd
def cmd_list_feeds(registry: Registry, args) -> dict:
    return registry.list_feeds(category=args.category)


@_registry_cmd
def cmd_add_category_def(registry: Registry, args) -> dict:
    return registry.add_category_def(args.name)


@_registry_cmd
def cmd_remove_category_def(registry: Registry, args) -> dict:
    return registry.remove_category_def(args.name)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="wirecache",
        description="Cache a curated newswire locally and query it.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("start", help="Start PostgreSQL via docker compose")
    sub.add_parser("stop", help="Stop PostgreSQL")
    sub.add_parser("init", help="Apply database schema")
    sub.add_parser("fetch", help="Pull all feeds into PostgreSQL")
    sub.add_parser("status", help="Show DB, feed, and last-fetch health")

    purge = sub.add_parser("purge", help="Delete old stories")
    purge.add_argument(
        "--days",
        type=int,
        default=DEFAULT_PURGE_DAYS,
        help=f"Delete stories fetched more than N days ago (default {DEFAULT_PURGE_DAYS})",
    )

    q = sub.add_parser("query", help="Query cached stories")
    q.add_argument(
        "--category",
        action="append",
        help="Filter by category (repeatable; OR)",
    )
    q.add_argument("--keyword", help="Full-text keyword search")
    q.add_argument("--source", help="Filter by source name")
    q.add_argument("--limit", type=int, help="Max stories to return")
    q.add_argument("--fetch-first", action="store_true", help="Run fetch before querying")
    q.add_argument(
        "--format",
        choices=FORMATS,
        default="json",
        help="Output format (default: json)",
    )
    time_g = q.add_mutually_exclusive_group()
    time_g.add_argument("--hours", type=int, help="Stories from last N hours (default 24)")
    time_g.add_argument("--days", type=int, help="Stories from last N days")
    time_g.add_argument("--since", help="Stories published at or after ISO-8601 timestamp")

    af = sub.add_parser("add-feed", help="Add a feed to the registry")
    af.add_argument("--url", required=True)
    af.add_argument("--name", required=True)
    af.add_argument("--categories", required=True, help="Comma-separated categories")

    rf = sub.add_parser("remove-feed", help="Remove a feed")
    rf.add_argument("--url", required=True)

    uf = sub.add_parser("update-feed", help="Update feed name or URL")
    uf.add_argument("--url", required=True, help="Current URL")
    uf.add_argument("--name", help="New display name")
    uf.add_argument("--new-url", help="New URL")

    ac = sub.add_parser("add-category", help="Add a category to a feed")
    ac.add_argument("--url", required=True)
    ac.add_argument("--category", required=True)

    rc = sub.add_parser("remove-category", help="Remove a category from a feed")
    rc.add_argument("--url", required=True)
    rc.add_argument("--category", required=True)

    lf = sub.add_parser("list-feeds", help="List feeds")
    lf.add_argument("--category", help="Filter by category")

    acd = sub.add_parser("add-category-def", help="Create a category definition")
    acd.add_argument("name")

    rcd = sub.add_parser("remove-category-def", help="Remove a category definition")
    rcd.add_argument("name")

    opml = sub.add_parser("import-opml", help="Import feeds from an OPML file")
    opml.add_argument("path", help="Path to .opml file")
    opml.add_argument(
        "--category",
        default="imported",
        help="Default category when OPML has no folders (default: imported)",
    )

    return parser


def main(argv: list[str] | None = None) -> None:
    bootstrap()
    load_env()

    parser = build_parser()
    args = parser.parse_args(argv)

    db_commands = {"init", "fetch", "query", "purge", "status"}
    store = StoryStore()

    if args.command in db_commands:
        docker_lifecycle.ensure_ready(store)

    if args.command == "query" and args.fetch_first:
        cmd_fetch(None)

    dispatch = {
        "start": cmd_start,
        "stop": cmd_stop,
        "init": cmd_init,
        "fetch": cmd_fetch,
        "query": cmd_query,
        "purge": cmd_purge,
        "status": cmd_status,
        "import-opml": cmd_import_opml,
        "add-feed": cmd_add_feed,
        "remove-feed": cmd_remove_feed,
        "update-feed": cmd_update_feed,
        "add-category": cmd_add_category,
        "remove-category": cmd_remove_category,
        "list-feeds": cmd_list_feeds,
        "add-category-def": cmd_add_category_def,
        "remove-category-def": cmd_remove_category_def,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
