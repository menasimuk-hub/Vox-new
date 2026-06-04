"""Inbound dedupe for WA Survey — prevent double-advance on webhook retries."""

from __future__ import annotations

from typing import Any


def _wa_conversation(payload: dict[str, Any]) -> dict[str, Any]:
    wa = payload.get("wa_conversation")
    return wa if isinstance(wa, dict) else {}


def is_duplicate_inbound(
    payload: dict[str, Any],
    *,
    log_id: int | None,
    inbound_message_id: str | None,
) -> bool:
    """
    True when this inbound log/message was already applied to the conversation.
    Only dedupes when at least one id is provided (simulator/tests without ids are unaffected).
    """
    if log_id is None and not inbound_message_id:
        return False
    conv = _wa_conversation(payload)
    if log_id is not None and conv.get("last_processed_inbound_log_id") == log_id:
        return True
    if inbound_message_id and conv.get("last_processed_inbound_message_id") == inbound_message_id:
        return True
    return False


def mark_inbound_processed(
    payload: dict[str, Any],
    *,
    log_id: int | None,
    inbound_message_id: str | None,
) -> dict[str, Any]:
    conv = _wa_conversation(payload)
    if log_id is not None:
        conv["last_processed_inbound_log_id"] = log_id
    if inbound_message_id:
        conv["last_processed_inbound_message_id"] = inbound_message_id
    payload["wa_conversation"] = conv
    return payload
