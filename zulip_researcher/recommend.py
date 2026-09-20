"""Recommend mode: read a mentioned thread and post candidate Questions into it.

Recommend does not touch the web or any secret — it reads the thread and asks omp to
propose questions, then posts them back into the same thread for the operator to copy
into `#research`.
"""

from __future__ import annotations

from typing import Callable

from . import config, omp, zulip
from .loop import Trigger

SYSTEM = (
    "You read a discussion and propose focused, self-contained research questions worth "
    "investigating further. Output ONLY the questions, one per line, with no "
    "numbering or commentary — between three and five of them."
)

OmpAsk = Callable[[str], str]


class Recommend:
    def __init__(self, cfg: config.Config, zc: "zulip.Zulip", omp_ask: OmpAsk | None = None):
        self.cfg = cfg
        self.zc = zc
        self.omp_ask = omp_ask or (lambda task: omp.ask(task))

    def _transcript(self, stream_id: int, topic: str) -> str:
        msgs = self.zc.get_messages(stream_id, topic)
        return "\n\n".join(
            f"{m.get('sender_full_name', '?')}: {m.get('content', '')}".strip()
            for m in msgs
        )

    def recommend(self, t: Trigger) -> None:
        stream_id = self.zc.get_stream_id(t.stream)
        transcript = self._transcript(stream_id, t.topic)
        if not transcript.strip():
            return
        receipt = self.zc.send_message(
            stream_id, t.topic, "🔎 Reading the thread and proposing research questions…"
        )
        answer = self.omp_ask(
            f"{SYSTEM}\n\nThread title: {t.topic}\n\n--- discussion ---\n\n{transcript}"
        )
        questions = _questions(answer)
        if not questions:
            self.zc.edit_message(receipt, "No research questions surfaced from this thread.")
            return
        body = (
            "````spoiler 💡 Candidate research questions\n"
            "Copy any worth pursuing into `#research`:\n\n"
            + "\n".join(f"- {q}" for q in questions) + "\n````"
        )
        self.zc.edit_message(receipt, body)


def _questions(answer: str) -> list[str]:
    out: list[str] = []
    for line in answer.splitlines():
        q = line.strip().lstrip("-*0123456789. \t").strip()
        if q:
            out.append(q)
    return out[:5]
