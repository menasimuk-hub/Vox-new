"""Open-text step detection for WhatsApp survey runtime."""

from __future__ import annotations

from typing import Any

OPEN_TEXT_REPLY_TYPES = frozenset({"text", "long_text", "contact", "date"})

OPEN_TEXT_STEP_ROLES = frozenset({"reason", "tell_us_more", "final_feedback_text", "follow_up", "improvement"})

VOICE_NOTE_FALLBACK_MESSAGE = (
    "Please reply using the buttons or type your answer. "
    "Voice notes are only supported for comment-style questions."
)

VOICE_NOTE_NO_MEDIA_MESSAGE = (
    "We couldn't process that voice note. Please try again or type your answer."
)

OPEN_TEXT_OUTBOUND_KINDS = frozenset(
    {"tell_us_more", "vague_auto_followup", "final_feedback"}
)

VOICE_NOTE_AUDIO_MESSAGE_TYPES = frozenset(
    {"audio", "voice", "ptt", "voice_note", "media_audio", "media_voice"}
)


def is_open_text_question(question: dict[str, Any] | None) -> bool:
    if not isinstance(question, dict):
        return False
    from app.services.survey_step_bank_service import normalize_step_role

    role = normalize_step_role(str(question.get("step_role") or ""))
    if role in OPEN_TEXT_STEP_ROLES:
        return True
    reply_type = str(question.get("reply_type") or "text").strip().lower()
    return reply_type in OPEN_TEXT_REPLY_TYPES


def _conv_expects_open_text_voice(conv: dict[str, Any]) -> bool:
    kind = str(conv.get("last_outbound_kind") or "").strip()
    return kind in OPEN_TEXT_OUTBOUND_KINDS


def allows_voice_note_answer(
    question: dict[str, Any] | None,
    *,
    answer_context: str,
    conv: dict[str, Any] | None = None,
) -> bool:
    ctx = str(answer_context or "normal").strip().lower()
    if ctx in {"final_feedback", "followup"}:
        return True
    c = conv or {}
    if _conv_expects_open_text_voice(c):
        return True
    if c.get("tell_us_more_pending") or c.get("awaiting_followup"):
        return True
    if c.get("awaiting_final_feedback_text"):
        return True
    from app.services.survey_wa_open_text_state import (
        is_awaiting_tell_us_more_reply,
        is_awaiting_vague_followup_reply,
    )

    if is_awaiting_tell_us_more_reply(c):
        return True
    if is_awaiting_vague_followup_reply(c):
        return True
    if isinstance(question, dict):
        source = str(question.get("source") or "")
        node_key = str(question.get("node_key") or "")
        if source == "builder_tell_us_more_template" or node_key.startswith("builder_tell_"):
            return True
    return is_open_text_question(question)


def voice_note_answer_context(
    *,
    conv: dict[str, Any] | None,
    question: dict[str, Any] | None,
) -> str:
    """Map inbound step state to voice-note answer_context (followup vs normal)."""
    c = conv or {}
    if c.get("awaiting_final_feedback_text"):
        return "final_feedback"
    if _conv_expects_open_text_voice(c):
        return "followup"
    if c.get("tell_us_more_pending") or c.get("awaiting_followup"):
        return "followup"
    from app.services.survey_wa_open_text_state import (
        is_awaiting_tell_us_more_reply,
        is_awaiting_vague_followup_reply,
    )

    if is_awaiting_tell_us_more_reply(c):
        return "followup"
    if is_awaiting_vague_followup_reply(c):
        return "followup"
    if isinstance(question, dict):
        from app.services.survey_step_bank_service import normalize_step_role

        role = normalize_step_role(str(question.get("step_role") or ""))
        if role in OPEN_TEXT_STEP_ROLES:
            return "followup"
    return "normal"


def is_voice_message_type(message_type: str) -> bool:
    clean = str(message_type or "").strip().lower()
    if not clean:
        return False
    if clean in VOICE_NOTE_AUDIO_MESSAGE_TYPES:
        return True
    return "audio" in clean or clean.endswith("_voice")


def enrich_answer_with_voice_fields(answer: dict[str, Any], *, job_id: str, status: str = "pending") -> dict[str, Any]:
    out = dict(answer)
    out["answer_source"] = "voice_note"
    out["transcription_status"] = status
    out["voice_note_job_id"] = job_id
    out.setdefault("answer_text", out.get("answer") or "")
    return out


def resolve_answer_text(item: dict[str, Any]) -> str:
    """Canonical free-text answer for reporting (typed or transcribed)."""
    if not isinstance(item, dict):
        return ""
    return str(
        item.get("answer_text")
        or item.get("answer_display")
        or item.get("answer")
        or item.get("final_additional_feedback")
        or ""
    ).strip()


def answer_has_pending_transcription(item: dict[str, Any]) -> bool:
    if not isinstance(item, dict):
        return False
    if str(item.get("answer_source") or "") != "voice_note":
        return False
    return str(item.get("transcription_status") or "") in {"pending", "retrying", "transcribing"}


VOICE_ANSWER_METADATA_KEYS = (
    "answer_source",
    "answer_text",
    "transcription_status",
    "transcription_error",
    "detected_language",
    "voice_note_job_id",
    "audio_file_path",
    "audio_mime_type",
    "audio_file_size",
    "inbound_message_id",
    "provider_media_id",
    "transcribed_at",
)


def merge_voice_metadata(target: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    out = dict(target)
    for key in VOICE_ANSWER_METADATA_KEYS:
        if key in source and source[key] is not None:
            out[key] = source[key]
    return out


def apply_transcript_to_answer(answer: dict[str, Any], *, text: str, detected_language: str | None, status: str) -> dict[str, Any]:
    out = dict(answer)
    cleaned = str(text or "").strip()
    out["answer"] = cleaned
    out["answer_text"] = cleaned
    out["answer_display"] = cleaned
    out["answer_source"] = out.get("answer_source") or "voice_note"
    out["transcription_status"] = status
    if detected_language:
        out["detected_language"] = detected_language
    return out
