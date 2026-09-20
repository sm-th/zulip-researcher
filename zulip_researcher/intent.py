"""The intent step: read what the operator dropped and decide the research task.

A message in `#research` is usually a link (sometimes with a short note). One omp
ask turns it into a thread `title` and a single self-contained `question` — a link
means "ingest that source". This is deliberately not the `prepare` service (which
only normalizes prose); intent is about *what the research is*, not how it reads.
"""

from __future__ import annotations

import json
from typing import Callable

from . import omp

Ask = Callable[[str], str]

TITLE_MAX = 72
QUESTION_MAX = 300

SYSTEM = (
    "You read a message dropped into a research chat and decide the research task. "
    "The message is usually a link, sometimes with a short note; then the task is to "
    "INGEST that source. Reply with ONLY a JSON object with two string fields:\n"
    '  "title": a short thread label, at most 72 characters — for a link, name the '
    'source subject, e.g. "Ingest: <subject>";\n'
    '  "question": one self-contained, coherent research question, at most 300 '
    "characters, phrased as a question (never a title plus a body).\n"
    "No prose and no code fences — just the JSON object."
)


def derive(message: str, *, ask: Ask | None = None) -> tuple[str, str]:
    """Return (title, question) for `message`, falling back to the message text
    when the intent step is unavailable or returns nothing usable."""
    ask = ask or (lambda task: omp.ask(task))
    try:
        raw = ask(f"{SYSTEM}\n\nMessage:\n{message}")
    except Exception:
        raw = ""
    title, question = _parse(raw)
    fallback = " ".join((message or "").split()).strip()
    return (title or fallback[:TITLE_MAX] or "research",
            question or fallback[:QUESTION_MAX] or "research")


def _parse(raw: str) -> tuple[str, str]:
    obj = _json_object(raw)
    title = str(obj.get("title") or "").strip().strip('"')[:TITLE_MAX].strip()
    question = str(obj.get("question") or "").strip().strip('"')[:QUESTION_MAX].strip()
    return title, question


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
