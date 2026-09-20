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


class _StopLoop(Exception):
    pass


class _RegisteringZulip(_FakeZulip):
    """Records register_event_queue kwargs, then aborts the loop deterministically."""

    def __init__(self):
        self.register_calls = []

    def get_topics(self, stream_id):
        return []

    def register_event_queue(self, **kwargs):
        self.register_calls.append(kwargs)
        return {"queue_id": "q1", "last_event_id": 0}

    def get_events(self, queue_id, last_event_id):
        raise _StopLoop()


class _NoopModes:
    def recommend(self, t):
        pass

    def research(self, t, resume):
        pass


def test_run_registers_event_queue_with_all_public_streams():
    zc = _RegisteringZulip()
    lp = Loop(_cfg(), zc=zc, modes=_NoopModes())
    lp._operator_id = 7
    try:
        lp.run()
    except _StopLoop:
        pass
    assert zc.register_calls
    assert zc.register_calls[0]["all_public_streams"] is True
