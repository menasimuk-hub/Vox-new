"""Always-on trace logging for Abuu agent pipeline (grep: abuu_agent_trace)."""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


def clip(text: str | None, max_len: int = 160) -> str:
    cleaned = str(text or "").replace("\n", " ").strip()
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[: max_len - 3] + "..."


def _format_fields(**fields: Any) -> str:
    parts: list[str] = []
    for key, value in fields.items():
        if value is None:
            continue
        if isinstance(value, bool):
            text = "true" if value else "false"
        elif isinstance(value, (dict, list)):
            text = clip(json.dumps(value, ensure_ascii=False), max_len=200)
        else:
            text = clip(str(value))
        if not text:
            continue
        if " " in text or "=" in text:
            parts.append(f'{key}="{text}"')
        else:
            parts.append(f"{key}={text}")
    return " ".join(parts)


def _emit(event: str, **fields: Any) -> None:
    payload = _format_fields(**fields)
    logger.info("abuu_agent_trace %s %s", event, payload)


def stt_ok(**fields: Any) -> None:
    _emit("stt_ok", **fields)


def stt_fail(**fields: Any) -> None:
    _emit("stt_fail", **fields)


def route(**fields: Any) -> None:
    _emit("route", **fields)


def turn_start(**fields: Any) -> None:
    _emit("turn_start", **fields)


def prefetch(**fields: Any) -> None:
    _emit("prefetch", **fields)


def llm_request(**fields: Any) -> None:
    _emit("llm_request", **fields)


def llm_tool(**fields: Any) -> None:
    _emit("llm_tool", **fields)


def llm_reply(**fields: Any) -> None:
    _emit("llm_reply", **fields)


def turn_end(**fields: Any) -> None:
    _emit("turn_end", **fields)


def state_before(**fields: Any) -> None:
    _emit("state_before", **fields)


def state_after(**fields: Any) -> None:
    _emit("state_after", **fields)
