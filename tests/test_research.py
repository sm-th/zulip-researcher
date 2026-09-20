"""Behavioural tests for Research orchestration (omp/wiki/PR/zulip faked)."""

import types

from zulip_researcher.github import repo_slug
from zulip_researcher.loop import Trigger
from zulip_researcher.research import Research, _split
from zulip_researcher.slug import slug


class FakeWiki:
    def __init__(self, changes=True):
        self.calls = []
        self._changes = changes

    def prepare(self, clone_dir, repo_url, base, branch, token, name, email):
        self.calls.append(("prepare", branch))

    def has_changes(self, clone_dir):
        return self._changes

    def commit_all(self, clone_dir, message):
        self.calls.append(("commit", message))

    def push(self, clone_dir, branch):
        self.calls.append(("push", branch))


class FakeZulip:
    def __init__(self, first):
        self._first = first
        self.sent = []

    def get_stream_id(self, name):
        return 5

    def first_message(self, stream_id, topic):
        return self._first

    def send_message(self, stream_id, topic, content):
        self.sent.append((topic, content))
        return 1


def _cfg():
    return types.SimpleNamespace(
        wiki_clone_dir="/tmp/wiki", wiki_repo_url="https://github.com/o/n.git",
        wiki_base_branch="main", push_token="tok", git_user_name="A",
        git_user_email="a@example.com", wiki_site_url="https://wiki.example.com",
        research_stream="research",
    )


def test_research_publishes_pushes_and_replies():
    zc = FakeZulip({"content": "Do rebuilds dominate?"})
    fw = FakeWiki()
    prs = []

    def fake_open_pr(repo, *, token, head, base, title, body):
        prs.append((repo, head, base))
        return "https://github.com/o/n/pull/1"

    def fake_omp(task, **kw):
        assert kw["tools"] and kw["approval"] == "yolo" and kw["cwd"] == "/tmp/wiki"
        return ('{"type":"message_end","message":{"role":"assistant","content":'
                '[{"type":"text","text":"Rebuilds rarely dominate.\\n'
                'FOLLOWUPS: When does churn matter? || Cost of rebuilds?"}]}}')

    t = Trigger(stream="research", topic="Do rebuilds dominate?", author_id=7,
                message_id=1, is_mention=False, is_topic_start=True)
    Research(_cfg(), zc, omp_run=fake_omp, wiki_ops=fw, open_pr=fake_open_pr).research(t)

    s = slug("Do rebuilds dominate?")
    assert ("push", f"researcher/{s}") in fw.calls
    assert prs == [("o/n", f"researcher/{s}", "main")]

    assert len(zc.sent) == 2
    _topic, body = zc.sent[0]
    assert "Rebuilds rarely dominate." in body
    assert f"https://wiki.example.com/{s}/" in body
    assert "FOLLOWUPS" not in body                       # stripped from the answer
    _t2, fbody = zc.sent[1]
    assert "When does churn matter?" in fbody and "Cost of rebuilds?" in fbody


def test_split_extracts_followups():
    answer, fu = _split("Short answer.\nFOLLOWUPS: a || b || c")
    assert answer == "Short answer."
    assert fu == ["a", "b", "c"]


def test_repo_slug_parses_https_and_ssh():
    assert repo_slug("https://github.com/owner/name.git") == "owner/name"
    assert repo_slug("git@github.com:owner/name.git") == "owner/name"


def test_slug_matches_eleventy_rules():
    assert slug("Do rebuilds dominate?") == "do-rebuilds-dominate"
    assert slug("  A/B & C  ") == "a-b-c"
