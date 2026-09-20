"""Mirror a `#research` topic to Bluesky as a dual-identity reply-thread.

Each Zulip message in the topic becomes one Bluesky post under its author's
identity: the operator's messages publish from the operator's Bluesky repo,
the agent's from the agent's (ADR-0005), each threaded as a reply to the
previous mirrored message via that post's published AT-URI. Any other
sender is not mirrored.

Stateless (ADR-0003): whether a message has already been mirrored, and what
it published as, are read back from the target repo on every pass, never
from a local store — `posts/<slug>.md` existing means it has been committed;
`posts/<slug>.state.json`'s `uri` field (written by that repo's own publish
CI, see the bluesky-publisher DESIGN) means it has actually published. A
post's own AT-URI is unknown until its CI runs, so a pass mirrors at most one
new message per identity chain and stops — the reply that would thread under
it waits for a later pass.

Reuses `wiki._git`/`wiki._auth_url` for the git plumbing: clone-or-pull the
target repo's branch, write one post file, commit, push. Same HTTPS+PAT
git-over-subprocess pattern as the wiki publisher (`wiki.py`).
"""

from __future__ import annotations

import json
import os

from . import config, wiki, zulip
from .prepare import PreparationClient

OPERATOR = "operator"
AGENT = "agent"

# A Zulip message whose raw content carries this sentinel is never mirrored to
# Bluesky (e.g. research follow-ups). Zulip strips HTML comments from the rendered
# message, so it is invisible in chat but present in the apply_markdown=False body.
NO_MIRROR = "<!-- no-mirror -->"


class BlueskyMirrorError(RuntimeError):
    pass


def _slug(message_id: int) -> str:
    return f"zulip-{message_id}"


def _post_file(reply_to: str | None, body: str) -> str:
    lines = ["---"]
    if reply_to:
        lines.append(f"reply_to: {reply_to}")
    lines.append("---")
    lines.append("")
    lines.append(body.strip())
    lines.append("")
    return "\n".join(lines)


class BlueskyMirror:
    """Mirrors one `#research` topic's messages to Bluesky, oldest-first."""

    def __init__(self, cfg: config.Config, zc: "zulip.Zulip",
                 prepare: "PreparationClient | None" = None, git=wiki):
        self.cfg = cfg
        self.zc = zc
        self.prepare = prepare or PreparationClient(cfg.prepare_url, cfg.prepare_token)
        self.git = git
        self._operator_id: int | None = None
        self._agent_id: int | None = None
        self._synced: set[str] = set()

    @property
    def operator_id(self) -> int:
        if self._operator_id is None:
            self._operator_id = self.cfg.operator_id or self.zc.user_id_for_email(self.cfg.operator_email)
        return self._operator_id

    @property
    def agent_id(self) -> int:
        if self._agent_id is None:
            self._agent_id = self.zc.user_id_for_email(self.cfg.zulip_api_username)
        return self._agent_id

    def _identity(self, sender_id: int | None) -> str | None:
        if sender_id == self.operator_id:
            return OPERATOR
        if sender_id == self.agent_id:
            return AGENT
        return None

    def _repo(self, identity: str) -> tuple[str, str, str]:
        """(repo_url, clone_dir, push_token) for the identity's Bluesky repo."""
        cfg = self.cfg
        if identity == OPERATOR:
            return (cfg.bluesky_operator_repo_url,
                    os.path.join(cfg.bluesky_clone_dir, OPERATOR),
                    cfg.bluesky_operator_push_token)
        return (cfg.bluesky_agent_repo_url,
                os.path.join(cfg.bluesky_clone_dir, AGENT),
                cfg.bluesky_agent_push_token)

    def _sync(self, repo_url: str, clone_dir: str, token: str) -> None:
        """Clone-or-pull the target repo's branch, once per mirror pass."""
        if clone_dir in self._synced:
            return
        cfg = self.cfg
        auth = self.git._auth_url(repo_url, token)
        if not os.path.isdir(os.path.join(clone_dir, ".git")):
            parent = os.path.dirname(clone_dir.rstrip("/")) or "."
            os.makedirs(parent, exist_ok=True)
            self.git._git(["clone", auth, clone_dir], cwd=parent)
        else:
            self.git._git(["remote", "set-url", "origin", auth], cwd=clone_dir)
        self.git._git(["config", "user.name", cfg.git_user_name], cwd=clone_dir)
        self.git._git(["config", "user.email", cfg.git_user_email], cwd=clone_dir)
        self.git._git(["fetch", "origin", cfg.bluesky_branch], cwd=clone_dir)
        self.git._git(["checkout", "-B", cfg.bluesky_branch, f"origin/{cfg.bluesky_branch}"],
                       cwd=clone_dir)
        self._synced.add(clone_dir)

    def _post_path(self, clone_dir: str, slug: str) -> str:
        return os.path.join(clone_dir, self.cfg.bluesky_posts_subdir, f"{slug}.md")

    def _state_path(self, clone_dir: str, slug: str) -> str:
        return os.path.join(clone_dir, self.cfg.bluesky_posts_subdir, f"{slug}.state.json")

    def _published_uri(self, clone_dir: str, slug: str) -> str | None:
        path = self._state_path(clone_dir, slug)
        if not os.path.exists(path):
            return None
        with open(path, encoding="utf-8") as f:
            return (json.load(f) or {}).get("uri")

    def _write_and_push(self, clone_dir: str, slug: str, message_id: int,
                         body: str, reply_to: str | None) -> None:
        path = self._post_path(clone_dir, slug)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(_post_file(reply_to, body))
        self.git._git(["add", "-A"], cwd=clone_dir)
        self.git._git(["commit", "-m", f"mirror zulip:{message_id}"], cwd=clone_dir)
        self.git._git(["push", "origin", self.cfg.bluesky_branch], cwd=clone_dir)

    def mirror_topic(self, stream: str, topic: str) -> None:
        """Mirror `stream`/`topic` to Bluesky, committing at most one new post.

        Walks messages oldest-first. Every already-published message advances
        the reply chain (its AT-URI becomes the parent for the next mirrored
        message). The first not-yet-mirrored operator/agent message is
        committed — as the thread root, or as a reply to the chain's current
        AT-URI — and the walk stops there: that post's own AT-URI is unknown
        until its identity's CI publishes it, so nothing after it can thread
        yet. A message whose post file exists but hasn't published yet also
        stops the walk (retried next pass); other senders are skipped and
        never break the chain.
        """
        stream_id = self.zc.get_stream_id(stream)
        prev_at_uri: str | None = None
        for m in self.zc.get_messages(stream_id, topic):
            if NO_MIRROR in (m.get("content") or ""):
                continue  # e.g. research follow-ups: never mirrored
            identity = self._identity(m.get("sender_id"))
            if identity is None:
                continue
            message_id = m["id"]
            slug = _slug(message_id)
            repo_url, clone_dir, token = self._repo(identity)
            self._sync(repo_url, clone_dir, token)

            if os.path.exists(self._post_path(clone_dir, slug)):
                uri = self._published_uri(clone_dir, slug)
                if uri is None:
                    return  # committed but not yet published; retry next pass
                prev_at_uri = uri
                continue

            body = m.get("content", "")
            if identity == OPERATOR:
                body = self.prepare.prepare(body).body
            self._write_and_push(clone_dir, slug, message_id, body, prev_at_uri)
            return  # this post's own AT-URI is unknown until its CI publishes it


__all__ = ["BlueskyMirror", "BlueskyMirrorError"]
