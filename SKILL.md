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

## How to Use

All commands use `uv run news.py <subcommand>` from the skill directory (`/home/abolinger/Developer/news-fetcher`).

**The script auto-manages PostgreSQL lifecycle.** On any command that needs the database, it starts PostgreSQL if not running and initializes the schema if needed. You never need to call `start` or `init` manually.

### Query News

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

### Presenting Results

Format results for the user as a readable list with title, source, and link. Don't dump raw JSON. Example:

```
Here are the latest AI stories:

1. **Story Title** — Source (2h ago)
   Brief summary...
   🔗 URL

2. ...
```

### Fetch & Maintain

Run `fetch` before querying if results seem stale or the user asks for the latest:

```bash
uv run news.py fetch    # pull all feeds → PostgreSQL
uv run news.py purge    # delete stories older than 30 days
```

### Feed Registry

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

### Lifecycle (manual override only)

```bash
uv run news.py start   # bring up PostgreSQL, wait until healthy
uv run news.py stop    # shut down PostgreSQL (data preserved in volume)
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
news-fetcher/
  ├── SKILL.md
  ├── feeds.yaml          # committed, source of truth
  ├── news.py
  ├── docker-compose.yml  # generated at runtime
  ├── schema.sql          # generated at runtime
  ├── .env                # generated at runtime
  ├── .env.example        # generated at runtime
  └── uv.lock
```
