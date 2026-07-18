#!/usr/bin/env bash
# Background fetch wrapper for cron. Runs fetch quietly; prints only when new stories land.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if ! command -v uv >/dev/null 2>&1; then
    echo "wirecache: uv not found on PATH" >&2
    exit 1
fi

output="$(uv run wirecache fetch 2>/dev/null)" || {
    echo "wirecache: fetch failed" >&2
    exit 1
}

inserted="$(echo "$output" | python3 -c "import sys,json; print(json.load(sys.stdin).get('inserted', 0))" 2>/dev/null || echo 0)"

if [ "$inserted" -gt 0 ]; then
    echo "wirecache: $inserted new stories"
fi
