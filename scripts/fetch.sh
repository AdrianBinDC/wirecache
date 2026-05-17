#!/bin/bash
# Background fetch wrapper for cronjob.
# Runs fetch silently; only outputs on errors.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"

# Run fetch, capture stdout
output=$(uv run "$SCRIPT_DIR/news.py" fetch 2>/dev/null) || {
    echo "news-fetch cron: fetch failed"
    exit 1
}

# Extract inserted count
inserted=$(echo "$output" | python3 -c "import sys,json; print(json.load(sys.stdin).get('inserted', 0))" 2>/dev/null || echo 0)

# Only announce if there are new stories (reduces noise)
if [ "$inserted" -gt 0 ]; then
    echo "news-fetch: $inserted new stories"
else
    # Silent — nothing new
    exit 0
fi
