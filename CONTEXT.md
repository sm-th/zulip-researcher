# Zulip Researcher

A Zulip bot that turns chat discussions into deep, sourced research. Mention it in a
thread to get suggested research questions; each one the operator copies into `#research`
becomes a deep, web-grounded Research, published as a short thread answer, a cited page
on the wiki, and a Bluesky post. Everything runs inside a microsandbox.

## The agent

**Agent**:
One small agent, one codebase, one wiki, run in two modes. The modes are just code paths,
not separate services or ceremonious modules.
_Avoid_: bot; recommender and researcher as separate services.

**Recommend mode**:
On an `@research` mention, reads a thread and posts recommended Questions back into that
same thread. It writes nothing to `#research`.

**Research mode**:
Runs one Research for a `#research` topic, editing the wiki and Bluesky repos directly with
a full toolset (file edits, semantic search, web search, git). Like the whole system, it
runs inside the microsandbox.

## Triggering & curation

**@research mention**:
Invoking Recommend mode from any channel. Produces Recommendations; it never starts a
Research directly.

**Recommendation**:
A candidate Question the agent posts into the Seed thread for the operator to weigh.
_Avoid_: proposal, suggestion.

**Manual copy**:
The operator copying chosen Questions into `#research`, one topic per Question. This is the
only curation gate, and it makes the operator the author — which is what drives Bluesky
identity. There is no like/👍 gate.
_Avoid_: approval, like.

**#research**:
The stream where Research happens. Every topic is a Question the operator copied in; a new
topic auto-starts a Research. It holds only operator Questions and agent answers.

**Research Session**:
The resumable exchange behind one `#research` topic. An operator comment continues the same
session — a new wiki link and a new answer — rather than starting a new Research.
_Avoid_: conversation.

**Seed thread**:
The origin discussion an `@research` mention fired in. It is private: never republished, and
never linked from public output.
_Avoid_: source thread, original thread.

## Research

**Research**:
One deep, web-grounded, source-cited investigation of a single Question, producing a Smith
Wiki page, a short answer reply in the topic, and a Bluesky post. Its method varies with the
question; the agent chooses it.
_Avoid_: report, study, deep dive.

**Clean**:
A quality of Research output: it carries only what the result needs — no operator context,
no Seed thread detail, no process noise. This is how privacy is kept, since output is
public.

**Atomic**:
One question, one self-contained result — every detail the answer needs and nothing more;
one idea per wiki page.

**Smith Wiki**:
The public discourse-graph wiki (`smith.wiki`, Eleventy → GitHub Pages) that Research pages
are written to, via pull request. Pages are typed (concept / source / claim / question /
moc / tool) and densely `[[wikilinked]]`.
_Avoid_: the wiki (when the reference is ambiguous).

## Publishing

**Producer**:
The agent edits page and post files in the publishing repos and opens the wiki PR / pushes
the Bluesky posts; each platform's own CI performs the actual publish.
_Avoid_: publisher.

**Preparation**:
Normalizing operator input into clean, publishable markdown via the shared
prepare-markdown service before it is used.
_Avoid_: cleanup, post-processing.

**Bluesky mirror**:
The `#research` topic mirrored to Bluesky as a reply-thread across two accounts: each Zulip
message becomes one Bluesky post under its author's identity, preserving topic order.

**Identity split**:
Operator-authored messages publish from the `andysmith.ai` repo; agent-authored answers
(each carrying a wiki link) from the `smith.wiki` repo.
