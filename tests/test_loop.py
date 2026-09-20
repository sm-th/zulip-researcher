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

    def user_id_for_email(self, email):
        return 99  # the bot/agent id


class _BoomModes:
    def recommend(self, t):
        raise RuntimeError("boom")

    def research(self, t, resume):
        raise RuntimeError("boom")


def _cfg():
    return types.SimpleNamespace(research_stream="research", operator_email="op@example.com",
                                 zulip_api_username="bot@example.com")


def test_safe_dispatch_swallows_handler_errors():
    lp = Loop(_cfg(), zc=_FakeZulip(), modes=_BoomModes())
    lp._operator_id = 7  # skip the network lookup
    t = Trigger(stream="research", topic="q", author_id=7, message_id=1,
                is_mention=False, is_topic_start=True)
    # A raising research must not propagate — the listener keeps running.
    assert lp._safe_dispatch(t) == IGNORE


def test_operator_id_prefers_config_override():
    # A configured numeric id is used verbatim; no network lookup happens.
    class _NoLookup(_FakeZulip):
        def user_id_for_email(self, email):
            raise AssertionError("must not hit the network when operator_id is set")
    cfg = types.SimpleNamespace(research_stream="research",
                                operator_email="x@example.com", operator_id=8)
    lp = Loop(cfg, zc=_NoLookup(), modes=_BoomModes())
    assert lp.operator_id == 8


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


def test_classify_treats_a_loose_message_as_a_fresh_research():
    from zulip_researcher.loop import classify, RESEARCH, RESUME
    base = dict(stream="research", author_id=7, message_id=1, is_mention=False)
    loose = Trigger(topic="general chat", is_topic_start=False, **base)
    assert classify(loose, "research", 7) == RESEARCH   # loose -> always fresh, never resume
    reply = Trigger(topic="A real topic", is_topic_start=False, **base)
    assert classify(reply, "research", 7) == RESUME


def test_classify_researches_any_non_agent_message_in_research():
    from zulip_researcher.loop import classify, RESEARCH, IGNORE
    base = dict(stream="research", topic="general chat", message_id=1,
                is_mention=False, is_topic_start=False)
    # a post moved in from another channel keeps its original (non-operator) author
    moved = Trigger(author_id=6, **base)
    assert classify(moved, "research", operator_id=8, agent_id=99) == RESEARCH
    # the bot's own posts in #research are never acted on
    own = Trigger(author_id=99, **base)
    assert classify(own, "research", operator_id=8, agent_id=99) == IGNORE


def test_classify_recommends_only_operator_mentions():
    from zulip_researcher.loop import classify, RECOMMEND, IGNORE
    base = dict(stream="general", topic="t", message_id=1, is_mention=True, is_topic_start=True)
    assert classify(Trigger(author_id=8, **base), "research", 8, 99) == RECOMMEND
    assert classify(Trigger(author_id=6, **base), "research", 8, 99) == IGNORE
