"""Zulip adapter built on the official Zulip Python SDK.

Wraps `zulip.Client` so the rest of the app never sees HTTP, auth, or event-queue
details. This is the only seam to Zulip; tests swap a fake in its place.
"""

from __future__ import annotations

import urllib.parse

from .models import ZulipMessage


class ZulipError(RuntimeError):
    pass


class Zulip:
    """Minimal Zulip client for the researcher's needs, backed by the SDK."""

    def __init__(self, url: str, api_key: str, api_username: str):
        self.url = url.rstrip("/")
        self.api_username = api_username
        self.api_key = api_key
        self._client_obj = None

    @property
    def _client(self):
        # Lazy: constructing the SDK client performs a network call, and importing
        # the SDK is deferred so the module imports without the dependency present
        # (tests swap in a fake before any real call).
        if self._client_obj is None:
            import zulip
            self._client_obj = zulip.Client(
                email=self.api_username, api_key=self.api_key, site=self.url)
        return self._client_obj

    def _ok(self, resp: dict) -> dict:
        if resp.get("result") != "success":
            raise ZulipError(resp.get("msg") or str(resp))
        return resp

    # --- reads ---

    def get_stream_id(self, stream_name: str) -> int:
        return self._ok(self._client.get_stream_id(stream_name))["stream_id"]

    def get_topics(self, stream_id: int) -> list[dict]:
        return self._ok(self._client.get_stream_topics(stream_id)).get("topics", [])

    def get_messages(self, stream_id: int, topic_name: str, anchor: str = "oldest",
                     num_before: int = 0, num_after: int = 100) -> list[ZulipMessage]:
        resp = self._ok(self._client.get_messages({
            "anchor": anchor,
            "num_before": num_before,
            "num_after": num_after,
            "narrow": [
                {"operator": "stream", "operand": stream_id},
                {"operator": "topic", "operand": topic_name},
            ],
            "apply_markdown": False,
        }))
        return resp.get("messages", [])

    def first_message(self, stream_id: int, topic_name: str) -> ZulipMessage | None:
        msgs = self.get_messages(stream_id, topic_name, anchor="oldest", num_after=1)
        return msgs[0] if msgs else None

    def get_message(self, message_id: int) -> ZulipMessage | None:
        resp = self._ok(self._client.get_messages({
            "anchor": message_id,
            "num_before": 0,
            "num_after": 0,
            "narrow": [{"operator": "id", "operand": message_id}],
            "apply_markdown": False,
        }))
        msgs = resp.get("messages", [])
        return msgs[0] if msgs else None

    def message_reactions(self, message_id: int) -> list[str]:
        msg = self.get_message(message_id) or {}
        return [r.get("emoji_name") for r in msg.get("reactions", []) if r.get("emoji_name")]

    def source_url(self, stream_id: int, topic_name: str, message_id: int) -> str:
        return (f"{self.url}/#narrow/channel/{stream_id}-"
                f"{urllib.parse.quote(topic_name, safe='')}/near/{message_id}")

    def user_lookup_raw(self, email: str) -> dict:
        """Raw `GET users/{email}` response — for diagnosing operator resolution."""
        return self._client.call_endpoint(f"users/{urllib.parse.quote(email)}", method="GET")

    def user_id_for_email(self, email: str) -> int | None:
        resp = self.user_lookup_raw(email)
        if resp.get("result") != "success":
            return None
        return (resp.get("user") or {}).get("user_id")

    # --- writes ---

    def send_message(self, stream_id: int, topic_name: str, content: str) -> int:
        resp = self._ok(self._client.send_message({
            "type": "stream",
            "to": stream_id,
            "topic": topic_name,
            "content": content,
        }))
        return resp["id"]

    def edit_message(self, message_id: int, content: str) -> None:
        self._ok(self._client.update_message({"message_id": message_id, "content": content}))

    def move_message(self, message_id: int, topic: str) -> None:
        self._ok(self._client.update_message({
            "message_id": message_id,
            "topic": topic,
            "propagate_mode": "change_all",
        }))

    def delete_message(self, message_id: int) -> None:
        self._ok(self._client.call_endpoint(f"messages/{message_id}", method="DELETE"))

    def add_reaction(self, message_id: int, emoji: str) -> None:
        # Idempotent: the reaction is a durable marker; re-adding an existing one is fine.
        resp = self._client.add_reaction({"message_id": message_id, "emoji_name": emoji})
        if resp.get("result") != "success" and "already exists" not in (resp.get("msg") or ""):
            raise ZulipError(resp.get("msg") or str(resp))

    def remove_reaction(self, message_id: int, emoji: str) -> None:
        # Idempotent: removing an absent reaction is a no-op.
        resp = self._client.remove_reaction({"message_id": message_id, "emoji_name": emoji})
        msg = resp.get("msg") or ""
        if resp.get("result") != "success" and "exist" not in msg:
            raise ZulipError(msg or str(resp))

    # --- event queue ---

    def register_event_queue(self, event_types: list[str] | None = None,
                             narrow: list[list[str]] | None = None,
                             all_public_streams: bool = False) -> dict:
        return self._ok(self._client.register(event_types=event_types, narrow=narrow,
                                                all_public_streams=all_public_streams))

    def get_events(self, queue_id: str, last_event_id: int) -> tuple[list[dict], int]:
        resp = self._client.get_events(
            queue_id=queue_id, last_event_id=last_event_id, dont_block=False)
        if resp.get("result") != "success":
            raise ZulipError(resp.get("msg") or str(resp))
        events = resp.get("events") or []
        new_last = last_event_id
        for e in events:
            if isinstance(e.get("id"), int):
                new_last = max(new_last, e["id"])
        return events, new_last


def topic_is_resolved(topic_name: str) -> bool:
    """A resolved Zulip topic is prefixed with the check mark Zulip inserts."""
    stripped = topic_name.strip()
    return stripped.startswith("✔") or stripped.startswith("✓")


__all__ = ["Zulip", "ZulipError", "topic_is_resolved"]
