"""Speakable prose for Hermes TTS — no audio synthesis here.

Natural narrative only: no numbered lists, no leading story counts.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _number_word(n: int) -> str:
    words = {
        0: "zero",
        1: "one",
        2: "two",
        3: "three",
        4: "four",
        5: "five",
        6: "six",
        7: "seven",
        8: "eight",
        9: "nine",
        10: "ten",
    }
    return words.get(n, str(n))


def _relative_spoken(iso: str | None) -> str:
    if not iso:
        return "recently"
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        seconds = int((datetime.now(timezone.utc) - dt).total_seconds())
        if seconds < 0:
            return "just now"
        if seconds < 3600:
            mins = max(1, seconds // 60)
            unit = "minute" if mins == 1 else "minutes"
            return f"{_number_word(mins) if mins <= 10 else mins} {unit} ago"
        if seconds < 86400:
            hours = max(1, seconds // 3600)
            unit = "hour" if hours == 1 else "hours"
            return f"{_number_word(hours) if hours <= 10 else hours} {unit} ago"
        days = max(1, seconds // 86400)
        unit = "day" if days == 1 else "days"
        return f"{_number_word(days) if days <= 10 else days} {unit} ago"
    except ValueError:
        return "recently"


def _window_spoken(query: dict) -> str:
    if "since" in query:
        return "since your last check"
    if "days" in query:
        d = query["days"]
        if d == 1:
            return "from the last day"
        return f"from the last {_number_word(d) if d <= 10 else d} days"
    hours = query.get("hours", 24)
    if hours == 24:
        return "from the last day"
    if hours == 1:
        return "from the last hour"
    return f"from the last {_number_word(hours) if hours <= 10 else hours} hours"


_TOPIC_LABELS = {
    "ai": "AI",
    "tech": "tech",
    "mac": "Mac",
    "us-news": "US news",
    "world-news": "world news",
    "us-politics": "US politics",
    "world-politics": "world politics",
    "business": "business",
}


def _label_cat(cat: str) -> str:
    return _TOPIC_LABELS.get(cat, cat.replace("-", " "))


def _topic_spoken(query: dict) -> str:
    cats = query.get("categories") or query.get("category")
    if cats:
        if isinstance(cats, list):
            labels = [_label_cat(c) for c in cats]
            if len(labels) == 1:
                return labels[0]
            if len(labels) == 2:
                return f"{labels[0]} and {labels[1]}"
            return ", ".join(labels[:-1]) + f", and {labels[-1]}"
        return _label_cat(str(cats))
    if query.get("keyword"):
        return f"on {query['keyword']}"
    if query.get("source"):
        return f"from {query['source']}"
    return "news"


def _a_or_an(phrase: str) -> str:
    head = phrase.strip().split()[0] if phrase.strip() else ""
    return "an" if head[:1].lower() in "aeiou" else "a"


def _clean_summary(summary: str) -> str:
    import re

    summary = summary.split("http")[0].strip()
    # Drop HN / Reddit feed chrome that TTS would read aloud
    summary = re.sub(
        r"(?i)\b(article url|comments url|points|comments)\s*:?\s*$",
        "",
        summary,
    ).strip()
    summary = re.sub(r"(?i)\b(article url|comments url)\s*:?\s*", "", summary).strip()
    if len(summary) > 160:
        summary = summary[:157].rsplit(" ", 1)[0] + "."
    if summary and not summary.endswith("."):
        summary += "."
    return summary



def _story_sentence(story: dict) -> str:
    title = (story.get("title") or "Untitled story").rstrip(".")
    source = story.get("source") or "an unknown source"
    when = _relative_spoken(story.get("published"))
    summary = _clean_summary((story.get("summary") or "").strip())
    if summary:
        return f"{title}, from {source}, {when}. {summary}"
    return f"{title}, from {source}, {when}."


def render(payload: dict[str, Any]) -> str:
    query = payload.get("query") or {}
    stories = payload.get("stories") or []
    count = payload.get("count", len(stories))

    topic = _topic_spoken(query)
    window = _window_spoken(query)

    if count == 0:
        return f"There are no {topic} stories {window}.\n"

    # Natural briefing — no "Six stories", no "1. 2. 3."
    article = _a_or_an(topic)
    parts = [f"Here's {article} {topic} briefing {window}."]
    for story in stories:
        parts.append(_story_sentence(story))
    parts.append("That's the briefing for now.")

    return " ".join(parts) + "\n"
