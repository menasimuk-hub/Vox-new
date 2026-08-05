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
from app.services.voice_transcription_service import (
    is_low_quality_transcript,
    looks_like_hallucination,
)

logger = logging.getLogger(__name__)
LOG_PREFIX = "[smart-card-voice]"

# Re-export for callers that import from this module only.
__all__ = (
    "extract_audio_media",
    "is_audio_inbound",
    "process_voice_for_session",
    "process_web_voice_bytes",
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
        low_confidence = looks_like_hallucination(original)

        job.transcript = original
        job.detected_language = (str(detected)[:32] if detected else None)
        job.low_confidence = low_confidence
        job.status = "completed"
        job.error = None
        job.updated_at = datetime.utcnow()
        db.add(job)
        db.commit()

        logger.info(
            "%s completed job=%s chars=%s lang=%s low_confidence=%s",
            LOG_PREFIX,
            job.id,
            len(original),
            detected,
            low_confidence,
        )
        return {
            "ok": True,
            "job_id": job.id,
            "original_text": original,
            "answer_text_en": answer_en,
            "detected_language": detected,
            "low_confidence": low_confidence,
        }
    except Exception as exc:
        job.status = "failed"
        job.error = str(exc)[:2000]
        job.updated_at = datetime.utcnow()
        db.add(job)
        db.commit()
        logger.warning("%s failed job=%s err=%s", LOG_PREFIX, job.id, exc)
        return {"ok": False, "error": str(exc)[:500], "job_id": job.id}


def process_web_voice_bytes(
    db: Session,
    *,
    session: SmartCardSession,
    audio_bytes: bytes,
    filename: str = "voice.webm",
    content_type: str = "audio/webm",
) -> dict[str, Any]:
    """Browser voice upload — store original audio, Whisper STT + English for the answer text."""
    if not audio_bytes:
        return {"ok": False, "error": "empty_upload"}

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
        # Keep the original recording (no re-encode) for playback / audit.
        try:
            from pathlib import Path

            root = Path("data") / "smart_card_voice" / str(session.org_id)
            root.mkdir(parents=True, exist_ok=True)
            safe_name = (filename or "voice.webm").replace("/", "_").replace("\\", "_")[:80]
            path = root / f"{job.id}_{safe_name}"
            path.write_bytes(audio_bytes)
            job.storage_path = str(path).replace("\\", "/")
            db.add(job)
            db.commit()
        except Exception as store_exc:
            logger.warning("%s store_audio_failed job=%s err=%s", LOG_PREFIX, job.id, store_exc)

        from app.services.voice_transcription_service import VoiceTranscriptionService

        stt = VoiceTranscriptionService.transcribe_uploaded_audio(
            db,
            audio_bytes=audio_bytes,
            filename=filename or "voice.webm",
            content_type=content_type or "audio/webm",
            language="auto",
        )
        text = str(getattr(stt, "transcript", None) or getattr(stt, "text", None) or "").strip()
        detected = getattr(stt, "detected_language", None)
        if not getattr(stt, "ok", False) or not text or is_low_quality_transcript(text):
            raise RuntimeError(str(getattr(stt, "error", None) or "empty_transcript"))

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
        low_confidence = bool(getattr(stt, "low_confidence", False)) or looks_like_hallucination(original)
        provider = str(getattr(stt, "stt_provider", None) or "") or None

        job.transcript = original
        job.detected_language = (str(detected)[:32] if detected else None)
        job.stt_provider = (provider[:32] if provider else None)
        job.low_confidence = low_confidence
        job.status = "completed"
        job.error = None
        job.updated_at = datetime.utcnow()
        db.add(job)
        db.commit()
        logger.info(
            "%s web_completed job=%s chars=%s lang=%s provider=%s low_confidence=%s",
            LOG_PREFIX,
            job.id,
            len(original),
            detected,
            provider,
            low_confidence,
        )
        return {
            "ok": True,
            "job_id": job.id,
            "original_text": original,
            "answer_text_en": answer_en,
            "detected_language": detected,
            "stt_provider": provider,
            "low_confidence": low_confidence,
        }
    except Exception as exc:
        job.status = "failed"
        job.error = str(exc)[:2000]
        job.updated_at = datetime.utcnow()
        db.add(job)
        db.commit()
        logger.warning("%s web_failed job=%s err=%s", LOG_PREFIX, job.id, exc)
        return {"ok": False, "error": str(exc)[:500], "job_id": job.id}
