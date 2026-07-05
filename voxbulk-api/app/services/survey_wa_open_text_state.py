"""Conversation state helpers for tell-us-more and closing open-text steps."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from app.services.survey_wa_flow_constants import (
    CLOSING_OUTCOME_ANSWERED,
    CLOSING_OUTCOME_SKIPPED_TIMEOUT,
    KEY_CLOSING_DEADLINE,
    KEY_CLOSING_OUTCOME,
    KEY_SURVEY_STARTED_AT,
    KEY_TUM_DEADLINE,
    KEY_TUM_ELIGIBLE_FOLLOWUP,
    KEY_TUM_FOLLOWUP_HANDLED,
    KEY_TUM_OUTCOME,
    KEY_TUM_PENDING,
    KEY_TUM_SENT_AT,
    OPEN_TEXT_TIMEOUT_SEC,
    TUM_OUTCOME_ANSWERED,
    TUM_OUTCOME_SKIPPED_TIMEOUT,
)

KEY_VAGUE_FOLLOWUP_SENT = "vague_followup_sent_at"
KEY_VAGUE_FOLLOWUP_ANSWERED = "vague_followup_answered"


def mark_survey_started(conv: dict[str, Any]) -> None:
    if not conv.get(KEY_SURVEY_STARTED_AT):
        conv[KEY_SURVEY_STARTED_AT] = datetime.now(timezone.utc).isoformat()


def mark_tell_us_more_prompt_sent(conv: dict[str, Any]) -> None:
    now = datetime.now(timezone.utc)
    conv[KEY_TUM_SENT_AT] = now.isoformat()
    conv[KEY_TUM_DEADLINE] = (now + timedelta(seconds=OPEN_TEXT_TIMEOUT_SEC)).isoformat()
    conv.pop(KEY_TUM_OUTCOME, None)
    conv[KEY_TUM_ELIGIBLE_FOLLOWUP] = False
    conv[KEY_TUM_FOLLOWUP_HANDLED] = False


def mark_tell_us_more_answered(conv: dict[str, Any]) -> None:
    conv[KEY_TUM_OUTCOME] = TUM_OUTCOME_ANSWERED
    conv[KEY_TUM_ELIGIBLE_FOLLOWUP] = False
    conv.pop(KEY_TUM_PENDING, None)
    conv.pop(KEY_TUM_DEADLINE, None)


def mark_tell_us_more_timeout(conv: dict[str, Any]) -> None:
    conv[KEY_TUM_OUTCOME] = TUM_OUTCOME_SKIPPED_TIMEOUT
    conv[KEY_TUM_ELIGIBLE_FOLLOWUP] = True
    conv.pop(KEY_TUM_PENDING, None)
    conv.pop(KEY_TUM_DEADLINE, None)


def mark_closing_answered(conv: dict[str, Any]) -> None:
    conv[KEY_CLOSING_OUTCOME] = CLOSING_OUTCOME_ANSWERED
    conv.pop(KEY_CLOSING_DEADLINE, None)


def mark_closing_timeout(conv: dict[str, Any]) -> None:
    conv[KEY_CLOSING_OUTCOME] = CLOSING_OUTCOME_SKIPPED_TIMEOUT
    conv.pop(KEY_CLOSING_DEADLINE, None)


def is_awaiting_tell_us_more_reply(conv: dict[str, Any]) -> bool:
    """True while the contact should answer the tell-us-more prompt (low rating branch)."""
    if conv.get(KEY_TUM_PENDING):
        return True
    if conv.get(KEY_TUM_OUTCOME):
        return False
    node_key = str(conv.get("current_node_key") or "")
    if node_key.startswith("builder_tell_"):
        return True
    if conv.get(KEY_TUM_SENT_AT) and not conv.get(KEY_TUM_OUTCOME):
        return True
    return bool(conv.get("tell_us_more_asked")) and not conv.get(KEY_TUM_OUTCOME)


def is_awaiting_vague_followup_reply(conv: dict[str, Any]) -> bool:
    """True after auto-followup 'What was wrong with…' until the contact answers."""
    if conv.get(KEY_VAGUE_FOLLOWUP_ANSWERED):
        return False
    if conv.get("awaiting_followup"):
        return True
    if conv.get(KEY_VAGUE_FOLLOWUP_SENT):
        return True
    if conv.get("followup_for_step") is not None and conv.get(KEY_VAGUE_FOLLOWUP_SENT):
        return True
    return False


def mark_vague_followup_prompt_sent(conv: dict[str, Any], *, step: int) -> None:
    now = datetime.now(timezone.utc)
    conv["awaiting_followup"] = True
    conv["followup_for_step"] = int(step or 0)
    conv[KEY_VAGUE_FOLLOWUP_SENT] = now.isoformat()
    conv.pop(KEY_VAGUE_FOLLOWUP_ANSWERED, None)


def mark_vague_followup_answered(conv: dict[str, Any]) -> None:
    conv[KEY_VAGUE_FOLLOWUP_ANSWERED] = True
    conv.pop("awaiting_followup", None)
    conv.pop("followup_for_step", None)


def is_buttonless_open_text_question(question: dict[str, Any] | None) -> bool:
    if not isinstance(question, dict):
        return False
    role = str(question.get("step_role") or "").strip().lower()
    reply_type = str(question.get("reply_type") or "").strip().lower()
    options = question.get("options") or []
    if role in {"tell_us_more", "reason", "final_feedback_text"}:
        return True
    if reply_type in {"text", "long_text", "contact", "date"} and not options:
        return True
    return False
