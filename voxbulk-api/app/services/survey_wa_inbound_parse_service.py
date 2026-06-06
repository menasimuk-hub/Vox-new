"""Normalize Telnyx WhatsApp inbound replies for survey runtime (text + buttons)."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, field
from typing import Any

logger = logging.getLogger(__name__)
LOG_PREFIX = "[survey-wa-inbound]"

START_ACTION = "start_survey"

# Generic start triggers — welcome templates may use different approved labels.
_START_LABEL_RE = re.compile(
    r"^\s*(?:"
    r"start(?:\s+survey)?|"
    r"begin(?:\s+survey)?|"
    r"continue|"
    r"let'?s\s+begin|"
    r"get\s+started|"
    r"open\s+survey|"
    r"yes(?:,\s*start)?"
    r")\s*[!.]?$",
    re.I,
)
_START_PAYLOAD_RE = re.compile(
    r"^\s*(?:start|start_survey|begin|begin_survey|continue|get_started)\s*$",
    re.I,
)


@dataclass
class NormalizedWaInboundReply:
    sender_phone: str = ""
    message_type: str = ""
    raw_text: str = ""
    button_text: str = ""
    button_title: str = ""
    button_payload: str = ""
    button_id: str = ""
    normalized_answer: str = ""
    normalized_action: str | None = None
    extracted_fields: dict[str, Any] = field(default_factory=dict)

    def to_log_dict(self) -> dict[str, Any]:
        return asdict(self)


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def is_start_survey_label(value: str) -> bool:
    raw = _clean(value)
    if not raw:
        return False
    if _START_LABEL_RE.match(raw):
        return True
    if _START_PAYLOAD_RE.match(_normalize_key(raw)):
        return True
    return _normalize_key(raw) in {
        "start",
        "start_survey",
        "begin",
        "begin_survey",
        "continue",
        "lets_begin",
        "get_started",
        "open_survey",
        "yes",
    }


def matches_start_trigger(value: str, extra_triggers: list[str] | None = None) -> bool:
    """True when inbound value is a generic or template-specific start action."""
    raw = _clean(value)
    if not raw:
        return False
    if is_start_survey_label(raw):
        return True
    if not extra_triggers:
        return False
    norm = _normalize_key(raw)
    lowered = raw.lower()
    for trigger in extra_triggers:
        t = _clean(trigger)
        if not t:
            continue
        if lowered == t.lower() or norm == _normalize_key(t):
            return True
    return False


def detect_start_action(
    reply: NormalizedWaInboundReply,
    *,
    extra_triggers: list[str] | None = None,
) -> str | None:
    candidates = [
        reply.button_title,
        reply.button_text,
        reply.button_payload,
        reply.button_id,
        reply.raw_text,
        reply.normalized_answer,
    ]
    for raw in candidates:
        if matches_start_trigger(raw, extra_triggers):
            return START_ACTION
    return None


def parse_telnyx_wa_inbound_record(
    record: dict[str, Any],
    *,
    sender_phone: str = "",
) -> NormalizedWaInboundReply:
    """Parse Telnyx message.received record into one normalized survey reply object."""
    from app.services.telnyx_inbound_messaging_service import (
        _deep_wa_reply_text,
        _extract_message_text,
        extract_wa_button_reply,
    )

    button = extract_wa_button_reply(record)
    raw_text = _clean(_extract_message_text(record))
    if not raw_text:
        raw_text = _clean(_deep_wa_reply_text(record))

    whatsapp_message = record.get("whatsapp_message")
    message_type = _clean(record.get("type") or record.get("record_type"))
    if isinstance(whatsapp_message, dict):
        message_type = _clean(whatsapp_message.get("type") or message_type)

    body_field = record.get("body")
    button_payload = ""
    if isinstance(body_field, dict):
        button_payload = _clean(body_field.get("payload") or body_field.get("id"))
    elif isinstance(body_field, str):
        button_payload = _clean(body_field)

    button_id = _clean(button.get("id")) or button_payload
    button_title = _clean(button.get("title"))
    button_text = button_title or raw_text

    normalized_answer = button_title or raw_text or button_id or button_payload

    reply = NormalizedWaInboundReply(
        sender_phone=_clean(sender_phone),
        message_type=message_type.lower() or "unknown",
        raw_text=raw_text,
        button_text=button_text,
        button_title=button_title,
        button_payload=button_payload,
        button_id=button_id,
        normalized_answer=normalized_answer,
        extracted_fields={
            "record_type": _clean(record.get("type")),
            "direction": _clean(record.get("direction")),
            "body_field_type": type(body_field).__name__,
            "whatsapp_message_type": _clean(
                whatsapp_message.get("type") if isinstance(whatsapp_message, dict) else ""
            ),
            "button_reply": button,
        },
    )
    reply.normalized_action = detect_start_action(reply)
    return reply


def log_raw_telnyx_inbound(
    *,
    record: dict[str, Any],
    org_id: str | None = None,
    message_id: str | None = None,
    sender_phone: str | None = None,
) -> None:
    """Log full inbound payload before parsing (truncated for safety)."""
    try:
        raw_json = json.dumps(record, ensure_ascii=False)
    except Exception:
        raw_json = str(record)
    logger.info(
        "%s raw_webhook org=%s message_id=%s from=%s payload=%s",
        LOG_PREFIX,
        org_id,
        message_id,
        sender_phone,
        raw_json[:4000],
    )


def log_normalized_inbound(
    reply: NormalizedWaInboundReply,
    *,
    phase: str,
    order_id: str | None = None,
    session_id: str | None = None,
    conv_step: int | None = None,
    awaiting_start: bool | None = None,
    send_result: bool | None = None,
    next_template_id: int | None = None,
    next_template_name: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    logger.info(
        "%s %s order=%s session=%s conv_step=%s awaiting_start=%s action=%s "
        "normalized_answer=%r button_title=%r button_id=%r button_payload=%r "
        "message_type=%s send_result=%s next_template_id=%s next_template_name=%s fields=%s extra=%s",
        LOG_PREFIX,
        phase,
        order_id,
        session_id,
        conv_step,
        awaiting_start,
        reply.normalized_action,
        reply.normalized_answer[:120],
        reply.button_title[:80],
        reply.button_id[:80],
        reply.button_payload[:80],
        reply.message_type,
        send_result,
        next_template_id,
        next_template_name,
        reply.extracted_fields,
        extra or {},
    )


def welcome_start_triggers_from_config(config: dict[str, Any]) -> list[str]:
    runtime = config.get("builder_runtime")
    if isinstance(runtime, dict):
        triggers = runtime.get("start_triggers")
        if isinstance(triggers, list):
            return [str(x) for x in triggers if str(x).strip()]
    triggers = config.get("start_triggers")
    if isinstance(triggers, list):
        return [str(x) for x in triggers if str(x).strip()]
    return []
