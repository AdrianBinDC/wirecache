# wirecache

**Cache a curated newswire locally and query it** — instead of letting an agent wander the open web for “today’s news.”

wirecache pulls RSS/Atom feeds you choose into PostgreSQL, then gives you (or [Hermes](https://nousresearch.com/)) a small CLI to filter by category, keyword, source, and time. Deterministic plumbing; the LLM owns judgment and TTS.

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) (PostgreSQL runs in Compose)
- [uv](https://docs.astral.sh/uv/)
- Python 3.11+

## Quick start

```bash
git clone <your-repo-url> wirecache
cd wirecache
uv sync --extra dev

# First run copies feeds.example.yaml → feeds.yaml and .env.example → .env
uv run wirecache fetch
uv run wirecache query --category ai --format text --limit 10
```

PostgreSQL starts automatically on the first DB command. Defaults are local-dev only (`news`/`news` on port `5432`).

## Use cases

| Goal | Command |
|------|---------|
| Multi-beat briefing (spoken) | `uv run wirecache query --category ai --category tech --format voice --limit 8` |
| Human-readable scan | `uv run wirecache query --category tech --format text` |
| Topic watch | `uv run wirecache query --keyword NVIDIA --since 2026-07-18T12:00:00Z` |
| Agent / JSON | `uv run wirecache query --keyword CUDA --limit 20` |
| Fresh then query | `uv run wirecache query --category ai --fetch-first --format text` |
| Health check | `uv run wirecache status` |
| Import subscriptions | `uv run wirecache import-opml ~/subscriptions.opml` |
| Add a feed | `uv run wirecache add-feed --url URL --name NAME --categories tech,ai` |
| Retention | `uv run wirecache purge --days 14` |

Background refresh (cron / Hermes): `scripts/fetch.sh`.

## Output formats

- **`json`** (default) — `{ query, count, stories }` for agents and scripts
- **`text`** — scannable terminal output with URLs
- **`voice`** — speakable prose for Hermes TTS (no URLs, no markdown). wirecache does not synthesize audio.

## Your feeds stay local

| File | Role |
|------|------|
| `feeds.example.yaml` | Committed starter (includes a strong **AI** section: labs, research, digests) |
| `feeds.yaml` | **Your** registry (gitignored). Created on first run; change via CLI |

```bash
uv run wirecache list-feeds --category ai
uv run wirecache add-feed --url URL --name NAME --categories ai,tech
uv run wirecache import-opml ~/subscriptions.opml --category ai
```

Tag by primary beat: AI-primary feeds get `ai`; general tech stays `tech` only. Full agent procedures: [SKILL.md](SKILL.md).

## Architecture

```
CLI  →  feeds.registry / feeds.opml
     →  fetch.rss        →  store.stories  →  PostgreSQL
     →  output (json|text|voice)
     →  docker_lifecycle
```

| Want to change… | Look in |
|-----------------|---------|
| Feed list / categories | `feeds.yaml` or `src/wirecache/feeds/` |
| How RSS is pulled | `src/wirecache/fetch/rss.py` |
| SQL / FTS / purge | `src/wirecache/store/stories.py`, `schema.sql` |
| Text / voice phrasing | `src/wirecache/output/` |
| Compose / DB | `docker-compose.yml`, `.env` |

## Hermes skill

See [SKILL.md](SKILL.md) for agent procedures. Install by placing this directory where Hermes loads skills, then call `uv run wirecache …`.

## Logging

Stdout is reserved for command results (JSON / text / voice). Logs go to **stderr** and, by default, `data/wirecache.log`.

```bash
uv run wirecache -v fetch          # DEBUG
uv run wirecache -q status         # warnings/errors only
uv run wirecache --log-file '' query --category ai   # no log file
```

Env: `WIRECACHE_LOG_LEVEL`, `WIRECACHE_LOG_FILE` (see `.env.example`).

## Development

```bash
uv sync --extra dev
uv run pytest -q
```

## License

MIT — see [LICENSE](LICENSE).
