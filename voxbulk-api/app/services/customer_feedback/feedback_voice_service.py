"""DeepInfra voice note transcription for Customer Feedback WhatsApp."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.services.voice_transcription_service import VoiceTranscriptionService, is_low_quality_transcript

logger = logging.getLogger(__name__)


def is_voice_inbound(record: dict[str, Any] | None) -> bool:
    if not record:
        return False
    try:
        from app.services.survey_wa_inbound_parse_service import parse_telnyx_wa_inbound_record
        from app.services.survey_wa_open_text_service import is_voice_message_type
        from app.services.survey_wa_voice_note_media_service import extract_media_items

        normalized = parse_telnyx_wa_inbound_record(record, sender_phone="")
        if normalized.is_voice_note:
            return True
        for candidate in (
            record.get("type"),
            (record.get("whatsapp_message") or {}).get("type")
            if isinstance(record.get("whatsapp_message"), dict)
            else None,
        ):
            if is_voice_message_type(str(candidate or "")):
                return True
        media_items = extract_media_items(record)
        for item in media_items:
            ctype = str(item.get("content_type") or item.get("mime_type") or "").lower()
            if ctype.startswith("audio/") or "ogg" in ctype:
                return True
    except Exception:
        logger.debug("feedback_voice_detect_failed", exc_info=True)
    return False


def transcribe_inbound(
    db: Session,
    *,
    record: dict[str, Any],
    customer_phone: str,
    language: str | None = None,
) -> tuple[str, bool]:
    """Return (transcript, ok)."""
    result = VoiceTranscriptionService.transcribe_inbound(
        db,
        record=record,
        customer_phone=customer_phone,
        language=language,
    )
    text = str(result.transcript or "").strip()
    if not result.ok or not text or is_low_quality_transcript(text):
        return text, False
    return text, True
