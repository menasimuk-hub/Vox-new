"""Async Customer Feedback voice-note STT + translation (WA + web)."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.models.customer_feedback import FeedbackResponse, FeedbackSession, FeedbackVoiceNoteJob
from app.services.customer_feedback.feedback_answer_service import translate_answer_to_english
from app.services.voice_transcription_service import VoiceTranscriptionService, is_low_quality_transcript

logger = logging.getLogger(__name__)
LOG_PREFIX = "[feedback-voice]"


def enqueue_feedback_voice_job(job_id: str) -> None:
    try:
        from app.workers.feedback_voice_note_tasks import transcribe_feedback_voice_note

        transcribe_feedback_voice_note.delay(job_id=job_id)
    except Exception as exc:
        logger.warning("%s enqueue_failed job=%s err=%s", LOG_PREFIX, job_id, str(exc)[:200])


def create_pending_response_and_job(
    db: Session,
    *,
    session: FeedbackSession,
    location_id: str,
    survey_type_id: str,
    question_key: str,
    step_order: int,
    media_url: str | None = None,
    audio_file_path: str | None = None,
    audio_original_filename: str | None = None,
    audio_mime_type: str | None = None,
    inbound_message_id: str = "",
    provider_media_id: str = "",
) -> tuple[FeedbackResponse, FeedbackVoiceNoteJob]:
    now = datetime.utcnow()
    response = FeedbackResponse(
        id=str(uuid.uuid4()),
        session_id=session.id,
        org_id=session.org_id,
        location_id=location_id,
        survey_type_id=survey_type_id,
        question_key=question_key,
        answer_text=None,
        original_text=None,
        answer_text_en=None,
        translation_status="pending",
        transcription_status="pending",
        detected_language=None,
        step_order=step_order,
        answer_source="voice",
        created_at=now,
    )
    db.add(response)
    db.flush()

    inbound = str(inbound_message_id or "").strip() or f"web:{response.id}"
    media_id = str(provider_media_id or "").strip() or (f"path:{audio_file_path}" if audio_file_path else "")
    job = FeedbackVoiceNoteJob(
        id=str(uuid.uuid4()),
        org_id=session.org_id,
        session_id=session.id,
        response_id=response.id,
        inbound_message_id=inbound[:128],
        provider_media_id=media_id[:128],
        media_url=media_url,
        audio_file_path=audio_file_path,
        audio_original_filename=audio_original_filename,
        audio_mime_type=audio_mime_type,
        transcription_status="pending",
        translation_status="pending",
        created_at=now,
        updated_at=now,
    )
    db.add(job)
    db.flush()
    return response, job


def process_voice_job(db: Session, job_id: str) -> dict[str, Any]:
    job = db.get(FeedbackVoiceNoteJob, job_id)
    if job is None:
        return {"ok": False, "error": "job_not_found"}
    if job.transcription_status == "completed" and job.original_text:
        return {"ok": True, "duplicate": True}

    response = db.get(FeedbackResponse, job.response_id)
    if response is None:
        return {"ok": False, "error": "response_not_found"}

    job.transcription_status = "transcribing"
    job.updated_at = datetime.utcnow()
    db.add(job)
    db.commit()

    try:
        text = ""
        detected: str | None = None
        if job.audio_file_path and Path(job.audio_file_path).is_file():
            path = Path(job.audio_file_path)
            result = VoiceTranscriptionService.transcribe_uploaded_audio(
                db,
                audio_bytes=path.read_bytes(),
                filename=job.audio_original_filename or path.name,
                content_type=job.audio_mime_type or "audio/webm",
                language="auto",
            )
            text = str(getattr(result, "transcript", "") or "").strip()
            detected = getattr(result, "detected_language", None)
            ok = bool(getattr(result, "ok", False) and text and not is_low_quality_transcript(text))
            if not ok:
                raise RuntimeError(str(getattr(result, "error", "") or "empty_transcript"))
        elif job.media_url:
            # Reuse inbound helper with a synthetic record.
            from app.services.customer_feedback.feedback_voice_service import transcribe_inbound

            session = db.get(FeedbackSession, job.session_id)
            phone = str(session.visitor_phone or "") if session else ""
            record = {
                "type": "audio",
                "media": [
                    {
                        "url": job.media_url,
                        "content_type": job.audio_mime_type or "audio/ogg",
                        "id": job.provider_media_id or "",
                    }
                ],
            }
            text, ok, detected = transcribe_inbound(
                db,
                record=record,
                customer_phone=phone,
                language="auto",
            )
            if not ok or not text:
                raise RuntimeError("empty_transcript")
        else:
            raise RuntimeError("missing_media")

        translated = translate_answer_to_english(
            db,
            answer=text,
            detected_language=detected,
            tpl=None,
            source_language=detected,
        )
        original = str(translated.get("original_text") or text).strip()
        answer_en = str(translated.get("answer_text_en") or original).strip()
        t_status = str(translated.get("translation_status") or "completed")

        job.original_text = original
        job.translated_text = answer_en
        job.detected_language = detected
        job.transcription_status = "completed"
        job.translation_status = t_status
        job.transcription_error = None
        job.transcribed_at = datetime.utcnow()
        job.processed_at = datetime.utcnow()
        job.updated_at = datetime.utcnow()
        db.add(job)

        response.original_text = original
        response.answer_text = answer_en
        response.answer_text_en = answer_en
        response.translation_status = t_status
        response.transcription_status = "completed"
        response.detected_language = detected
        response.answer_source = "voice"
        db.add(response)

        if session := db.get(FeedbackSession, job.session_id):
            if detected:
                from app.services.customer_feedback.locale_service import map_stt_language_code

                mapped = map_stt_language_code(detected)
                if mapped and mapped != session.detected_language:
                    session.detected_language = mapped
                    db.add(session)

        db.commit()
        logger.info(
            "%s completed job=%s response=%s chars=%s lang=%s",
            LOG_PREFIX,
            job.id,
            response.id,
            len(original),
            detected,
        )
        return {"ok": True, "job_id": job.id, "response_id": response.id}
    except Exception as exc:
        # Never blank out a completed English/original from a prior success.
        if response.transcription_status == "completed" and (response.original_text or response.answer_text_en):
            job.transcription_error = str(exc)[:2000]
            job.updated_at = datetime.utcnow()
            db.add(job)
            db.commit()
            logger.exception("%s failed_after_completed job=%s err=%s", LOG_PREFIX, job.id, exc)
            return {"ok": True, "job_id": job.id, "duplicate": True, "kept_completed": True}

        job.retry_count = int(job.retry_count or 0) + 1
        job.transcription_status = "failed"
        job.translation_status = "failed"
        job.transcription_error = str(exc)[:2000]
        job.updated_at = datetime.utcnow()
        db.add(job)
        response.transcription_status = "failed"
        response.translation_status = "failed"
        db.add(response)
        db.commit()
        logger.exception("%s failed job=%s err=%s", LOG_PREFIX, job.id, exc)
        return {"ok": False, "job_id": job.id, "error": str(exc)}


def extract_wa_media(record: dict[str, Any] | None) -> dict[str, str]:
    """Best-effort media URL / ids from a Telnyx/Meta inbound record."""
    out = {"media_url": "", "inbound_message_id": "", "provider_media_id": "", "mime_type": "", "filename": ""}
    if not record:
        return out
    try:
        from app.services.survey_wa_voice_note_media_service import extract_media_items

        items = extract_media_items(record)
        if items:
            item = items[0]
            out["media_url"] = str(item.get("url") or "")
            out["provider_media_id"] = str(
                item.get("provider_media_id") or item.get("id") or item.get("media_id") or ""
            )
            out["mime_type"] = str(item.get("content_type") or item.get("mime_type") or "")
            out["filename"] = str(item.get("original_filename") or "")
    except Exception:
        logger.debug("%s extract_media_failed", LOG_PREFIX, exc_info=True)
    for key in ("id", "message_id", "whatsapp_message_id"):
        raw = record.get(key)
        if raw:
            out["inbound_message_id"] = str(raw)
            break
    wa = record.get("whatsapp_message") if isinstance(record.get("whatsapp_message"), dict) else {}
    if not out["inbound_message_id"] and wa.get("id"):
        out["inbound_message_id"] = str(wa.get("id"))
    if not out["media_url"]:
        media = record.get("media_url") or record.get("media")
        if isinstance(media, list) and media:
            first = media[0]
            out["media_url"] = str(first.get("url") if isinstance(first, dict) else first)
        elif isinstance(media, str):
            out["media_url"] = media
    return out


def store_web_upload(
    *,
    org_id: str,
    session_id: str,
    audio_bytes: bytes,
    filename: str,
    content_type: str,
) -> Path:
    from app.core.config import get_settings

    settings = get_settings()
    root = Path(str(getattr(settings, "voice_note_storage_dir", None) or "data/survey_voice_notes"))
    dest_dir = root / "feedback" / org_id / session_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    safe_name = (filename or "voice.webm").replace("\\", "_").replace("/", "_")
    path = dest_dir / f"{uuid.uuid4().hex}_{safe_name}"
    path.write_bytes(audio_bytes)
    return path
