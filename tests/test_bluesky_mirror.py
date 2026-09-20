"""Behavioural tests for the Bluesky mirror (git/Zulip/prepare faked, no network)."""

import json
import os
import types

from zulip_researcher.bluesky_mirror import BlueskyMirror

OPERATOR_ID = 7
AGENT_ID = 42
OTHER_ID = 99


class FakeGit:
    """Records `_git`/`_auth_url` calls; a "clone" materializes a `.git` marker
    on disk so a second sync sees the repo as already cloned."""

    def __init__(self):
        self.calls = []

    def _auth_url(self, repo_url, token):
        return f"{repo_url}#{token}"

    def _git(self, args, cwd):
        self.calls.append((tuple(args), cwd))
        if args[0] == "clone":
            os.makedirs(os.path.join(args[2], ".git"), exist_ok=True)
        return ""


class FakeZulip:
    def __init__(self, messages, user_ids):
        self._messages = messages
        self._user_ids = user_ids

    def get_stream_id(self, name):
        return 1

    def get_messages(self, stream_id, topic):
        return self._messages

    def user_id_for_email(self, email):
        return self._user_ids[email]


class FakePrepare:
    def __init__(self):
        self.calls = []

    def prepare(self, body, **kwargs):
        self.calls.append(body)
        return types.SimpleNamespace(body=f"PREPARED: {body}")


def _cfg(tmp_path):
    return types.SimpleNamespace(
        bluesky_operator_repo_url="https://github.com/o/operator.git",
        bluesky_agent_repo_url="https://github.com/o/agent.git",
        bluesky_clone_dir=str(tmp_path / "bluesky"),
        bluesky_posts_subdir="posts",
        bluesky_branch="main",
        git_user_name="A",
        git_user_email="a@example.com",
        push_token="tok",
        bluesky_operator_push_token="tok",
        bluesky_agent_push_token="tok",
        operator_email="andy@example.com",
        zulip_api_username="research-bot@example.com",
        prepare_url="https://prepare.example.com",
        prepare_token="ptok",
    )


def _mirror(tmp_path, messages):
    cfg = _cfg(tmp_path)
    user_ids = {cfg.operator_email: OPERATOR_ID, cfg.zulip_api_username: AGENT_ID}
    zc = FakeZulip(messages, user_ids)
    git = FakeGit()
    prepare = FakePrepare()
    m = BlueskyMirror(cfg, zc, prepare=prepare, git=git)
    return m, git, prepare, cfg


def _seed_published(clone_dir, slug, uri="at://did:plc:seed/app.bsky.feed.post/1"):
    """Pre-populate an already-cloned, already-published post on disk."""
    posts = os.path.join(clone_dir, "posts")
    os.makedirs(os.path.join(clone_dir, ".git"), exist_ok=True)
    os.makedirs(posts, exist_ok=True)
    with open(os.path.join(posts, f"{slug}.md"), "w") as f:
        f.write("---\n---\n\nseed\n")
    with open(os.path.join(posts, f"{slug}.state.json"), "w") as f:
        json.dump({"uri": uri}, f)
    return uri


def _seed_unpublished(clone_dir, slug):
    """Pre-populate a committed-but-not-yet-published post (no state file)."""
    posts = os.path.join(clone_dir, "posts")
    os.makedirs(os.path.join(clone_dir, ".git"), exist_ok=True)
    os.makedirs(posts, exist_ok=True)
    with open(os.path.join(posts, f"{slug}.md"), "w") as f:
        f.write("---\n---\n\nseed\n")


def test_root_operator_message_commits_to_operator_repo_prepared_no_reply_to(tmp_path):
    messages = [{"id": 100, "sender_id": OPERATOR_ID, "content": "Do rebuilds dominate?"}]
    m, git, prepare, cfg = _mirror(tmp_path, messages)

    m.mirror_topic("research", "topic")

    operator_dir = os.path.join(cfg.bluesky_clone_dir, "operator")
    agent_dir = os.path.join(cfg.bluesky_clone_dir, "agent")
    post_path = os.path.join(operator_dir, "posts", "zulip-100.md")
    assert os.path.exists(post_path)
    content = open(post_path).read()
    assert content == "---\n---\n\nPREPARED: Do rebuilds dominate?\n"
    assert "reply_to" not in content
    assert prepare.calls == ["Do rebuilds dominate?"]
    assert not os.path.isdir(agent_dir)  # agent repo never touched
    pushes = [c for c in git.calls if c[0][0] == "push" and c[1] == operator_dir]
    assert len(pushes) == 1


def test_agent_reply_threads_under_published_operator_post(tmp_path):
    operator_dir = os.path.join(_cfg(tmp_path).bluesky_clone_dir, "operator")
    uri = _seed_published(operator_dir, "zulip-100")
    messages = [
        {"id": 100, "sender_id": OPERATOR_ID, "content": "Do rebuilds dominate?"},
        {"id": 101, "sender_id": AGENT_ID, "content": "Rarely, unless CI is I/O bound."},
    ]
    m, git, prepare, cfg = _mirror(tmp_path, messages)

    m.mirror_topic("research", "topic")

    agent_dir = os.path.join(cfg.bluesky_clone_dir, "agent")
    post_path = os.path.join(agent_dir, "posts", "zulip-101.md")
    assert os.path.exists(post_path)
    content = open(post_path).read()
    assert content == f"---\nreply_to: {uri}\n---\n\nRarely, unless CI is I/O bound.\n"
    assert prepare.calls == []  # agent text is used as-is, never prepared
    # message 100's post file was not rewritten (already published, left alone)
    assert open(os.path.join(operator_dir, "posts", "zulip-100.md")).read() == "---\n---\n\nseed\n"


def test_already_mirrored_messages_are_skipped_and_chain_advances(tmp_path):
    cfg0 = _cfg(tmp_path)
    operator_dir = os.path.join(cfg0.bluesky_clone_dir, "operator")
    agent_dir = os.path.join(cfg0.bluesky_clone_dir, "agent")
    _seed_published(operator_dir, "zulip-100", uri="at://did:plc:seed/app.bsky.feed.post/1")
    second_uri = _seed_published(agent_dir, "zulip-101", uri="at://did:plc:seed/app.bsky.feed.post/2")
    messages = [
        {"id": 100, "sender_id": OPERATOR_ID, "content": "Q1"},
        {"id": 101, "sender_id": AGENT_ID, "content": "A1"},
        {"id": 102, "sender_id": OPERATOR_ID, "content": "Follow-up"},
    ]
    m, git, prepare, cfg = _mirror(tmp_path, messages)

    m.mirror_topic("research", "topic")

    # the third message threads under the SECOND published post, not the first
    post_path = os.path.join(operator_dir, "posts", "zulip-102.md")
    content = open(post_path).read()
    assert content == f"---\nreply_to: {second_uri}\n---\n\nPREPARED: Follow-up\n"
    # the two already-published posts were never rewritten
    assert not any(c[0][0] == "commit" for c in git.calls if "zulip-100" in str(c) or "zulip-101" in str(c))


def test_stops_when_predecessor_committed_but_not_yet_published(tmp_path):
    cfg0 = _cfg(tmp_path)
    operator_dir = os.path.join(cfg0.bluesky_clone_dir, "operator")
    agent_dir = os.path.join(cfg0.bluesky_clone_dir, "agent")
    _seed_unpublished(operator_dir, "zulip-100")
    messages = [
        {"id": 100, "sender_id": OPERATOR_ID, "content": "Q1"},
        {"id": 101, "sender_id": AGENT_ID, "content": "A1"},
    ]
    m, git, prepare, cfg = _mirror(tmp_path, messages)

    m.mirror_topic("research", "topic")

    # the agent's reply is never attempted: its parent isn't published yet
    assert not os.path.isdir(agent_dir)
    assert not any(c[0][0] == "commit" for c in git.calls)
    assert prepare.calls == []


def test_other_users_are_ignored_and_never_break_the_chain(tmp_path):
    cfg0 = _cfg(tmp_path)
    operator_dir = os.path.join(cfg0.bluesky_clone_dir, "operator")
    uri = _seed_published(operator_dir, "zulip-100")
    messages = [
        {"id": 100, "sender_id": OPERATOR_ID, "content": "Q1"},
        {"id": 150, "sender_id": OTHER_ID, "content": "unrelated chatter"},
        {"id": 101, "sender_id": AGENT_ID, "content": "A1"},
    ]
    m, git, prepare, cfg = _mirror(tmp_path, messages)

    m.mirror_topic("research", "topic")

    agent_dir = os.path.join(cfg.bluesky_clone_dir, "agent")
    # the other user's message never becomes a post anywhere
    assert not os.path.exists(os.path.join(operator_dir, "posts", "zulip-150.md"))
    assert not os.path.exists(os.path.join(agent_dir, "posts", "zulip-150.md"))
    # the agent's reply threads directly under the operator's post, skipping message 150
    content = open(os.path.join(agent_dir, "posts", "zulip-101.md")).read()
    assert content == f"---\nreply_to: {uri}\n---\n\nA1\n"
