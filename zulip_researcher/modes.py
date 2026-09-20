"""The two behaviours the listener dispatches to, and how to build them.

Recommend reads a mentioned thread and posts candidate Questions back into it. Research
runs one deep Research for a #research topic, publishing to the wiki via PR.
"""

from __future__ import annotations

from typing import Protocol

from . import config, zulip
from .loop import Trigger
from .recommend import Recommend
from .research import Research


class Modes(Protocol):
    def recommend(self, t: Trigger) -> None: ...
    def research(self, t: Trigger, resume: bool) -> None: ...


class _Modes:
    def __init__(self, recommend: Recommend, research: Research):
        self._recommend = recommend
        self._research = research

    def recommend(self, t: Trigger) -> None:
        self._recommend.recommend(t)

    def research(self, t: Trigger, resume: bool) -> None:
        self._research.research(t, resume)


def build(cfg: config.Config, zc: "zulip.Zulip | None" = None) -> _Modes:
    zc = zc or zulip.Zulip(cfg.zulip_url, cfg.zulip_api_key, cfg.zulip_api_username)
    return _Modes(Recommend(cfg, zc), Research(cfg, zc))
