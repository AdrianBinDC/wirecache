#!/bin/bash
# Background fetch wrapper for cronjob.
# Runs fetch silently; only outputs on errors.
set -euo pipefail

# Cron environments may lack ~/.local/bin — source profile if possible
if [ -f /home/abolinger/.bashrc ]; then
    source /home/abolinger/.bashrc 2>/dev/null || true
fi

SCRIPT_DIR="/home/abolinger/Developer/news-fetcher/scripts"

# Run fetch, capture stdout
output=$(/home/abolinger/.local/bin/uv run "$SCRIPT_DIR/news.py" fetch 2>/dev/null) || {
    echo "news-fetch cron: fetch failed" >&2
    exit 1
}

# Extract inserted count
inserted=$(echo "$output" | /usr/bin/python3 -c "import sys,json; print(json.load(sys.stdin).get('inserted', 0))" 2>/dev/null || echo 0)

# Only announce if there are new stories (reduces noise)
if [ "$inserted" -gt 0 ]; then
    echo "news-fetch: $inserted new stories"
else
    # Silent — nothing new
    exit 0
fi
