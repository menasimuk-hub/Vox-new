"""Smart Card WhatsApp voice notes — Whisper STT + translate answer to English.

Reuses Expo helpers for inbound audio detection/media extraction; sync transcription
(no Celery) via the same Customer Feedback ``transcribe_inbound`` path Expo uses.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.smart_card import SmartCardSession, SmartCardVoiceNoteJob
from app.services.customer_feedback.feedback_answer_service import (
    TRANSLATION_UNAVAILABLE_EN,
    translate_answer_to_english,
)
from app.services.expo.voice_note_service import (
    correct_detected_language,
    extract_audio_media,
    is_audio_inbound,
)
from app.services.voice_transcription_service import is_low_quality_transcript

logger = logging.getLogger(__name__)
LOG_PREFIX = "[smart-card-voice]"

# Re-export for callers that import from this module only.
__all__ = (
    "extract_audio_media",
    "is_audio_inbound",
    "process_voice_for_session",
)


def _english_or_original(translated: dict[str, Any], original: str) -> str:
    answer_en = str(translated.get("answer_text_en") or "").strip()
    if not answer_en or answer_en == TRANSLATION_UNAVAILABLE_EN:
        return original
    return answer_en


def process_voice_for_session(
    db: Session,
    *,
    session: SmartCardSession,
    record: dict[str, Any] | None,
) -> dict[str, Any]:
    """Download/transcribe/translate inbound voice; return fields for session advance."""
    media = extract_audio_media(record)
    if not media:
        return {"ok": False, "error": "no_audio_media"}

    now = datetime.utcnow()
    job = SmartCardVoiceNoteJob(
        id=str(uuid.uuid4()),
        org_id=session.org_id,
        session_id=session.id,
        status="transcribing",
        created_at=now,
        updated_at=now,
    )
    db.add(job)
    db.commit()

    try:
        from app.services.customer_feedback.feedback_voice_service import transcribe_inbound

        phone = str(session.visitor_phone or "")
        media_block: dict[str, Any] = {
            "url": media.get("url") or "",
            "content_type": media.get("content_type") or "audio/ogg",
            "id": media.get("provider_media_id") or "",
        }
        if not media_block["url"] and media_block["id"]:
            from app.services.expo.business_card_ocr_service import _resolve_meta_media_url

            resolved = _resolve_meta_media_url(db, str(media_block["id"]))
            if resolved:
                media_block["url"] = resolved

        inbound_record = {"type": "audio", "audio": media_block, "media": [media_block]}
        text, ok, detected = transcribe_inbound(
            db,
            record=inbound_record,
            customer_phone=phone,
            language="auto",
        )
        if not ok or not text or is_low_quality_transcript(text):
            raise RuntimeError("empty_transcript")

        detected = correct_detected_language(text, detected)
        translated = translate_answer_to_english(
            db,
            answer=text,
            detected_language=detected,
            tpl=None,
            source_language=detected,
        )
        original = str(translated.get("original_text") or text).strip()
        answer_en = _english_or_original(translated, original)

        job.transcript = original
        job.status = "completed"
        job.error = None
        job.updated_at = datetime.utcnow()
        db.add(job)
        db.commit()

        logger.info(
            "%s completed job=%s chars=%s lang=%s",
            LOG_PREFIX,
            job.id,
            len(original),
            detected,
        )
        return {
            "ok": True,
            "job_id": job.id,
            "original_text": original,
            "answer_text_en": answer_en,
            "detected_language": detected,
        }
    except Exception as exc:
        job.status = "failed"
        job.error = str(exc)[:2000]
        job.updated_at = datetime.utcnow()
        db.add(job)
        db.commit()
        logger.warning("%s failed job=%s err=%s", LOG_PREFIX, job.id, exc)
        return {"ok": False, "error": str(exc)[:500], "job_id": job.id}
