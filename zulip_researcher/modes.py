"""The two behaviours the listener dispatches to, and how to build them.

Recommend reads a mentioned thread and posts candidate Questions back into it. Research
runs one Research for a #research topic; its implementation lands in issue #4.
"""

from __future__ import annotations

from typing import Protocol

from . import config, zulip
from .loop import Trigger
from .recommend import Recommend


class Modes(Protocol):
    def recommend(self, t: Trigger) -> None: ...
    def research(self, t: Trigger, resume: bool) -> None: ...


class _Research:
    def research(self, t: Trigger, resume: bool) -> None:
        raise NotImplementedError("Research mode lands in issue #4")


class _Modes:
    def __init__(self, recommend: Recommend):
        self._recommend = recommend
        self._research = _Research()

    def recommend(self, t: Trigger) -> None:
        self._recommend.recommend(t)

    def research(self, t: Trigger, resume: bool) -> None:
        self._research.research(t, resume)


def build(cfg: config.Config, zc: "zulip.Zulip | None" = None) -> _Modes:
    zc = zc or zulip.Zulip(cfg.zulip_url, cfg.zulip_api_key, cfg.zulip_api_username)
    return _Modes(Recommend(cfg, zc))
