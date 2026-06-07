"""Open-text step detection for WhatsApp survey runtime."""

from __future__ import annotations

from typing import Any

OPEN_TEXT_REPLY_TYPES = frozenset({"text", "long_text", "contact", "date"})

VOICE_NOTE_FALLBACK_MESSAGE = (
    "Please reply using the buttons or type your answer. "
    "Voice notes are only supported for comment-style questions."
)

VOICE_NOTE_AUDIO_MESSAGE_TYPES = frozenset(
    {"audio", "voice", "ptt", "voice_note", "media_audio", "media_voice"}
)


def is_open_text_question(question: dict[str, Any] | None) -> bool:
    if not isinstance(question, dict):
        return False
    reply_type = str(question.get("reply_type") or "text").strip().lower()
    return reply_type in OPEN_TEXT_REPLY_TYPES


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
