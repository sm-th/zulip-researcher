"""Behavioural tests for Research orchestration (omp/wiki/PR/zulip faked)."""

import re
import types

from zulip_researcher.github import repo_slug
from zulip_researcher.loop import Trigger
from zulip_researcher.research import Research, _split
from zulip_researcher.slug import slug


class FakeWiki:
    def __init__(self, changes=True):
        self.calls = []
        self._changes = changes

    def prepare(self, clone_dir, repo_url, base, branch, token, name, email, resume=False):
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
        self.moved = []
        self.edits = []
        self.messages = []

    def get_stream_id(self, name):
        return 5

    def first_message(self, stream_id, topic):
        return self._first

    def send_message(self, stream_id, topic, content):
        self.sent.append((topic, content))
        return 1

    def edit_message(self, message_id, content):
        self.edits.append((message_id, content))

    def move_message(self, message_id, topic):
        self.moved.append((message_id, topic))

    def get_messages(self, stream_id, topic):
        return self.messages

    def user_id_for_email(self, email):
        return 42


def _cfg():
    return types.SimpleNamespace(
        wiki_clone_dir="/tmp/wiki", wiki_repo_url="https://github.com/o/n.git",
        wiki_base_branch="main", push_token="tok", wiki_push_token="tok", git_user_name="A",
        git_user_email="a@example.com", wiki_site_url="https://wiki.example.com",
        research_stream="research", prepare_policy="faithful-en-v1", prepare_format="markdown",
        omp_timeout=600, zulip_api_username="bot@example.com",
    )


def test_research_publishes_pushes_and_replies():
    zc = FakeZulip({"content": "Do rebuilds dominate?"})
    fw = FakeWiki()
    prs = []
    merges = []

    def fake_open_pr(repo, *, token, head, base, title, body):
        prs.append((repo, head, base))
        return "https://github.com/o/n/pull/1"

    def fake_omp(task, **kw):
        assert kw["tools"] and kw["approval"] == "yolo" and kw["cwd"] == "/tmp/wiki"
        assert "RESEARCH THIS:\nDo rebuilds dominate?" in task   # the body drives the research
        return ('{"type":"message_end","message":{"role":"assistant","content":'
                '[{"type":"text","text":"Rebuilds rarely dominate.\\n'
                'FOLLOWUPS: When does churn matter? || Cost of rebuilds?"}]}}')

    t = Trigger(stream="research", topic="Do rebuilds dominate?", author_id=7,
                message_id=1, is_mention=False, is_topic_start=True)
    Research(_cfg(), zc, omp_run=fake_omp, wiki_ops=fw, open_pr=fake_open_pr,
             merge_pr=lambda repo, number, token: merges.append((repo, number))).research(t)

    s = slug("Do rebuilds dominate?")
    assert ("push", f"researcher/{s}") in fw.calls
    assert prs == [("o/n", f"researcher/{s}", "main")]
    assert merges == [("o/n", 1)]                        # the PR is auto-merged (published)

    assert len(zc.sent) == 2                              # receipt + separate follow-ups
    assert zc.sent[0][1] == "🔎 Researching…"
    _mid, body = zc.edits[-1]                             # edited in place to the answer
    assert "````spoiler" not in body                     # research is a full message
    assert "Rebuilds rarely dominate." in body
    assert f"https://wiki.example.com/{s}/" in body
    assert "FOLLOWUPS" not in body                       # stripped from the answer
    assert "When does churn matter?" not in body         # follow-ups are a separate message
    from zulip_researcher.bluesky_mirror import NO_MIRROR
    follow = zc.sent[1][1]
    assert "When does churn matter?" in follow and "Cost of rebuilds?" in follow
    assert NO_MIRROR in follow                            # excluded from the Bluesky mirror


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


def test_research_prompt_uses_body_and_titles_the_branch():
    zc = FakeZulip({"content": "Because containers share the kernel."})
    fw = FakeWiki()
    seen = {}

    def fake_omp(task, **kw):
        seen["task"] = task
        return ('{"type":"message_end","message":{"role":"assistant",'
                '"content":[{"type":"text","text":"ok"}]}}')

    t = Trigger(stream="research", topic="Why microVMs over containers?",
                author_id=7, message_id=1, is_mention=False, is_topic_start=True)
    Research(_cfg(), zc, omp_run=fake_omp, wiki_ops=fw,
             open_pr=lambda *a, **k: "").research(t)

    assert "RESEARCH THIS:\nBecause containers share the kernel." in seen["task"]  # body drives research
    assert ("push", f"researcher/{slug('Why microVMs over containers?')}") in fw.calls  # title names the branch


def test_research_branch_slug_is_ascii_for_a_non_ascii_title():
    zc = FakeZulip({"content": "Δοκιμή σώματος."})
    fw = FakeWiki()

    def fake_omp(task, **kw):
        return ('{"type":"message_end","message":{"role":"assistant","content":'
                '[{"type":"text","text":"ok"}]}}')

    t = Trigger(stream="research", topic="Δοκιμή τίτλος με ερώτημα;", author_id=7,
                message_id=1, is_mention=False, is_topic_start=True)
    Research(_cfg(), zc, omp_run=fake_omp, wiki_ops=fw,
             open_pr=lambda *a, **k: "").research(t)

    pushed = [branch for op, branch in fw.calls if op == "push"]
    assert len(pushed) == 1
    branch = pushed[0]
    assert branch.startswith("researcher/")
    s = branch[len("researcher/"):]
    assert s
    assert re.fullmatch(r"[a-z0-9][a-z0-9-]*", s)


def test_research_moves_untitled_message_into_auto_titled_thread():
    zc = FakeZulip({"content": "Check out https://example.com/some-article"})
    fw = FakeWiki()

    def fake_intent(task):
        return '{"title": "Load the example link"}'

    def fake_omp(task, **kw):
        assert "RESEARCH THIS:\nCheck out https://example.com/some-article" in task
        return ('{"type":"message_end","message":{"role":"assistant","content":'
                '[{"type":"text","text":"Loaded and summarized."}]}}')

    t = Trigger(stream="research", topic="general chat", author_id=7, message_id=42,
                is_mention=False, is_topic_start=True)
    Research(_cfg(), zc, omp_run=fake_omp, wiki_ops=fw,
             open_pr=lambda *a, **k: "", omp_ask=fake_intent).research(t)

    assert zc.moved == [(42, "Load the example link")]

    s = slug("Load the example link")
    assert ("push", f"researcher/{s}") in fw.calls

    assert len(zc.sent) == 1                              # receipt posted to the new topic
    topic, _status = zc.sent[0]
    assert topic == "Load the example link"
    assert "Loaded and summarized." in zc.edits[-1][1]    # final edit carries the answer


def test_is_untitled_matches_empty_and_general_chat():
    from zulip_researcher.zulip import is_untitled
    assert is_untitled("") and is_untitled("   ")
    assert is_untitled("general chat") and is_untitled("General Chat")
    assert not is_untitled("Real research topic")


def test_slug_falls_back_to_hash_for_non_ascii_input():
    s = slug("Δοκιμή τίτλος με ερώτημα;")
    assert s
    assert re.fullmatch(r"[a-z0-9][a-z0-9-]*", s)


def test_research_ingests_attached_link():
    zc = FakeZulip({"content": "https://example.com/paper — worth a look"})
    fw = FakeWiki()
    seen = {}

    def fake_intent(task):
        return '{"title": "Ingest: Example Paper"}'

    def fake_omp(task, **kw):
        seen["task"] = task
        return ('{"type":"message_end","message":{"role":"assistant","content":'
                '[{"type":"text","text":"Summarized."}]}}')

    t = Trigger(stream="research", topic="general chat", author_id=7, message_id=9,
                is_mention=False, is_topic_start=True)
    Research(_cfg(), zc, omp_run=fake_omp, wiki_ops=fw,
             open_pr=lambda *a, **k: "", omp_ask=fake_intent).research(t)

    task = seen["task"]
    assert "https://example.com/paper" in task
    assert "to ingest" in task
    assert "type: concept" in task    # concept cards requested (issue #48)


def test_research_reports_a_failure_in_the_receipt():
    zc = FakeZulip({"content": "Do rebuilds dominate?"})
    fw = FakeWiki()

    def boom_omp(task, **kw):
        raise RuntimeError("omp timed out after 600 seconds")

    t = Trigger(stream="research", topic="Do rebuilds dominate?", author_id=7,
                message_id=1, is_mention=False, is_topic_start=True)
    raised = False
    try:
        Research(_cfg(), zc, omp_run=boom_omp, wiki_ops=fw,
                 open_pr=lambda *a, **k: "").research(t)
    except RuntimeError:
        raised = True

    assert raised                                # the failure still propagates
    assert "Research failed" in zc.edits[-1][1]  # ...but the receipt is not left hanging
    assert "omp timed out" in zc.edits[-1][1]


def test_research_reuses_an_existing_receipt_instead_of_duplicating():
    zc = FakeZulip({"content": "Do rebuilds dominate?"})
    zc.messages = [
        {"id": 500, "sender_id": 7, "content": "Do rebuilds dominate?"},
        {"id": 501, "sender_id": 42, "content": "⚠️ Research failed — earlier"},
    ]
    fw = FakeWiki()

    def fake_omp(task, **kw):
        return ('{"type":"message_end","message":{"role":"assistant","content":'
                '[{"type":"text","text":"Rarely."}]}}')

    t = Trigger(stream="research", topic="Do rebuilds dominate?", author_id=7,
                message_id=500, is_mention=False, is_topic_start=True)
    Research(_cfg(), zc, omp_run=fake_omp, wiki_ops=fw,
             open_pr=lambda *a, **k: "").research(t)

    assert zc.sent == []                              # no duplicate receipt posted
    assert zc.edits[0] == (501, "🔎 Researching…")    # the existing receipt was reused


def test_research_streams_tool_activity_and_excludes_subagents():
    from zulip_researcher.research import RESEARCH_TOOLS
    zc = FakeZulip({"content": "Do rebuilds dominate?"})
    fw = FakeWiki()

    def fake_omp(task, on_tool=None, **kw):
        assert kw["tools"] == RESEARCH_TOOLS and "task" not in RESEARCH_TOOLS  # no sub-agents
        if on_tool:
            on_tool("read", "Reading example.com/x", {})
        return ('{"type":"message_end","message":{"role":"assistant","content":'
                '[{"type":"text","text":"Done."}]}}')

    t = Trigger(stream="research", topic="Do rebuilds dominate?", author_id=7,
                message_id=1, is_mention=False, is_topic_start=True)
    Research(_cfg(), zc, omp_run=fake_omp, wiki_ops=fw,
             open_pr=lambda *a, **k: "").research(t)

    assert any("step 1" in c and "Reading example.com/x" in c for _id, c in zc.edits)
