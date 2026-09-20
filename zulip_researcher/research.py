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
import time
from typing import Callable

from . import bluesky_mirror, config, github, intent, omp, wiki, zulip
from .loop import Trigger
from .slug import slug

SYSTEM = """You are Agent Smith, author of a public discourse-graph wiki. Research the
message below (usually a link to ingest) and publish the result as atomic, densely
[[wikilinked]] Markdown pages in the `site/` directory of the repo at your working directory.

Work in a SINGLE pass, by yourself — do NOT spawn sub-agents. Fetch and read the link(s)
directly, then write the pages.

Method: pick the approach the message needs — evidence synthesis for empirical
questions, a landscape map for broad ones, a criteria verdict for comparisons, a
definition for concepts, positions for open questions. Ground every substantive claim in
a source: one `type: source` page per cited URL (frontmatter `url`, `author`, `date`;
title ends with the domain in parentheses), cited from a `## Sources` section. Give
`type: claim` pages an honest `status:` of established / tentative / speculative.

Reuse what exists: `grep` the `site/` directory for related page titles and [[link]] them;
only create a page that does not already exist.

Page frontmatter: `title`, `type` (concept/source/claim/question/moc/tool), `by`, and
optional `tags`. The core page's slug MUST be `%(slug)s`.

When done, commit your changes. Then reply with a SHORT, clean answer (no operator
context, no thread detail) for a chat thread, and on a final line list follow-up
questions exactly as: `FOLLOWUPS: question one || question two`.
"""

OmpRun = Callable[..., str]
OpenPr = Callable[..., str]
MirrorTopic = Callable[[str, str], None]

# Single-pass research toolset: everything the agent needs to fetch, grep and write —
# but NOT `task` (no sub-agents) or `todo`/`computer`/`python`.
RESEARCH_TOOLS = "read,bash,edit,write,grep,glob,web_search"
_TOOL_EMOJI = {"read": "📖", "bash": "🖥️", "edit": "✍️", "write": "✍️",
               "grep": "🔎", "glob": "🔎", "web_search": "🌐", "browser": "🌐"}
OmpAsk = Callable[[str], str]


class Research:
    def __init__(self, cfg: config.Config, zc: "zulip.Zulip",
                 omp_run: OmpRun | None = None, wiki_ops=wiki,
                 open_pr: OpenPr | None = None, mirror: MirrorTopic | None = None,
                 omp_ask: OmpAsk | None = None, merge_pr=None):
        self.cfg = cfg
        self.zc = zc
        self.omp_run = omp_run or omp.run_stream
        self.wiki = wiki_ops
        self.open_pr = open_pr or github.open_pr
        self.merge_pr = merge_pr or (
            lambda repo, number, token: github.merge_pr(repo, number, token=token))
        self.mirror = mirror or (
            lambda stream, topic: bluesky_mirror.BlueskyMirror(cfg, zc).mirror_topic(stream, topic)
        )
        self.omp_ask = omp_ask or (lambda task: omp.ask(task))
        self._agent_id_cache: int | None = None

    def _opening(self, stream_id: int, topic: str) -> str:
        first = self.zc.first_message(stream_id, topic)
        return (first or {}).get("content", "").strip()

    def _transcript(self, stream_id: int, topic: str) -> str:
        return "\n\n".join(
            f"{m.get('sender_full_name', '?')}: {m.get('content', '')}".strip()
            for m in self.zc.get_messages(stream_id, topic)
        )

    @property
    def _agent_id(self) -> int | None:
        if self._agent_id_cache is None:
            self._agent_id_cache = self.zc.user_id_for_email(self.cfg.zulip_api_username)
        return self._agent_id_cache

    def _receipt(self, stream_id: int, topic: str, status: str) -> int:
        """Reuse the bot's existing status message in the topic (idempotent across
        retries and restarts), else post a fresh one — so a re-run never duplicates
        the receipt."""
        for m in self.zc.get_messages(stream_id, topic):
            if (m.get("sender_id") == self._agent_id
                    and bluesky_mirror.NO_MIRROR not in (m.get("content") or "")):
                self.zc.edit_message(m["id"], status)
                return m["id"]
        return self.zc.send_message(stream_id, topic, status)

    def research(self, t: Trigger, resume: bool = False) -> None:
        cfg = self.cfg
        stream_id = self.zc.get_stream_id(cfg.research_stream)
        opening = self._opening(stream_id, t.topic)
        message = opening or t.topic

        untitled = zulip.is_untitled(t.topic)
        if untitled:
            # The title auto-writer only names the thread for orientation; the
            # research works from the operator's actual message (the body), never
            # a reformulation.
            title = intent.derive(message, ask=self.omp_ask)
        else:
            title = t.topic
        s = slug(title)
        branch = f"researcher/{s}"

        topic = t.topic
        if untitled and title != t.topic:
            self.zc.move_message(t.message_id, title)  # move just this one message
            topic = title
        receipt = self._receipt(stream_id, topic, "🔎 Researching…")

        try:
            self.wiki.prepare(cfg.wiki_clone_dir, cfg.wiki_repo_url, cfg.wiki_base_branch,
                              branch, cfg.wiki_push_token, cfg.git_user_name,
                              cfg.git_user_email, resume=resume)

            task = (SYSTEM % {"slug": s}) + f"\n\nRESEARCH THIS:\n{message}\n"
            links = _urls(message)
            if links:
                bullets = "\n".join(f"- {u}" for u in links)
                task += (
                    "\nAttached link(s) to ingest — this is the whole task. An ingest is a "
                    "source card, NOT a Map of Content: never set `type: moc` here.\n"
                    f"{bullets}\n"
                    "Fetch and read each link yourself, then:\n"
                    f"1. The core page (slug `{s}`) IS the source card: `type: source`, with "
                    "frontmatter `url`/`author`/`date` and a title ending with the domain in "
                    "parentheses — capture its key points, a concise summary, and the author's "
                    "conclusions.\n"
                    "2. Only if the source introduces distinct, reusable ideas, add an atomic "
                    "`type: concept` page for each, densely [[wikilinked]] and citing the "
                    "source under `## Sources`; link them from the source card.\n"
                )
            if resume:
                task += ("\nThe #research thread so far — continue from it and update the "
                         "existing page:\n\n" + self._transcript(stream_id, topic))

            self.zc.edit_message(receipt, "🌐 Reading sources and drafting the page…")
            step = [0]
            last = [0.0]

            def on_tool(name, intent_text, args):
                step[0] += 1
                now = time.monotonic()
                if now - last[0] < 2.0:            # rate-limit the Zulip edits
                    return
                last[0] = now
                label = (intent_text or name or "working").strip().splitlines()[0][:180]
                try:
                    self.zc.edit_message(
                        receipt,
                        f"🌐 Researching… · step {step[0]}\n{_TOOL_EMOJI.get(name, '🔧')} {label}")
                except Exception:
                    pass

            out = self.omp_run(task, tools=RESEARCH_TOOLS, approval="yolo", session=False,
                               json_mode=True, cwd=cfg.wiki_clone_dir,
                               timeout=cfg.omp_timeout, on_tool=on_tool)

            self.zc.edit_message(receipt, "📤 Publishing to the wiki…")
            if self.wiki.has_changes(cfg.wiki_clone_dir):
                self.wiki.commit_all(cfg.wiki_clone_dir, f"research: {title[:60]}")
            self.wiki.push(cfg.wiki_clone_dir, branch)

            page_url = f"{cfg.wiki_site_url}/{s}/"
            pr_url = self._open_pr(branch, title, page_url)

            answer, followups = _split(omp.assistant_text(out))
            body = f"{answer}\n\n📄 {page_url}" + (f"\nPR: {pr_url}" if pr_url else "")
            # Research posts the full, visible answer (the primary result — not a spoiler).
            self.zc.edit_message(receipt, body)
            if followups:
                # A separate message, marked so the Bluesky mirror never publishes it.
                self.zc.send_message(stream_id, topic, bluesky_mirror.NO_MIRROR + "\n"
                    "**Follow-ups** — copy any worth pursuing into a new `#research` topic:\n"
                    + "\n".join(f"- {q}" for q in followups))
            self._mirror_topic(topic)
        except Exception as e:
            self.zc.edit_message(
                receipt,
                f"⚠️ Research failed — {type(e).__name__}: {str(e)[:200]}\n"
                "I'll retry on the next run.")
            raise

    def _mirror_topic(self, topic: str) -> None:
        try:
            self.mirror(self.cfg.research_stream, topic)
        except Exception as e:  # a mirror failure must not break the research reply
            print(f"[researcher] bluesky mirror failed for {topic}: {e}",
                  file=sys.stderr, flush=True)

    def _open_pr(self, branch: str, title: str, page_url: str) -> str:
        repo = github.repo_slug(self.cfg.wiki_repo_url)
        token = self.cfg.wiki_push_token
        try:
            url = self.open_pr(
                repo, token=token, head=branch, base=self.cfg.wiki_base_branch,
                title=title[:72], body=f"Research for: {title}\n\nPage: {page_url}")
        except github.GitHubError as e:
            print(f"[researcher] open_pr failed: {e}", file=sys.stderr, flush=True)
            return ""  # e.g. the PR already exists (resume)
        number = github.pr_number(url)
        if number is not None:
            try:
                self.merge_pr(repo, number, token)  # publish: squash-merge to main
            except github.GitHubError as e:
                print(f"[researcher] PR #{number} opened but not merged: {e}",
                      file=sys.stderr, flush=True)
        return url


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


URL_RE = re.compile(r'https?://[^\s<>()\[\]"\']+')


def _urls(text: str) -> list[str]:
    """Distinct http(s) URLs in order of appearance, trailing punctuation trimmed."""
    seen: set[str] = set()
    out: list[str] = []
    for u in URL_RE.findall(text or ""):
        u = u.rstrip('.,);:]')
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out
