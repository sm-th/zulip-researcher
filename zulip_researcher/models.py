"""Small shared types."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# A raw Zulip message as returned by the SDK (apply_markdown=False).
ZulipMessage = dict[str, Any]


@dataclass
class PreparedDocument:
    """Result of the preparation interface: operator's text normalized to clean, publishable markdown."""

    fingerprint: str
    policy: str
    title: str | None
    body: str
    cache_hit: bool | None = None
