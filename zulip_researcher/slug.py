"""Slugify a title the same way the wiki's Eleventy config does."""

from __future__ import annotations

import re


def slug(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")
