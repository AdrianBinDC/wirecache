# What wirecache can do

Curated RSS feeds → local PostgreSQL cache → ask for headlines.  
Built so an agent (or you) gets **source-bounded news** without wandering the open web.

## In one sentence

wirecache remembers the feeds you trust, refreshes them on demand, and answers with what’s in the cache — as a readable list, speakable briefing, or JSON for the agent.

## You can ask for…

- **Headlines by beat** — AI, tech, Mac, business, US/world news & politics (plus any categories you add)
- **Keyword watch** — e.g. stories mentioning CUDA or NVIDIA in a time window
- **A spoken briefing** — short prose meant for TTS (no URL soup)
- **Freshness** — pull feeds first when you care about “latest”
- **Feed management** — list, add, update, remove feeds; import OPML; keep categories high-signal
- **Housekeeping** — status (is Postgres up? any dead feeds?), purge old stories

## How results come back

| Form | Best for |
|------|----------|
| **Readable list** | Skimming with titles and links |
| **Speakable briefing** | Hermes TTS / Telegram voice |
| **JSON** | Agent filtering, near-dedupe, further reasoning |

## What it will not do

- Search the open web for “today’s news” (that’s the opposite of the product)
- Invent RSS URLs you didn’t provide (or import via OPML)
- Synthesize audio itself — it only prepares text; **Hermes** does TTS
- Fuzzy-merge the same event from many outlets — the agent should near-dedupe when presenting

## Natural ways to start (talk to Hermes)

- “What’s in AI news?”
- “Spoken tech briefing”
- “Anything about CUDA since noon?”
- “List my AI feeds”
- “Add this RSS feed under ai”
- “Import this OPML”

## Under the hood (one breath)

CLI + Dockerized Postgres. Categories tag feeds; query filters by category, keyword, source, and time. Exact URL dedupe on insert; same-story near-dedupe when presenting is the agent’s job.

For command flags and procedures, see `SKILL.md` or `uv run wirecache --help`.
