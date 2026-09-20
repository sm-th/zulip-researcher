"""The listener must survive a failing or not-yet-wired mode."""

import types

from zulip_researcher.loop import IGNORE, Loop, Trigger


class _FakeZulip:
    def get_stream_id(self, name):
        return 1

    def message_reactions(self, message_id):
        return []

    def add_reaction(self, *a):
        pass

    def remove_reaction(self, *a):
        pass


class _BoomModes:
    def recommend(self, t):
        raise RuntimeError("boom")

    def research(self, t, resume):
        raise RuntimeError("boom")


def _cfg():
    return types.SimpleNamespace(research_stream="research")


def test_safe_dispatch_swallows_handler_errors():
    lp = Loop(_cfg(), zc=_FakeZulip(), modes=_BoomModes())
    lp._operator_id = 7  # skip the network lookup
    t = Trigger(stream="research", topic="q", author_id=7, message_id=1,
                is_mention=False, is_topic_start=True)
    # A raising research must not propagate — the listener keeps running.
    assert lp._safe_dispatch(t) == IGNORE
