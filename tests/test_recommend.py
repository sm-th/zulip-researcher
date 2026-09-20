"""Behavioural tests for Recommend mode and omp NDJSON parsing."""

from zulip_researcher import omp
from zulip_researcher.loop import Trigger
from zulip_researcher.recommend import Recommend


class FakeZulip:
    def __init__(self, messages):
        self._messages = messages
        self.sent = []

    def get_stream_id(self, name):
        return 10

    def get_messages(self, stream_id, topic, **kw):
        return self._messages

    def send_message(self, stream_id, topic, content):
        self.sent.append((stream_id, topic, content))
        return 1


def _mention(stream="design", topic="agents"):
    return Trigger(stream=stream, topic=topic, author_id=7, message_id=1,
                   is_mention=True, is_topic_start=False)


def test_recommend_posts_candidate_questions_into_thread():
    msgs = [
        {"sender_full_name": "A", "content": "We keep rebuilding agent images."},
        {"sender_full_name": "A", "content": "Is that the real bottleneck?"},
    ]
    zc = FakeZulip(msgs)
    seen = {}

    def fake_ask(task):
        seen["task"] = task
        return "- When do image rebuilds dominate?\n2. How often do envs churn?\n"

    Recommend(cfg=object(), zc=zc, omp_ask=fake_ask).recommend(_mention())

    assert len(zc.sent) == 1
    _sid, topic, body = zc.sent[0]
    assert topic == "agents"
    assert "When do image rebuilds dominate?" in body
    assert "How often do envs churn?" in body      # numbering stripped
    assert "#research" in body
    assert "real bottleneck" in seen["task"]        # discussion reached omp


def test_recommend_ignores_empty_thread():
    zc = FakeZulip([])
    Recommend(cfg=object(), zc=zc, omp_ask=lambda task: "Q?").recommend(_mention())
    assert zc.sent == []


def test_recommend_ignores_when_no_questions():
    zc = FakeZulip([{"sender_full_name": "A", "content": "hi"}])
    Recommend(cfg=object(), zc=zc, omp_ask=lambda task: "   \n\n").recommend(_mention())
    assert zc.sent == []


def test_assistant_text_extracts_from_ndjson():
    nd = "\n".join([
        '{"type":"message_start"}',
        '{"type":"tool_use"}',
        '{"type":"message_end","message":{"role":"assistant",'
        '"content":[{"type":"text","text":"Q1\\nQ2"}]}}',
    ])
    assert omp.assistant_text(nd) == "Q1\nQ2"
