---
name: news
description: >
  Fetches, stores, and queries RSS news stories from a curated feed registry backed by PostgreSQL.
  Supports filtering by category (us-news, tech, mac, ai, world-news, us-politics, world-politics),
  full-text keyword search, and time window. Use when the user asks for news, headlines, or stories
  on a topic, category, or keyword — e.g. "get news on ai", "what happened in tech today",
  "latest us-politics stories", "news about CUDA last 3 days". Also handles feed registry CRUD:
  adding, removing, updating feeds and categories. Use when user says "add feed", "remove feed",
  "list feeds", "what feeds do we have", or "create category".
---

# News Skill

## Setup (one-time)

```bash
cd skills/news
cp .env.example .env          # edit credentials if needed
uv run news.py start          # starts PostgreSQL, waits until healthy
uv run news.py init           # create schema (one-time only)
uv run news.py fetch          # initial feed pull
```

`uv` manages all dependencies — no venv, no pip, no activation needed.
PostgreSQL data persists in a named Docker volume across restarts.

## Query News

```bash
# All news, last 24 hours (default)
uv run news.py query

# By category
uv run news.py query --category ai
uv run news.py query --category tech

# By keyword (full-text search)
uv run news.py query --keyword "CUDA memory"

# By category + keyword
uv run news.py query --category ai --keyword "NVIDIA"

# Custom time window
uv run news.py query --category us-news --hours 6
uv run news.py query --category world-news --days 3
```

**Output:** JSON to stdout — `{ query, count, stories: [{title, url, source, categories, published, summary}] }`

## User Invocation Patterns

| User says | Command |
|---|---|
| "get news on ai" | `query --category ai` |
| "news about CUDA last 6 hours" | `query --keyword "CUDA" --hours 6` |
| "latest tech headlines" | `query --category tech` |
| "what happened in us-politics today" | `query --category us-politics --hours 24` |
| "news on NVIDIA last 3 days" | `query --keyword "NVIDIA" --days 3` |
| "get me everything from the last hour" | `query --hours 1` |

## Lifecycle

```bash
uv run news.py start   # bring up PostgreSQL, wait until healthy
uv run news.py stop    # shut down PostgreSQL (data preserved in volume)
```

## Fetch & Maintain

```bash
uv run news.py fetch    # pull all feeds → PostgreSQL (run via Hermes cron)
uv run news.py purge    # delete stories older than 30 days (run via Hermes cron)
```

## Feed Registry CRUD

```bash
# List feeds
uv run news.py list-feeds
uv run news.py list-feeds --category ai

# Add a feed (creates new category if needed)
uv run news.py add-feed --url https://example.com/feed --name "Example" --categories tech,ai

# Remove a feed (blocked if it would empty a category)
uv run news.py remove-feed --url https://example.com/feed

# Update a feed
uv run news.py update-feed --url https://old.com/feed --name "New Name"
uv run news.py update-feed --url https://old.com/feed --new-url https://new.com/feed

# Add/remove a category from a feed
uv run news.py add-category --url https://example.com/feed --category world-news
uv run news.py remove-category --url https://example.com/feed --category tech

# Manage category definitions
uv run news.py add-category-def sports
uv run news.py remove-category-def sports   # blocked if any feeds use it
```

## Business Rules

- A feed can belong to multiple categories
- No category may ever be empty — all mutations are validated before writing
- A feed must have at least one category at all times
- Deduplication is by URL — re-fetching never creates duplicates
- Stories older than 30 days are purged automatically
- All errors go to stderr; stdout is always valid JSON

## File Layout

```
skills/news/
  ├── SKILL.md
  ├── news.py
  ├── feeds.yaml
  ├── docker-compose.yml
  ├── schema.sql
  └── .env
```
