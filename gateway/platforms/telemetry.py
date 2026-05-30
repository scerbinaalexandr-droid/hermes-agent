"""Lightweight UX telemetry for the Telegram gateway.

Purpose: feed HERMES_TO_96.md Assumption A1 — "иерархическое inline-меню
удобнее свободного текста для CEO". We log every incoming update (message
type + commands vs callback_query button clicks) without touching state.db
and without blocking the bot.

Design constraints (intentionally narrow):
- One JSONL file per day at $HERMES_HOME/logs/telemetry/YYYY-MM-DD.jsonl.
- Append-only. No reads from this module. No external deps.
- Never raise. A telemetry crash MUST NOT take down user-facing handlers.
- No message content beyond first token of commands (no PII leakage).
- Backed up by the existing daily backup job (logs/telemetry added to INCLUDE).

Used by: skills/ceo/telemetry/scripts/telemetry_report.py
"""
from __future__ import annotations

import json
import os
import pathlib
from datetime import datetime, timezone
from typing import Any

_TELEMETRY_DIR = (
    pathlib.Path(os.environ.get("HERMES_HOME") or os.path.expanduser("~/.hermes"))
    / "logs"
    / "telemetry"
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _log_event(event: dict[str, Any]) -> None:
    """Append one event. Defensive — swallow any error."""
    try:
        _TELEMETRY_DIR.mkdir(parents=True, exist_ok=True)
        today = datetime.now(timezone.utc).date().isoformat()
        path = _TELEMETRY_DIR / f"{today}.jsonl"
        event.setdefault("ts", _now_iso())
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
    except Exception:
        # Telemetry failure must never affect bot UX.
        pass


def _message_kind(msg: Any) -> str:
    """Coarse classification — what TYPE of input arrived."""
    try:
        if msg.voice:
            return "voice"
        if msg.video_note:
            return "video_note"
        if msg.photo:
            return "photo"
        if msg.document:
            return "document"
        if msg.audio:
            return "audio"
        if msg.sticker:
            return "sticker"
        if msg.location or msg.venue:
            return "location"
    except AttributeError:
        pass

    text = (getattr(msg, "text", None) or "").strip()
    if not text:
        return "other"
    if text.startswith("/"):
        return "command"
    return "text"


async def log_message(update: Any, context: Any) -> None:  # noqa: ARG001
    """Pre-handler — log inbound message metadata before the real handler runs."""
    try:
        msg = update.message or update.edited_message
        if msg is None:
            return
        kind = _message_kind(msg)
        text = (getattr(msg, "text", None) or "").strip()
        # Only the first token of commands — to know /brief vs /coach vs /cost.
        # NOT free text content (PII boundary).
        first_token = ""
        if kind == "command" and text:
            first_token = text.split(maxsplit=1)[0][:40]

        _log_event({
            "kind": kind,
            "source": "message",
            "user_id": (msg.from_user.id if msg.from_user else None),
            "chat_id": (msg.chat.id if msg.chat else None),
            "text_len": len(text),
            "command": first_token or None,
        })
    except Exception:
        pass


async def log_callback(update: Any, context: Any) -> None:  # noqa: ARG001
    """Pre-handler — log inline-keyboard button clicks."""
    try:
        cq = update.callback_query
        if cq is None:
            return
        _log_event({
            "kind": "callback",
            "source": "callback_query",
            "user_id": (cq.from_user.id if cq.from_user else None),
            "chat_id": (
                cq.message.chat.id if cq.message and cq.message.chat else None
            ),
            "callback_data": (cq.data or "")[:80],
        })
    except Exception:
        pass
