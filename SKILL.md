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
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [News, RSS, Aggregator, Research, Headlines]
    requires_toolsets: [terminal]
    config:
      - key: news.fetch_before_query
        description: "Auto-fetch latest stories before each query"
        default: "false"
        prompt: "Fetch latest stories before every query?"
---

# News Skill

Fetch, store, and query RSS news stories from a curated feed registry backed by PostgreSQL.

## When to Use

- User asks for news, headlines, or stories on a topic, category, or keyword
- User wants to manage news feeds (add, remove, update, list)
- User asks what's happening in a particular domain (tech, politics, AI, etc.)

## Prerequisites

- **Docker** — PostgreSQL runs in a Docker container (auto-managed)
- **uv** — manages Python dependencies

## Quick Reference

| Action | Command |
|--------|---------|
| Query all recent news | `uv run ${HERMES_SKILL_DIR}/scripts/news.py query` |
| Query by category | `uv run ${HERMES_SKILL_DIR}/scripts/news.py query --category ai` |
| Search by keyword | `uv run ${HERMES_SKILL_DIR}/scripts/news.py query --keyword "CUDA"` |
| Fetch + query in one call | `uv run ${HERMES_SKILL_DIR}/scripts/news.py query --fetch-first` |
| Fetch latest stories | `uv run ${HERMES_SKILL_DIR}/scripts/news.py fetch` |
| List feeds | `uv run ${HERMES_SKILL_DIR}/scripts/news.py list-feeds` |
| Add a feed | `uv run ${HERMES_SKILL_DIR}/scripts/news.py add-feed --url URL --name NAME --categories cat1,cat2` |
| Purge old stories | `uv run ${HERMES_SKILL_DIR}/scripts/news.py purge` |

**PostgreSQL lifecycle is auto-managed.** The script starts PostgreSQL and initializes the schema automatically when needed. You never call `start` or `init` manually.

## Procedure

### 1. Self-Bootstrap (first invocation only)

On the **first time** the news skill is used in a session, ensure the background fetch cron exists:

1. List existing cron jobs: `cronjob action=list`
2. Look for a job named `news-fetch`. If it does NOT exist, create it:

   Use the cronjob tool with:
   - `action=create`
   - `name="news-fetch"`
   - `schedule="15m"`
   - `script="${HERMES_SKILL_DIR}/scripts/fetch.sh"`
   - `no_agent=true`

   This runs fetch every 30 minutes in the background. The script is silent unless new stories arrive or an error occurs. After this, the DB stays fresh automatically.

3. **Then run one initial fetch** to populate the DB before the first query:

```bash
uv run ${HERMES_SKILL_DIR}/scripts/news.py fetch
```

### 2. Query News

On subsequent invocations (cron already running), just query directly — no fetch needed:

```bash
# All news, last 24 hours (default)
uv run ${HERMES_SKILL_DIR}/scripts/news.py query

# By category
uv run ${HERMES_SKILL_DIR}/scripts/news.py query --category ai
uv run ${HERMES_SKILL_DIR}/scripts/news.py query --category tech

# By keyword (full-text search)
uv run ${HERMES_SKILL_DIR}/scripts/news.py query --keyword "CUDA memory"

# Category + keyword
uv run ${HERMES_SKILL_DIR}/scripts/news.py query --category ai --keyword "NVIDIA"

# By source
uv run ${HERMES_SKILL_DIR}/scripts/news.py query --source "The Verge"

# Custom time window
uv run ${HERMES_SKILL_DIR}/scripts/news.py query --category us-news --hours 6
uv run ${HERMES_SKILL_DIR}/scripts/news.py query --category world-news --days 3

# Limit results
uv run ${HERMES_SKILL_DIR}/scripts/news.py query --category tech --limit 5

# Fetch + query in one call (when you know DB might be stale)
uv run ${HERMES_SKILL_DIR}/scripts/news.py query --fetch-first --category ai --limit 5
```

**Output:** JSON to stdout — `{ query, count, stories: [{title, url, source, categories, published, summary}] }`

### 3. Present Results

Format results for the user as a readable list. Do not dump raw JSON.

```
Here are the latest AI stories:

1. **Story Title** — Source (2h ago)
   Brief summary...
   🔗 URL

2. ...
```

### 4. Feed Registry Management

```bash
# List all feeds
uv run ${HERMES_SKILL_DIR}/scripts/news.py list-feeds

# List feeds by category
uv run ${HERMES_SKILL_DIR}/scripts/news.py list-feeds --category ai

# Add a feed (creates new category if needed)
uv run ${HERMES_SKILL_DIR}/scripts/news.py add-feed --url https://example.com/feed --name "Example" --categories tech,ai

# Remove a feed (blocked if it would empty a category)
uv run ${HERMES_SKILL_DIR}/scripts/news.py remove-feed --url https://example.com/feed

# Update a feed
uv run ${HERMES_SKILL_DIR}/scripts/news.py update-feed --url https://old.com/feed --name "New Name"
uv run ${HERMES_SKILL_DIR}/scripts/news.py update-feed --url https://old.com/feed --new-url https://new.com/feed

# Add/remove a category from a feed
uv run ${HERMES_SKILL_DIR}/scripts/news.py add-category --url https://example.com/feed --category world-news
uv run ${HERMES_SKILL_DIR}/scripts/news.py remove-category --url https://example.com/feed --category tech

# Manage category definitions
uv run ${HERMES_SKILL_DIR}/scripts/news.py add-category-def sports
uv run ${HERMES_SKILL_DIR}/scripts/news.py remove-category-def sports   # blocked if any feeds use it
```

### 5. Maintenance

```bash
# Purge stories older than 30 days
uv run ${HERMES_SKILL_DIR}/scripts/news.py purge

# Manual lifecycle (rare — only if needed)
uv run ${HERMES_SKILL_DIR}/scripts/news.py start
uv run ${HERMES_SKILL_DIR}/scripts/news.py stop
```

## Available Categories

| Category | Description |
|----------|-------------|
| `us-news` | US general news |
| `tech` | Technology |
| `mac` | Apple/Mac |
| `ai` | Artificial Intelligence |
| `world-news` | International news |
| `us-politics` | US politics |
| `world-politics` | International politics |

## Verification

- **Query worked:** stdout is valid JSON with `"count" > 0`
- **Fetch worked:** output shows `"inserted" > 0` or `"inserted": 0` (if already current)
- **Feed operations:** output includes `"status": "added"`, `"removed"`, `"updated"`
- **Errors:** always go to stderr; stdout is always valid JSON

## Pitfalls

- **Docker not installed:** The script will fail with a subprocess error. Check `docker --version` first.
- **Port 5432 in use:** If another PostgreSQL is running, change `POSTGRES_PORT` in `.env`.
- **Feed fetch failures:** Some feeds may be unreachable. Check `"failed"` count in fetch output.
- **Slow startup on first run:** Docker pulls the PostgreSQL image (~100MB). Subsequent starts are instant.
- **Large result sets:** Always use `--limit` when the agent needs a manageable number of results.
- **HTML entities in summaries:** Some feeds include `&#8230;` etc. in summaries — this is expected and harmless.
- **Cron job must exist for fresh data:** The background `news-fetch` cron keeps the DB current. If it was removed or never created, the agent should recreate it on first invocation (see self-bootstrap above).

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
  ├── SKILL.md              # this file
  ├── .env.example          # template for .env
  ├── feeds.yaml            # feed registry — source of truth
  ├── scripts/
  │   ├── news.py           # main script (inline deps via uv)
  │   └── fetch.sh          # wrapper for cronjob (silent background fetch)
  ├── docker-compose.yml    # generated at runtime by _bootstrap_files()
  └── schema.sql            # generated at runtime by _bootstrap_files()
```

`.env` and `.gitignore` are local-only and not committed.
