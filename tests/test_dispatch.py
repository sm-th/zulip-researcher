"""Behavioural tests for the listener's dispatch decision (`classify`)."""

from zulip_researcher.loop import (
    IGNORE, RECOMMEND, RESEARCH, RESUME, Trigger, classify,
)

RESEARCH_STREAM = "research"
OPERATOR = 7
OTHER = 99


def _t(stream="general", author_id=OPERATOR, is_mention=False, is_topic_start=False):
    return Trigger(
        stream=stream, topic="t", author_id=author_id, message_id=1,
        is_mention=is_mention, is_topic_start=is_topic_start,
    )


def test_mention_outside_research_recommends():
    t = _t(stream="design", is_mention=True)
    assert classify(t, RESEARCH_STREAM, OPERATOR) == RECOMMEND


def test_new_operator_topic_in_research_researches():
    t = _t(stream=RESEARCH_STREAM, is_topic_start=True)
    assert classify(t, RESEARCH_STREAM, OPERATOR) == RESEARCH


def test_operator_reply_in_research_resumes():
    t = _t(stream=RESEARCH_STREAM, is_topic_start=False)
    assert classify(t, RESEARCH_STREAM, OPERATOR) == RESUME


def test_non_operator_mention_outside_research_is_ignored():
    # Only the operator can summon Recommendations from outside #research.
    assert classify(_t(stream="design", author_id=OTHER, is_mention=True),
                    RESEARCH_STREAM, OPERATOR) == IGNORE


def test_any_non_agent_post_in_research_researches():
    # #research is the operator's queue: a post moved in from another channel (a
    # different author) still becomes research; only the bot's own posts are skipped.
    assert classify(_t(stream=RESEARCH_STREAM, author_id=OTHER, is_topic_start=True),
                    RESEARCH_STREAM, OPERATOR, agent_id=123) == RESEARCH
    assert classify(_t(stream=RESEARCH_STREAM, author_id=123, is_topic_start=True),
                    RESEARCH_STREAM, OPERATOR, agent_id=123) == IGNORE


def test_plain_message_without_mention_is_ignored():
    t = _t(stream="random", is_mention=False)
    assert classify(t, RESEARCH_STREAM, OPERATOR) == IGNORE


def test_mention_inside_research_still_researches_not_recommends():
    # In #research the stream rule wins; a mention there does not trigger Recommend.
    t = _t(stream=RESEARCH_STREAM, is_mention=True, is_topic_start=True)
    assert classify(t, RESEARCH_STREAM, OPERATOR) == RESEARCH
