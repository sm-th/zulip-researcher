"""The two behaviours the listener dispatches to.

This module only defines the seam; the real, sandbox-backed implementations land in
issue #3 (Recommend) and issue #4 (Research).
"""

from __future__ import annotations

from typing import Protocol

from .loop import Trigger


class Modes(Protocol):
    def recommend(self, t: Trigger) -> None:
        """Read the mentioned thread and post candidate Questions back into it."""
        ...

    def research(self, t: Trigger, resume: bool) -> None:
        """Run one Research for a #research topic (or resume it on a reply)."""
        ...
