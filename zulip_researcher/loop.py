"""The listener: watch Zulip and dispatch to Recommend / Research, idempotently.

Stateless (ADR-0003): what has already been handled is read back from Zulip via the
bot's own reaction markers, not from a local store. The dispatch decision itself is a
pure function (`classify`) so it can be tested without any I/O.
"""

from __future__ import annotations

import os
import time
import sys
from dataclasses import dataclass

from . import config, zulip
from .zulip import topic_is_resolved

# Dispatch actions.
RECOMMEND = "recommend"
RESEARCH = "research"
RESUME = "resume"
IGNORE = "ignore"

# Bot-owned reaction markers on a message (the operator never sets these).
WORKING = "working_on_it"
DONE = "checkered_flag"


@dataclass(frozen=True)
class Trigger:
    """A normalized Zulip message the listener may act on."""

    stream: str
    topic: str
    author_id: int
    message_id: int
    is_mention: bool
    is_topic_start: bool


def classify(t: Trigger, research_stream: str, operator_id: int) -> str:
    """Pure decision: what should the listener do with this message?

    Only the operator triggers anything (single-user). A message the operator writes
    in #research starts a Research (a new topic) or resumes one (a reply); an
    @research mention anywhere else asks for Recommendations. Everything else is
    ignored — including the agent's own posts and other users.
    """
    if t.author_id != operator_id:
        return IGNORE
    if t.stream == research_stream:
        return RESEARCH if t.is_topic_start else RESUME
    if t.is_mention:
        return RECOMMEND
    return IGNORE


class ModesNotWired(RuntimeError):
    pass


class Loop:
    """Event loop + stateless reconcile. `modes` provides the two behaviours; its
    real implementations land in issues #3 (Recommend) and #4 (Research)."""

    def __init__(self, cfg: config.Config, zc: "zulip.Zulip | None" = None, modes=None):
        self.cfg = cfg
        self.zc = zc or zulip.Zulip(cfg.zulip_url, cfg.zulip_api_key, cfg.zulip_api_username)
        self.modes = modes
        self._stream_id: int | None = None
        self._operator_id: int | None = None

    @property
    def stream_id(self) -> int:
        if self._stream_id is None:
            self._stream_id = self.zc.get_stream_id(self.cfg.research_stream)
        return self._stream_id

    @property
    def operator_id(self) -> int:
        if self._operator_id is None:
            self._operator_id = self.zc.user_id_for_email(self.cfg.operator_email)
        return self._operator_id

    # --- dispatch ---

    def _require_modes(self):
        if self.modes is None:
            raise ModesNotWired(
                "Recommend/Research modes are not wired yet (issues #3/#4)."
            )

    def dispatch(self, t: Trigger) -> str:
        """Run the action for one trigger, idempotently. Returns the action taken."""
        action = classify(t, self.cfg.research_stream, self.operator_id)
        if action == IGNORE:
            return IGNORE
        self._require_modes()
        if action == RECOMMEND:
            if DONE in self.zc.message_reactions(t.message_id):
                return IGNORE
            self.zc.add_reaction(t.message_id, WORKING)
            self.modes.recommend(t)
            self.zc.remove_reaction(t.message_id, WORKING)
            self.zc.add_reaction(t.message_id, DONE)
        else:  # RESEARCH or RESUME
            if DONE in self.zc.message_reactions(t.message_id):
                return IGNORE
            self.zc.add_reaction(t.message_id, WORKING)
            self.modes.research(t, resume=(action == RESUME))
            self.zc.remove_reaction(t.message_id, WORKING)
            self.zc.add_reaction(t.message_id, DONE)
        return action

    def _safe_dispatch(self, t: Trigger) -> str:
        try:
            return self.dispatch(t)
        except Exception as e:  # a failing/unavailable mode must not kill the listener
            print(f"[researcher] dispatch failed for {t.stream}/{t.topic}: {e}",
                  file=sys.stderr, flush=True)
            return IGNORE

    # --- event parsing ---

    def _trigger_from_event(self, event: dict) -> Trigger | None:
        if event.get("type") != "message":
            return None
        m = event.get("message") or {}
        if m.get("type") != "stream":
            return None  # DMs are out of scope
        stream = m.get("display_recipient") or ""
        topic = m.get("subject") or ""
        is_mention = "mentioned" in (event.get("flags") or [])
        is_topic_start = False
        if stream == self.cfg.research_stream:
            first = self.zc.first_message(self.stream_id, topic)
            is_topic_start = bool(first and first.get("id") == m.get("id"))
        return Trigger(
            stream=stream,
            topic=topic,
            author_id=m.get("sender_id"),
            message_id=m.get("id"),
            is_mention=is_mention,
            is_topic_start=is_topic_start,
        )

    # --- reconcile (stateless backlog scan of #research) ---

    def reconcile(self) -> int:
        """Research any operator #research topic that has no DONE marker yet.

        This recovers work missed while the listener was down; idempotency is the
        DONE reaction on the topic's first message.
        """
        handled = 0
        for topic in self.zc.get_topics(self.stream_id):
            name = topic.get("name", "")
            if topic_is_resolved(name):
                continue
            first = self.zc.first_message(self.stream_id, name)
            if not first:
                continue
            t = Trigger(
                stream=self.cfg.research_stream,
                topic=name,
                author_id=first.get("sender_id"),
                message_id=first.get("id"),
                is_mention=False,
                is_topic_start=True,
            )
            if self._safe_dispatch(t) != IGNORE:
                handled += 1
        return handled

    # --- run ---

    def run_once(self) -> int:
        return self.reconcile()

    def run(self) -> None:
        self._require_modes()
        print("[researcher] starting; scanning #research backlog", file=sys.stderr, flush=True)
        op = self.operator_id
        print(f"[researcher] operator_id={op} operator_email={self.cfg.operator_email!r} "
              f"stream={self.cfg.research_stream!r} stream_id={self.stream_id}",
              file=sys.stderr, flush=True)
        if op is None:
            print(f"[researcher] operator NOT resolved — raw GET users/<email>: "
                  f"{self.zc.user_lookup_raw(self.cfg.operator_email)}",
                  file=sys.stderr, flush=True)
            for m in [x for x in self.zc.list_members() if not x.get("is_bot")][:100]:
                print(f"[researcher]   member id={m.get('user_id')} "
                      f"name={m.get('full_name')!r} email={m.get('email')!r} "
                      f"delivery_email={m.get('delivery_email')!r}",
                      file=sys.stderr, flush=True)
        handled = self.reconcile()
        print(f"[researcher] backlog scan done ({handled} dispatched); listening for events",
              file=sys.stderr, flush=True)
        reg = self.zc.register_event_queue(event_types=["message"], all_public_streams=True)
        queue_id, last = reg["queue_id"], reg["last_event_id"]
        while True:
            try:
                events, last = self.zc.get_events(queue_id, last)
                for event in events:
                    if os.environ.get("RESEARCHER_DEBUG"):
                        dm = event.get("message") or {}
                        print(f"[researcher] event #{event.get('id')} type={event.get('type')} "
                              f"stream={dm.get('display_recipient')!r} topic={dm.get('subject')!r} "
                              f"sender={dm.get('sender_id')} flags={event.get('flags')}",
                              file=sys.stderr, flush=True)
                    t = self._trigger_from_event(event)
                    if t is not None:
                        action = self._safe_dispatch(t)
                        if action != IGNORE:
                            print(f"[researcher] {t.stream}/{t.topic}: {action}",
                                  file=sys.stderr, flush=True)
                        elif t.is_mention and t.author_id != self.operator_id:
                            print(f"[researcher] ignored mention in {t.stream}/{t.topic}: "
                                  f"author {t.author_id} != operator {self.operator_id} "
                                  f"(check RESEARCHER_OPERATOR_EMAIL)",
                                  file=sys.stderr, flush=True)
            except zulip.ZulipError:
                time.sleep(self.cfg.poll_interval)
                reg = self.zc.register_event_queue(event_types=["message"], all_public_streams=True)
                queue_id, last = reg["queue_id"], reg["last_event_id"]
