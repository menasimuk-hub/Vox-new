"""Expo WhatsApp / web voice notes — Whisper STT + translate answer to English."""

from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.expo import ExpoResponse, ExpoSession, ExpoVoiceNoteJob
from app.services.customer_feedback.feedback_answer_service import (
    TRANSLATION_UNAVAILABLE_EN,
    translate_answer_to_english,
)
from app.services.voice_transcription_service import is_low_quality_transcript

logger = logging.getLogger(__name__)
LOG_PREFIX = "[expo-voice]"

_ARABIC_SCRIPT_RE = re.compile(r"[\u0600-\u06FF]")


def correct_detected_language(text: str, detected: str | None) -> str | None:
    """Force ``ar`` when the transcript contains Arabic script.

    Whisper-family STT sometimes mislabels Arabic voice notes as Turkish, Farsi, or Urdu
    (confusable accent/phoneme cues) — trust the actual script over the model's language guess.
    """
    clean = str(text or "")
    if _ARABIC_SCRIPT_RE.search(clean):
        det = str(detected or "").strip().lower()
        if det != "ar":
            return "ar"
    return detected


def _english_or_original(translated: dict[str, Any], original: str) -> str:
    """Prefer English translation; fall back to original if CF returns the unavailable sentinel."""
    answer_en = str(translated.get("answer_text_en") or "").strip()
    if not answer_en or answer_en == TRANSLATION_UNAVAILABLE_EN:
        return original
    return answer_en


def enqueue_expo_voice_job(job_id: str) -> None:
    try:
        from app.workers.expo_voice_note_tasks import transcribe_expo_voice_note

        transcribe_expo_voice_note.delay(job_id=job_id)
    except Exception as exc:
        logger.warning("%s enqueue_failed job=%s err=%s", LOG_PREFIX, job_id, str(exc)[:200])


def extract_audio_media(record: dict[str, Any] | None) -> dict[str, str] | None:
    if not isinstance(record, dict):
        return None
    from app.services.survey_wa_voice_note_media_service import extract_media_items

    items = extract_media_items(record)
    for item in items:
        ct = str(item.get("content_type") or "").lower()
        url = str(item.get("url") or "").strip()
        mid = str(item.get("provider_media_id") or "").strip()
        if ct.startswith("audio") or ct in {"", "audio", "ogg", "opus"} or url or mid:
            return {
                "url": url,
                "provider_media_id": mid,
                "content_type": ct if ct.startswith("audio/") else "audio/ogg",
            }
    # Meta Cloud API top-level audio
    for key in ("audio", "voice", "ptt"):
        block = record.get(key)
        if isinstance(block, dict):
            mid = str(block.get("id") or "").strip()
            url = str(block.get("url") or block.get("link") or "").strip()
            if mid or url:
                return {
                    "url": url,
                    "provider_media_id": mid,
                    "content_type": str(block.get("mime_type") or "audio/ogg"),
                }
    return None


def is_audio_inbound(record: dict[str, Any] | None) -> bool:
    if not isinstance(record, dict):
        return False
    msg_type = str(record.get("type") or record.get("message_type") or "").strip().lower()
    if msg_type in {"audio", "voice", "ptt"}:
        return True
    if isinstance(record.get("audio"), dict) or isinstance(record.get("voice"), dict):
        return True
    return extract_audio_media(record) is not None


def process_voice_for_session(
    db: Session,
    *,
    session: ExpoSession,
    record: dict[str, Any] | None,
    inbound_message_id: str = "",
) -> dict[str, Any]:
    """Transcribe + translate inbound voice; return fields for session advance (no response row yet)."""
    media = extract_audio_media(record)
    if not media:
        return {"ok": False, "error": "no_audio_media"}

    now = datetime.utcnow()
    job = ExpoVoiceNoteJob(
        id=str(uuid.uuid4()),
        org_id=session.org_id,
        session_id=session.id,
        booth_id=session.booth_id,
        response_id=None,
        inbound_message_id=(inbound_message_id or f"wa:{uuid.uuid4().hex[:12]}")[:128],
        provider_media_id=(media.get("provider_media_id") or "")[:255] or None,
        media_url=media.get("url") or None,
        status="pending",
        created_at=now,
        updated_at=now,
    )
    db.add(job)
    db.commit()

    result = process_expo_voice_job(db, job.id)
    if not result.get("ok"):
        return {"ok": False, "error": result.get("error") or "transcription_failed", "job_id": job.id}

    return {
        "ok": True,
        "job_id": job.id,
        "original_text": result.get("original_text") or "",
        "answer_text_en": result.get("answer_text_en") or "",
        "detected_language": result.get("detected_language"),
    }


def process_expo_voice_job(db: Session, job_id: str) -> dict[str, Any]:
    job = db.get(ExpoVoiceNoteJob, job_id)
    if job is None:
        return {"ok": False, "error": "job_not_found"}
    if job.status == "completed" and (job.translated_text or job.original_text):
        return {
            "ok": True,
            "duplicate": True,
            "original_text": job.original_text,
            "answer_text_en": job.translated_text or job.original_text,
            "detected_language": job.detected_language,
        }

    response = db.get(ExpoResponse, job.response_id) if job.response_id else None
    job.status = "transcribing"
    job.updated_at = datetime.utcnow()
    db.add(job)
    db.commit()

    try:
        text = ""
        detected: str | None = None
        if job.media_url or job.provider_media_id:
            from app.services.customer_feedback.feedback_voice_service import transcribe_inbound

            session = db.get(ExpoSession, job.session_id)
            phone = str(session.visitor_phone or "") if session else ""
            media_block: dict[str, Any] = {
                "url": job.media_url or "",
                "content_type": "audio/ogg",
                "id": job.provider_media_id or "",
            }
            # Resolve Meta media id → url when needed
            if not media_block["url"] and media_block["id"]:
                from app.services.expo.business_card_ocr_service import _resolve_meta_media_url

                resolved = _resolve_meta_media_url(db, str(media_block["id"]))
                if resolved:
                    media_block["url"] = resolved
                    job.media_url = resolved
            record = {"type": "audio", "audio": media_block, "media": [media_block]}
            text, ok, detected = transcribe_inbound(
                db,
                record=record,
                customer_phone=phone,
                language="auto",
            )
            if not ok or not text or is_low_quality_transcript(text):
                raise RuntimeError("empty_transcript")
        else:
            raise RuntimeError("missing_media")

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

        job.original_text = original
        job.translated_text = answer_en
        job.transcript_text = original
        job.detected_language = detected
        job.status = "completed"
        job.error_detail = None
        job.updated_at = datetime.utcnow()
        db.add(job)

        if response is not None:
            response.original_text = original
            response.answer_text = answer_en
            response.answer_text_en = answer_en
            response.answer_source = "voice"
            db.add(response)

        session = db.get(ExpoSession, job.session_id)
        if session is not None and detected:
            session.detected_language = str(detected)[:16]
            db.add(session)

        db.commit()
        logger.info("%s completed job=%s chars=%s lang=%s", LOG_PREFIX, job.id, len(original), detected)
        return {
            "ok": True,
            "job_id": job.id,
            "original_text": original,
            "answer_text_en": answer_en,
            "detected_language": detected,
        }
    except Exception as exc:
        job.status = "failed"
        job.error_detail = str(exc)[:2000]
        job.updated_at = datetime.utcnow()
        db.add(job)
        db.commit()
        logger.warning("%s failed job=%s err=%s", LOG_PREFIX, job_id, exc)
        return {"ok": False, "error": str(exc)[:500]}


def process_web_voice_bytes(
    db: Session,
    *,
    session: ExpoSession,
    audio_bytes: bytes,
    filename: str = "voice.webm",
    content_type: str = "audio/webm",
) -> dict[str, Any]:
    """Browser voice upload → Whisper STT + English translation (sync, like WA path)."""
    if not audio_bytes:
        return {"ok": False, "error": "empty_upload"}

    now = datetime.utcnow()
        job = ExpoVoiceNoteJob(
        id=str(uuid.uuid4()),
        org_id=session.org_id,
        session_id=session.id,
        booth_id=session.booth_id,
        response_id=None,
        inbound_message_id=f"web:{uuid.uuid4().hex[:12]}"[:128],
        provider_media_id=None,
        media_url=None,
        status="transcribing",
        created_at=now,
        updated_at=now,
    )
    db.add(job)
    db.commit()

    try:
        # Persist original recording for dashboard playback.
        try:
            from pathlib import Path

            root = Path("data") / "expo_voice" / str(session.org_id)
            root.mkdir(parents=True, exist_ok=True)
            safe_name = (filename or "voice.webm").replace("/", "_").replace("\\", "_")[:80]
            path = root / f"{job.id}_{safe_name}"
            path.write_bytes(audio_bytes)
            # Store relative path in media_url for auth download endpoint.
            job.media_url = f"/expo/results/voice-notes/{job.id}/audio"
            job.provider_media_id = str(path).replace("\\", "/")
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

        job.original_text = original
        job.translated_text = answer_en
        job.transcript_text = original
        job.detected_language = str(detected)[:32] if detected else None
        job.status = "completed"
        job.error_detail = None
        job.updated_at = datetime.utcnow()
        db.add(job)
        if detected:
            session.detected_language = str(detected)[:16]
            db.add(session)
        db.commit()
        return {
            "ok": True,
            "job_id": job.id,
            "original_text": original,
            "answer_text_en": answer_en,
            "detected_language": detected,
        }
    except Exception as exc:
        job.status = "failed"
        job.error_detail = str(exc)[:2000]
        job.updated_at = datetime.utcnow()
        db.add(job)
        db.commit()
        logger.warning("%s web_voice_failed job=%s err=%s", LOG_PREFIX, job.id, exc)
        return {"ok": False, "error": str(exc)[:500], "job_id": job.id}
