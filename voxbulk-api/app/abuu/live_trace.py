"""Unified live trace logging for Abuu WhatsApp (grep: abuu_live_trace)."""

from __future__ import annotations

import logging
from typing import Any

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_FORBIDDEN_FRAGMENTS = ("كيف بقدر أساعدك", "ما لقيت أطباق")


def _format_fields(**fields: Any) -> str:
    parts: list[str] = []
    for key, value in fields.items():
        if value is None:
            continue
        text = str(value).replace("\n", " ").strip()
        if not text:
            continue
        if " " in text or "=" in text:
            parts.append(f'{key}="{text}"')
        else:
            parts.append(f"{key}={text}")
    return " ".join(parts)


def enabled() -> bool:
    return bool(get_settings().abuu_waiter_trace_enabled)


def live(event: str, **fields: Any) -> None:
    if not enabled():
        return
    payload = _format_fields(**fields)
    logger.info("abuu_live_trace %s %s", event, payload)


def boot(**fields: Any) -> None:
    live("boot", **fields)


def route(**fields: Any) -> None:
    live("route", **fields)


def inbound(**fields: Any) -> None:
    live("in", **fields)


def search(**fields: Any) -> None:
    live("search", **fields)


def think(**fields: Any) -> None:
    live("think", **fields)


def outbound(**fields: Any) -> None:
    reply = str(fields.get("reply_preview") or "")
    fields = dict(fields)
    if reply and "forbidden_hit" not in fields:
        fields["forbidden_hit"] = any(fragment in reply for fragment in _FORBIDDEN_FRAGMENTS)
    live("out", **fields)


def skip(**fields: Any) -> None:
    live("skip", **fields)
