"""The intent step: name the thread a dropped message starts.

A message in `#research` is usually a link (sometimes with a short note). One omp
ask turns it into a short thread `title` — for orientation only. The research
itself works from the message body verbatim, never a reformulation. Deliberately
not the `prepare` service (which normalizes prose); intent only labels the thread.
"""

from __future__ import annotations

import json
from typing import Callable

from . import omp

Ask = Callable[[str], str]

TITLE_MAX = 72

SYSTEM = (
    "You read a message dropped into a research chat and name the thread it starts. "
    "The message is usually a link, sometimes with a short note. Reply with ONLY a "
    "JSON object with one string field:\n"
    '  "title": a short thread label, at most 72 characters — for a link, name the '
    'source subject, e.g. "Ingest: <subject>".\n'
    "No prose and no code fences — just the JSON object."
)


def derive(message: str, *, ask: Ask | None = None) -> str:
    """Return a short thread title for `message`, falling back to the message text
    when the intent step is unavailable or returns nothing usable."""
    ask = ask or (lambda task: omp.ask(task))
    try:
        raw = ask(f"{SYSTEM}\n\nMessage:\n{message}")
    except Exception:
        raw = ""
    title = _parse_title(raw)
    fallback = " ".join((message or "").split()).strip()
    return title or fallback[:TITLE_MAX] or "research"


def _parse_title(raw: str) -> str:
    obj = _json_object(raw)
    return str(obj.get("title") or "").strip().strip('"')[:TITLE_MAX].strip()


def _json_object(raw: str) -> dict:
    """The first JSON object in `raw` (LLMs sometimes wrap it in prose/fences)."""
    if not raw:
        return {}
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        return {}
    try:
        obj = json.loads(raw[start:end + 1])
    except json.JSONDecodeError:
        return {}
    return obj if isinstance(obj, dict) else {}
