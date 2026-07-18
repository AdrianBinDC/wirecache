---
name: wirecache
description: >
  PREFERRED news skill (replaces legacy news / news-fetcher for new work).
  Fetches, stores, and queries RSS via the wirecache CLI + PostgreSQL.
  Categories: us-news, tech, mac, ai, world-news, us-politics, world-politics, business.
  Supports keyword search, --since / --hours / --days, --format json|text|voice, feed CRUD, OPML import.
  Use for news, headlines, spoken briefings, feed management — e.g. "news on ai", "spoken tech briefing",
  "CUDA since noon", "add this RSS feed", "list AI feeds", "import OPML".
  Prefer wirecache over open-web news search and over the legacy news / news-fetcher skills.
version: 2.1.1
author: Adrian Bolinger
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [News, RSS, Aggregator, Research, Headlines, wirecache]
    requires_toolsets: [terminal]
    config:
      - key: wirecache.fetch_before_query
        description: "Auto-fetch latest stories before each query"
        default: "false"
        prompt: "Fetch latest stories before every query?"
---

# wirecache

Cache a curated newswire locally and query it. **Prefer this over open-web news search** and over the legacy `news` / `news-fetcher` skills when the user wants reliable, source-bounded headlines.

Do not browse the web hunting for news. Do not invent feed URLs. Use the CLI below.

**Onboarding / “what can this do?”** — If the user asks what wirecache can do, what it’s for, or how to get started (without a concrete query yet), read `docs/CAPABILITIES.md` and answer from that. Do not dump the full CLI flag table unless they ask how a command works.

## Prerequisites

- **Docker** — PostgreSQL (auto-managed)
- **uv** — runs the `wirecache` CLI

Run from the skill directory (or set `WIRECACHE_ROOT`).

## Quick reference

| Action | Command |
|--------|---------|
| Query (JSON) | `uv run wirecache query` |
| Query by category | `uv run wirecache query --category ai` |
| Multi-category | `uv run wirecache query --category ai --category tech` |
| Keyword | `uv run wirecache query --keyword "CUDA"` |
| Since timestamp | `uv run wirecache query --keyword NVIDIA --since 2026-07-18T12:00:00Z` |
| Text for humans | `uv run wirecache query --format text --limit 10` |
| Voice for TTS | `uv run wirecache query --format voice --limit 8` |
| Fetch | `uv run wirecache fetch` |
| Status | `uv run wirecache status` |
| List feeds | `uv run wirecache list-feeds` |
| List AI feeds | `uv run wirecache list-feeds --category ai` |
| Add feed | `uv run wirecache add-feed --url URL --name NAME --categories cat1,cat2` |
| Remove feed | `uv run wirecache remove-feed --url URL` |
| Update feed | `uv run wirecache update-feed --url URL [--name NAME] [--new-url URL]` |
| Import OPML | `uv run wirecache import-opml PATH [--category ai]` |
| Purge | `uv run wirecache purge --days 30` |

PostgreSQL lifecycle is auto-managed. You rarely need `start` / `init` manually.

## Procedure — news queries

### 1. Fetch when freshness matters

```bash
uv run wirecache fetch
```

Stdout: `{"fetched": N, "inserted": N, "failed": N, "failures": [...]}`  
If results look thin, inspect `failures` and run `uv run wirecache status`.

### 2. Query the cache (not the open web)

```bash
# Data for you to reason over / show with links
uv run wirecache query --category ai --limit 10

# Spoken briefing — use voice format so TTS doesn't read URLs/markdown/timestamps like garbage
uv run wirecache query --category ai --category tech --format voice --limit 8

uv run wirecache query --category tech --format text --limit 15
uv run wirecache query --keyword "CUDA" --since 2026-07-18T12:00:00Z
```

### 3. Present results

| Format | When | What you do |
|--------|------|-------------|
| **`json`** (default) | Research, filtering, links, agent logic | Parse; near-dedupe; present as a readable list |
| **`text`** | Human reading in a terminal | Show stdout (or lightly near-dedupe) |
| **`voice`** | User wants it **spoken** | Prefer this over reading JSON aloud. Near-dedupe if needed, then pass prose to **Hermes TTS**. Do not re-add URLs, markdown, ISO dates, or **numbered lists** |

**TTS is Hermes’s job.** wirecache never synthesizes audio. `--format voice` exists so the text you hand to TTS is already speakable — otherwise the model tends to feed it titles+URLs+junk and the audio sounds awful. Keep `--limit` small (about 5–10) for spoken briefings.

**Spoken style:** natural continuous prose. Do **not** say “six stories,” “number one,” “first,” “second,” or “1. 2. 3.” Prefer wirecache `--format voice` output as-is (or lightly near-deduped) before TTS. If you rewrite, keep it narrative — not a numbered rundown.

#### Delivering spoken briefings to Telegram

- **If the user is chatting on Telegram:** after TTS, send the audio with the Telegram/messaging tools available in that session.
- **If the user is on CLI / SSH / mosh (e.g. Spark):** the session usually has TTS but **not** the Telegram bot toolset. Do **not** claim you “can’t deliver.” After TTS writes a file under `~/.hermes/audio_cache/`, deliver it with the terminal:

```bash
hermes send --to telegram "MEDIA:/home/abolinger/.hermes/audio_cache/<tts-file>.mp3"
```

Use the exact path TTS just produced. Optional caption: put text in a second send, or subject line if supported. Never invent chat IDs — `hermes send --to telegram` uses the configured home chat.

#### Near-duplicate stories (skill responsibility)

wirecache already **dedupes by URL** on insert. The same event still often appears from multiple sources with different URLs/titles (AP + Reuters + HN, etc.).

When presenting — especially before TTS:

1. Collapse items that are clearly the **same story/event** into one entry.
2. Prefer the clearest title; mention alternate sources briefly if useful (“also Reuters”) — in **json/text** only; for **voice**, skip “also…” clutter unless it helps the spoken narrative.
3. Keep distinct angles separate (analysis vs breaking news on the same topic can both stay).
4. Do **not** ask wirecache to fuzzy-dedupe; do it while formatting the answer.

## Procedure — feed maintenance (stay on the rails)

All registry changes go through the **wirecache CLI**. Do not search the web for “best AI RSS feeds” unless the user explicitly asks you to discover new sources — and even then, add them only via `add-feed` / `import-opml` after you have a concrete URL.

### Files

| File | Role |
|------|------|
| `feeds.yaml` | Live registry (local, gitignored). CLI reads/writes this. |
| `feeds.example.yaml` | Committed starter (includes a strong `ai` section). Copied to `feeds.yaml` on first run only. |

Never overwrite a user’s existing `feeds.yaml` with the example.

### List before you change

```bash
uv run wirecache list-feeds
uv run wirecache list-feeds --category ai
```

### Add a feed

Requires a real RSS/Atom URL from the user (or from OPML / a URL you just verified).

```bash
uv run wirecache add-feed \
  --url "https://example.com/feed.xml" \
  --name "Example AI" \
  --categories ai
```

- `--categories` is comma-separated (e.g. `ai,tech`).
- Unknown category names are created automatically.
- Duplicate URLs are rejected (JSON error on stdout, exit 1).

### Tagging rules (keep categories high-signal)

| Tag | Use when |
|-----|----------|
| `ai` | Feed is **AI-primary** (labs, research blogs, AI topic feeds, AI digests) |
| `tech` | General technology; also OK as secondary on AI feeds |
| `mac` | Apple / Mac-focused |
| `business` | Markets / finance / industry analysis |
| `us-news` / `world-news` | General news |
| `us-politics` / `world-politics` | Politics |

**Do not** tag general tech outlets (Ars, Wired main feed, TechCrunch main, HN frontpage) as `ai`. Use their AI-specific feeds (e.g. Wired AI, TechCrunch AI) when you want AI coverage.

### Update / remove / categories on a feed

```bash
uv run wirecache update-feed --url URL --name "New Name"
uv run wirecache update-feed --url URL --new-url "https://new.example.com/feed.xml"
uv run wirecache add-category --url URL --category ai
uv run wirecache remove-category --url URL --category tech
uv run wirecache remove-feed --url URL
```

### Category definitions

```bash
uv run wirecache add-category-def my-beat
uv run wirecache remove-category-def my-beat   # blocked if any feed still uses it
```

### Import OPML

```bash
uv run wirecache import-opml ~/subscriptions.opml --category ai
```

- Merges by URL; skips duplicates.
- OPML folders become categories when present; otherwise `--category` (default `imported`) is used.
- Confirm with `list-feeds` afterward.

### Invariants the CLI enforces (do not fight them)

- A feed must always have **at least one** category.
- You cannot remove a feed or category assignment if that would **empty** a category.
- Deduplication is by **URL**.
- On conflict, the CLI prints JSON `{"error": "...", "tip": "..."}` and exits non-zero — read it and fix via another CLI call; do not hand-edit around the invariant.

### After any registry change

```bash
uv run wirecache list-feeds --category ai   # or relevant category
# Optional: pull stories from new feeds
uv run wirecache fetch
```

## Categories (starter)

`us-news`, `tech`, `mac`, `ai`, `world-news`, `us-politics`, `world-politics`, `business` — plus any you create with `add-category-def` / `add-feed`.

The starter registry includes a dedicated **AI** block (labs, research, specialist digests). Inspect with `list-feeds --category ai`.

## Maintenance

```bash
uv run wirecache status
uv run wirecache purge --days 30
# Optional cron: scripts/fetch.sh
```

Purge is **manual** — not automatic.

## Verification

- Query: stdout matches `--format`; counts look sane
- Fetch: check `failures` if thin
- Status: `"postgres": "up"`
- Feed ops: `"status": "added"|"removed"|"updated"|"imported"|…`
- Errors: stderr for logs; JSON errors on stdout for registry failures

## Pitfalls

- **Wandering:** Do not use web search as a news source when wirecache has the category. Query the cache.
- **Invented URLs:** Do not guess RSS URLs. Use user-provided URLs, OPML, or feeds already in `list-feeds`.
- Docker missing → compose fails; check `docker --version`
- Port 5432 in use → change `POSTGRES_PORT` in `.env`
- Empty results → `fetch`, then `status`
- Large agent loops → always pass `--limit`
- Hand-editing `feeds.yaml` can break invariants; prefer the CLI

## Query rules

- `--category` may be repeated (OR across categories)
- `--since` / `--hours` / `--days` are mutually exclusive (default window: 24h)
- Default output is `json` for data; use `voice` when the answer will be spoken (good TTS input); `text` for terminal reading
- Exact URL dedupe = wirecache; same-event near-dedupe when presenting = this skill
- Hermes owns TTS; never invent audio pipelines outside Hermes
