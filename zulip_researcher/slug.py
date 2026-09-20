"""Slugify a title the same way the wiki's Eleventy config does."""

from __future__ import annotations

import hashlib
import re


def slug(s: str) -> str:
    original = s
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    out = s.strip("-")
    if out:
        return out
    return "topic-" + hashlib.sha1(original.encode("utf-8")).hexdigest()[:10]
