"""Research mode: run one deep, web-grounded Research for a #research topic.

The heavy lifting is omp's: it runs inside the sandbox with a full toolset, researches
the question (delegating all web reading to isolated no-access sub-agents, ADR-0007),
writes typed wiki pages, and commits. The host then pushes the branch and opens the PR
(ADR-0006), replies a short Clean answer with the page URL, and posts follow-ups, then
mirrors the topic to Bluesky (ADR-0005) — a mirror failure never breaks the reply.

Resume is stateless (ADR-0003): on an operator comment we re-run a fresh omp given the
thread transcript, based on the existing research branch (so the agent updates the page
it already wrote) — no omp session continuity.
"""

from __future__ import annotations

import re
import sys
from typing import Callable

from . import bluesky_mirror, config, github, omp, wiki, zulip
from .loop import Trigger
from .prepare import PreparationClient
from .slug import slug

SYSTEM = """You are Agent Smith, author of a public discourse-graph wiki. Research the
QUESTION and publish the result as atomic, densely [[wikilinked]] Markdown pages in the
`site/` directory of the repository at your working directory.

Method: pick the approach the question needs — evidence synthesis for empirical
questions, a landscape map for broad ones, a criteria verdict for comparisons, a
definition for concepts, positions for open questions. Ground every substantive claim in
a source: one `type: source` page per cited URL (frontmatter `url`, `author`, `date`;
title ends with the domain in parentheses), cited from a `## Sources` section. Give
`type: claim` pages an honest `status:` of established / tentative / speculative.

Safety: never open web pages yourself. Delegate all fetching and reading of web content
to isolated sub-agents that have no credentials and no repository access; work only from
the text they return.

Page frontmatter: `title`, `type` (concept/source/claim/question/moc/tool), `by`, and
optional `tags`. The core page's slug MUST be `%(slug)s`.

When done, commit your changes. Then reply with a SHORT, clean answer (no operator
context, no thread detail) for a chat thread, and on a final line list follow-up
questions exactly as: `FOLLOWUPS: question one || question two`.
"""

OmpRun = Callable[..., str]
OpenPr = Callable[..., str]
MirrorTopic = Callable[[str, str], None]


class Research:
    def __init__(self, cfg: config.Config, zc: "zulip.Zulip",
                 omp_run: OmpRun | None = None, wiki_ops=wiki,
                 open_pr: OpenPr | None = None, mirror: MirrorTopic | None = None,
                 prepare: PreparationClient | None = None):
        self.cfg = cfg
        self.zc = zc
        self.omp_run = omp_run or omp.run
        self.wiki = wiki_ops
        self.open_pr = open_pr or github.open_pr
        self.mirror = mirror or (
            lambda stream, topic: bluesky_mirror.BlueskyMirror(cfg, zc).mirror_topic(stream, topic)
        )
        self.prepare = prepare or PreparationClient(cfg.prepare_url, cfg.prepare_token)

    def _opening(self, stream_id: int, topic: str) -> str:
        first = self.zc.first_message(stream_id, topic)
        return (first or {}).get("content", "").strip()

    def _transcript(self, stream_id: int, topic: str) -> str:
        return "\n\n".join(
            f"{m.get('sender_full_name', '?')}: {m.get('content', '')}".strip()
            for m in self.zc.get_messages(stream_id, topic)
        )

    def research(self, t: Trigger, resume: bool = False) -> None:
        cfg = self.cfg
        stream_id = self.zc.get_stream_id(cfg.research_stream)
        opening = self._opening(stream_id, t.topic)
        prepared = self.prepare.prepare(body=(opening or t.topic), title=t.topic,
                                        policy=cfg.prepare_policy, fmt=cfg.prepare_format)
        question = (prepared.title or t.topic or opening).strip()
        detail = (prepared.body or "").strip()

        topic = t.topic
        if not topic.strip():
            # A loose, untitled message: move it into an auto-titled thread first.
            self.zc.move_message(t.message_id, question)
            topic = question
        s = slug(question)
        branch = f"researcher/{s}"
        receipt = self.zc.send_message(stream_id, topic, "🔎 Researching…")

        self.wiki.prepare(cfg.wiki_clone_dir, cfg.wiki_repo_url, cfg.wiki_base_branch,
                          branch, cfg.wiki_push_token, cfg.git_user_name, cfg.git_user_email,
                          resume=resume)

        task = (SYSTEM % {"slug": s}) + f"\n\nQUESTION:\n{question}\n"
        if detail and detail != question:
            task += f"\nDetails:\n{detail}\n"
        if resume:
            task += ("\nThe #research thread so far — continue from it and update the "
                     "existing page:\n\n" + self._transcript(stream_id, topic))

        self.zc.edit_message(receipt, "🌐 Reading sources and drafting the page…")
        out = self.omp_run(task, tools=True, approval="yolo", session=False,
                           json_mode=True, cwd=cfg.wiki_clone_dir)

        self.zc.edit_message(receipt, "📤 Publishing to the wiki…")
        if self.wiki.has_changes(cfg.wiki_clone_dir):
            self.wiki.commit_all(cfg.wiki_clone_dir, f"research: {question[:60]}")
        self.wiki.push(cfg.wiki_clone_dir, branch)

        page_url = f"{cfg.wiki_site_url}/{s}/"
        pr_url = self._open_pr(branch, question, page_url)

        answer, followups = _split(omp.assistant_text(out))
        body = f"{answer}\n\n📄 {page_url}" + (f"\nPR: {pr_url}" if pr_url else "")
        if followups:
            body += ("\n\n**Follow-ups** — copy any worth pursuing into a new "
                     "`#research` topic:\n" + "\n".join(f"- {q}" for q in followups))
        # Research posts the full, visible answer (the primary result — not a spoiler).
        self.zc.edit_message(receipt, body)
        self._mirror_topic(topic)

    def _mirror_topic(self, topic: str) -> None:
        try:
            self.mirror(self.cfg.research_stream, topic)
        except Exception as e:  # a mirror failure must not break the research reply
            print(f"[researcher] bluesky mirror failed for {topic}: {e}",
                  file=sys.stderr, flush=True)

    def _open_pr(self, branch: str, question: str, page_url: str) -> str:
        try:
            return self.open_pr(
                github.repo_slug(self.cfg.wiki_repo_url), token=self.cfg.wiki_push_token,
                head=branch, base=self.cfg.wiki_base_branch,
                title=question[:72], body=f"Research for: {question}\n\nPage: {page_url}",
            )
        except github.GitHubError:
            return ""  # e.g. the PR already exists (resume)


def _split(text: str) -> tuple[str, list[str]]:
    """Split the agent's reply into (short answer, follow-up questions)."""
    followups: list[str] = []
    kept: list[str] = []
    for line in text.splitlines():
        m = re.match(r"\s*FOLLOWUPS:\s*(.+)", line, re.IGNORECASE)
        if m:
            followups = [q.strip() for q in m.group(1).split("||") if q.strip()]
            continue
        kept.append(line)
    return "\n".join(kept).strip(), followups
