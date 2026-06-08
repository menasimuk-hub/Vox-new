"""Orchestrate WhatsApp survey voice-note acceptance, storage, and transcription."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.models.survey_voice_note_job import SurveyVoiceNoteJob
from app.services.survey_wa_open_text_service import (
    VOICE_NOTE_FALLBACK_MESSAGE,
    apply_transcript_to_answer,
    enrich_answer_with_voice_fields,
    is_open_text_question,
    is_voice_message_type,
)
from app.services.survey_wa_voice_note_media_service import (
    download_media_file,
    extract_media_items,
    storage_path_for_job,
)
from app.services.survey_wa_voice_note_settings import voice_note_settings, voice_notes_enabled
from app.services.survey_wa_whisper_service import WhisperTranscriptionError, transcribe_with_whisper_cpp

logger = logging.getLogger(__name__)
LOG_PREFIX = "[survey-wa-voice]"


class SurveyWaVoiceNoteService:
    @staticmethod
    def is_inbound_voice(reply) -> bool:
        if not voice_notes_enabled():
            return False
        if bool(getattr(reply, "is_voice_note", False)):
            return True
        fields = getattr(reply, "extracted_fields", None) or {}
        media_items = fields.get("media_items") if isinstance(fields, dict) else None
        if isinstance(media_items, list) and media_items:
            return True
        return is_voice_message_type(getattr(reply, "message_type", ""))

    @staticmethod
    def _first_media_item(reply, record: dict[str, Any] | None) -> dict[str, Any] | None:
        fields = getattr(reply, "extracted_fields", None) or {}
        items = fields.get("media_items") if isinstance(fields, dict) else None
        if isinstance(items, list) and items:
            first = items[0]
            return first if isinstance(first, dict) else None
        if isinstance(record, dict):
            parsed = extract_media_items(record)
            return parsed[0] if parsed else None
        return None

    @staticmethod
    def find_existing_job(
        db: Session,
        *,
        inbound_message_id: str,
        provider_media_id: str,
    ) -> SurveyVoiceNoteJob | None:
        return (
            db.execute(
                select(SurveyVoiceNoteJob).where(
                    SurveyVoiceNoteJob.inbound_message_id == str(inbound_message_id or ""),
                    SurveyVoiceNoteJob.provider_media_id == str(provider_media_id or ""),
                )
            )
            .scalars()
            .first()
        )

    @staticmethod
    def enqueue_transcription(job_id: str) -> None:
        from app.workers.survey_wa_voice_note_tasks import transcribe_survey_voice_note

        logger.info("%s transcription_job_created job_id=%s", LOG_PREFIX, job_id)
        transcribe_survey_voice_note.delay(job_id=job_id)

    @staticmethod
    def create_pending_job(
        db: Session,
        *,
        org_id: str,
        order: ServiceOrder,
        recipient: ServiceOrderRecipient,
        session_id: str | None,
        whatsapp_log_id: int | None,
        inbound_message_id: str,
        media_item: dict[str, Any],
        answer_context: str,
        step_index: int,
        answer_index: int | None,
        question_id: str | None = None,
    ) -> SurveyVoiceNoteJob:
        provider_media_id = str(media_item.get("provider_media_id") or "")
        existing = SurveyWaVoiceNoteService.find_existing_job(
            db,
            inbound_message_id=inbound_message_id,
            provider_media_id=provider_media_id,
        )
        if existing is not None:
            logger.info(
                "%s duplicate_webhook_skipped job_id=%s inbound_message_id=%s media_id=%s",
                LOG_PREFIX,
                existing.id,
                inbound_message_id,
                provider_media_id,
            )
            return existing

        now = datetime.utcnow()
        job = SurveyVoiceNoteJob(
            org_id=str(org_id),
            order_id=str(order.id),
            recipient_id=str(recipient.id),
            session_id=session_id,
            whatsapp_log_id=whatsapp_log_id,
            answer_context=str(answer_context or "normal"),
            step_index=int(step_index or 0),
            answer_index=answer_index,
            question_id=str(question_id or "").strip() or None,
            inbound_message_id=str(inbound_message_id or ""),
            provider_media_id=provider_media_id,
            media_url=str(media_item.get("url") or ""),
            audio_mime_type=str(media_item.get("content_type") or ""),
            audio_original_filename=str(media_item.get("original_filename") or "") or None,
            transcription_status="pending",
            answer_source="voice_note",
            created_at=now,
            updated_at=now,
        )
        db.add(job)
        db.flush()
        return job

    @staticmethod
    def _resolve_recipient_language(recipient: ServiceOrderRecipient | None) -> str | None:
        if recipient is None:
            return None
        for key in ("language", "locale"):
            raw = str(getattr(recipient, key, "") or "").strip().lower()
            if raw:
                return raw.split("-")[0]
        try:
            payload = json.loads(recipient.result_json or "{}")
            if isinstance(payload, dict):
                for key in ("language", "locale"):
                    raw = str(payload.get(key) or "").strip().lower()
                    if raw:
                        return raw.split("-")[0]
        except Exception:
            pass
        return None

    @staticmethod
    def _transcribe_audio(
        db: Session,
        audio_path,
        *,
        recipient: ServiceOrderRecipient | None = None,
    ) -> dict[str, Any]:
        language = SurveyWaVoiceNoteService._resolve_recipient_language(recipient)
        try:
            from app.services.providers.deepinfra_service import DeepInfraProviderService

            if DeepInfraProviderService.is_configured(db):
                return DeepInfraProviderService.transcribe_audio_file(
                    db,
                    audio_path=audio_path,
                    language=language,
                )
        except Exception as exc:
            logger.warning("%s deepinfra_transcription_fallback reason=%s", LOG_PREFIX, str(exc)[:300])
        return transcribe_with_whisper_cpp(audio_path)

    @staticmethod
    def process_transcription_job(db: Session, job_id: str) -> dict[str, Any]:
        job = db.get(SurveyVoiceNoteJob, job_id)
        if job is None:
            return {"ok": False, "error": "job_not_found"}

        if job.transcription_status == "completed" and job.answer_text:
            logger.info("%s transcription_already_completed job_id=%s", LOG_PREFIX, job_id)
            return {"ok": True, "duplicate": True}

        cfg = voice_note_settings()
        job.transcription_status = "retrying" if job.retry_count else "pending"
        job.updated_at = datetime.utcnow()
        db.add(job)
        db.commit()

        try:
            if not job.media_url:
                raise ValueError("Missing media URL on voice note job")
            ext = ".ogg"
            if job.audio_original_filename and "." in job.audio_original_filename:
                ext = f".{job.audio_original_filename.rsplit('.', 1)[-1]}"
            dest = storage_path_for_job(
                org_id=job.org_id,
                order_id=job.order_id,
                job_id=job.id,
                extension=ext,
            )
            path, size, mime = download_media_file(
                db,
                media_url=job.media_url,
                content_type=job.audio_mime_type or "",
                original_filename=job.audio_original_filename or "",
                dest_path=dest,
                max_bytes=int(cfg["voice_note_max_file_size_bytes"]),
                timeout_seconds=int(cfg["voice_note_download_timeout_seconds"]),
            )
            job.audio_file_path = str(path)
            job.audio_file_size = size
            job.audio_mime_type = mime
            job.transcription_status = "transcribing"
            job.updated_at = datetime.utcnow()
            db.add(job)
            db.commit()

            logger.info("%s transcription_started job_id=%s path=%s", LOG_PREFIX, job.id, path)
            recipient = db.get(ServiceOrderRecipient, job.recipient_id)
            result = SurveyWaVoiceNoteService._transcribe_audio(db, path, recipient=recipient)
            text = str(result.get("text") or "").strip()
            if not text:
                raise WhisperTranscriptionError("Empty transcript")

            job.answer_text = text
            job.detected_language = result.get("detected_language")
            job.transcription_model = result.get("transcription_model")
            job.transcription_duration_ms = result.get("transcription_duration_ms")
            job.transcription_status = "completed"
            job.transcribed_at = datetime.utcnow()
            job.processed_at = datetime.utcnow()
            job.updated_at = datetime.utcnow()
            job.transcription_error = None
            db.add(job)
            db.commit()

            SurveyWaVoiceNoteService.apply_transcript_to_recipient(db, job)
            logger.info(
                "%s transcription_completed job_id=%s language=%s chars=%s",
                LOG_PREFIX,
                job.id,
                job.detected_language,
                len(text),
            )
            return {"ok": True, "job_id": job.id, "text_length": len(text)}
        except Exception as exc:
            job.retry_count = int(job.retry_count or 0) + 1
            job.transcription_status = "failed"
            job.transcription_error = str(exc)[:2000]
            job.updated_at = datetime.utcnow()
            db.add(job)
            db.commit()
            logger.exception("%s transcription_failed job_id=%s err=%s", LOG_PREFIX, job.id, exc)
            SurveyWaVoiceNoteService._mark_answer_transcription_failed(db, job, str(exc))
            return {"ok": False, "job_id": job.id, "error": str(exc)}

    @staticmethod
    def _mark_answer_transcription_failed(db: Session, job: SurveyVoiceNoteJob, error: str) -> None:
        recipient = db.get(ServiceOrderRecipient, job.recipient_id)
        if recipient is None:
            return
        try:
            payload = json.loads(recipient.result_json or "{}")
        except Exception:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        SurveyWaVoiceNoteService._update_answer_in_payload(
            payload,
            job=job,
            updater=lambda ans: {
                **ans,
                "transcription_status": "failed",
                "transcription_error": error[:500],
            },
        )
        recipient.result_json = json.dumps(payload, ensure_ascii=False)
        db.add(recipient)
        db.commit()

    @staticmethod
    def _update_answer_in_payload(
        payload: dict[str, Any],
        *,
        job: SurveyVoiceNoteJob,
        updater,
    ) -> None:
        conv = payload.setdefault("wa_conversation", {})
        answers = list(conv.get("answers") or [])
        idx = job.answer_index
        if idx is not None and 0 <= int(idx) < len(answers):
            answers[int(idx)] = updater(dict(answers[int(idx)]))
        else:
            for i, ans in enumerate(answers):
                if isinstance(ans, dict) and str(ans.get("voice_note_job_id") or "") == job.id:
                    answers[i] = updater(dict(ans))
                    break
        conv["answers"] = answers
        payload["wa_conversation"] = conv

        extracted = list(payload.get("extracted_answers") or [])
        for i, row in enumerate(extracted):
            if not isinstance(row, dict):
                continue
            if str(row.get("voice_note_job_id") or "") == job.id:
                updated = updater(row)
                extracted[i] = {
                    **row,
                    "answer": updated.get("answer") or updated.get("answer_text") or row.get("answer"),
                    "answer_text": updated.get("answer_text") or updated.get("answer"),
                    "transcription_status": updated.get("transcription_status"),
                    "detected_language": updated.get("detected_language"),
                    "answer_source": updated.get("answer_source") or "voice_note",
                }
                break
        payload["extracted_answers"] = extracted

        if job.answer_context == "final_feedback":
            text = str(job.answer_text or "").strip()
            if text:
                payload["final_additional_feedback"] = text
                conv["final_additional_feedback"] = text

    @staticmethod
    def apply_transcript_to_recipient(db: Session, job: SurveyVoiceNoteJob) -> None:
        recipient = db.get(ServiceOrderRecipient, job.recipient_id)
        if recipient is None:
            return
        try:
            payload = json.loads(recipient.result_json or "{}")
        except Exception:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}

        text = str(job.answer_text or "").strip()

        def _apply(ans: dict[str, Any]) -> dict[str, Any]:
            return apply_transcript_to_answer(
                ans,
                text=text,
                detected_language=job.detected_language,
                status="completed",
            )

        SurveyWaVoiceNoteService._update_answer_in_payload(payload, job=job, updater=_apply)

        if job.answer_context == "followup" and text:
            from app.services.survey_wa_vague_negative_followup_service import merge_elaboration_into_answers

            answers = list((payload.get("wa_conversation") or {}).get("answers") or [])
            merge_elaboration_into_answers(answers, text)
            payload.setdefault("wa_conversation", {})["answers"] = answers
            payload["extracted_answers"] = [
                {"question": a["question"], "answer": a.get("answer_display") or a["answer"]}
                for a in answers
                if isinstance(a, dict)
            ]

        recipient.result_json = json.dumps(payload, ensure_ascii=False)
        db.add(recipient)
        db.commit()
        logger.info(
            "%s transcript_attached job_id=%s recipient_id=%s report_answer_chars=%s",
            LOG_PREFIX,
            job.id,
            recipient.id,
            len(text),
        )

        if text:
            from app.services.survey_wa_translation_service import SurveyWaTranslationService

            SurveyWaTranslationService.enqueue_answer_translation(
                recipient.id,
                voice_note_job_id=job.id,
            )

        if job.answer_context == "final_feedback":
            from app.services.survey_wa_final_feedback_service import try_complete_survey_after_final_feedback_voice

            try_complete_survey_after_final_feedback_voice(db, job)

        session_id = job.session_id
        if session_id and text:
            from app.models.survey_session import SurveySessionAnswer
            from app.services.survey_session_service import SurveySessionService

            rows = SurveySessionService.list_answers(db, session_id)
            target: SurveySessionAnswer | None = None
            for row in rows:
                if row.step_index == job.step_index:
                    target = row
            if target is not None:
                target.raw_value = text
                target.normalized_value = text
                db.add(target)
                db.commit()

    @staticmethod
    def prepare_voice_answer(
        db: Session,
        *,
        order: ServiceOrder,
        recipient: ServiceOrderRecipient,
        payload: dict[str, Any],
        conv: dict[str, Any],
        question: dict[str, Any] | None,
        reply,
        inbound_message_id: str | None,
        log_id: int | None,
        session_id: str | None,
        answer_context: str,
        step_index: int,
        record: dict[str, Any] | None = None,
        config: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        if not SurveyWaVoiceNoteService.is_inbound_voice(reply):
            return None

        logger.info(
            "%s inbound_voice_note_received order=%s recipient=%s step=%s context=%s message_id=%s",
            LOG_PREFIX,
            order.id,
            recipient.id,
            step_index,
            answer_context,
            inbound_message_id,
        )

        if answer_context == "final_feedback":
            open_ok = True
        elif answer_context == "followup":
            open_ok = True
        else:
            open_ok = is_open_text_question(question)

        if not open_ok:
            logger.info(
                "%s rejected_non_open_text order=%s recipient=%s step=%s type=%s",
                LOG_PREFIX,
                order.id,
                recipient.id,
                step_index,
                (question or {}).get("reply_type"),
            )
            return {"rejected": True, "fallback_message": VOICE_NOTE_FALLBACK_MESSAGE}

        media_item = SurveyWaVoiceNoteService._first_media_item(reply, record)
        if not media_item or not media_item.get("url"):
            return {"rejected": True, "fallback_message": VOICE_NOTE_FALLBACK_MESSAGE, "reason": "no_media"}

        provider_media_id = str(media_item.get("provider_media_id") or "")
        existing = SurveyWaVoiceNoteService.find_existing_job(
            db,
            inbound_message_id=inbound_message_id,
            provider_media_id=provider_media_id,
        )
        if existing is not None:
            logger.info(
                "%s duplicate_webhook_skipped job_id=%s inbound_message_id=%s media_id=%s",
                LOG_PREFIX,
                existing.id,
                inbound_message_id,
                provider_media_id,
            )
            for ans in list(conv.get("answers") or []):
                if isinstance(ans, dict) and str(ans.get("voice_note_job_id") or "") == existing.id:
                    return {
                        "accepted": True,
                        "duplicate": True,
                        "job_id": existing.id,
                        "transcript_ready": existing.transcription_status == "completed",
                    }
            if existing.transcription_status == "completed" and existing.answer_text:
                answer_entry = apply_transcript_to_answer(
                    enrich_answer_with_voice_fields(
                        {
                            "step_role": str((question or {}).get("step_role") or answer_context),
                            "question": str((question or {}).get("text") or ""),
                            "answer": existing.answer_text,
                            "reply_type": (question or {}).get("reply_type") if question else "long_text",
                        },
                        job_id=existing.id,
                        status="completed",
                    ),
                    text=existing.answer_text,
                    detected_language=existing.detected_language,
                    status="completed",
                )
                return {
                    "accepted": True,
                    "duplicate": True,
                    "job_id": existing.id,
                    "answer": answer_entry,
                    "transcript_ready": True,
                }
            q_text = str((question or {}).get("text") or "")
            if answer_context == "final_feedback":
                from app.services.survey_wa_final_feedback_service import final_feedback_settings

                q_text = str(final_feedback_settings(config or {}).get("open_text_prompt") or q_text)
            pending_entry = enrich_answer_with_voice_fields(
                {
                    "step_role": str((question or {}).get("step_role") or answer_context),
                    "question": q_text,
                    "answer": existing.answer_text or "",
                    "answer_text": existing.answer_text or "",
                    "reply_type": (question or {}).get("reply_type") if question else "long_text",
                    "audio_file_path": existing.audio_file_path,
                    "audio_mime_type": existing.audio_mime_type,
                    "inbound_message_id": existing.inbound_message_id,
                    "provider_media_id": existing.provider_media_id,
                },
                job_id=existing.id,
                status=str(existing.transcription_status or "pending"),
            )
            return {
                "accepted": True,
                "duplicate": True,
                "job_id": existing.id,
                "answer": pending_entry,
                "transcript_ready": existing.transcription_status == "completed",
            }

        answer_index = len(list(conv.get("answers") or []))
        if answer_context == "followup" and answer_index > 0:
            answer_index = answer_index - 1

        question_id = None
        if isinstance(question, dict):
            question_id = str(
                question.get("id")
                or question.get("question_id")
                or question.get("step_role")
                or question.get("template_id")
                or ""
            ).strip() or None

        job = SurveyWaVoiceNoteService.create_pending_job(
            db,
            org_id=str(order.org_id),
            order=order,
            recipient=recipient,
            session_id=session_id,
            whatsapp_log_id=log_id,
            inbound_message_id=str(inbound_message_id or ""),
            media_item=media_item,
            answer_context=answer_context,
            step_index=step_index,
            answer_index=answer_index,
            question_id=question_id,
        )

        if job.transcription_status == "completed" and job.answer_text:
            answer_entry = apply_transcript_to_answer(
                enrich_answer_with_voice_fields(
                    {
                        "step_role": str((question or {}).get("step_role") or ""),
                        "question": str((question or {}).get("text") or ""),
                        "answer": job.answer_text,
                        "reply_type": (question or {}).get("reply_type") if question else "long_text",
                    },
                    job_id=job.id,
                    status="completed",
                ),
                text=job.answer_text,
                detected_language=job.detected_language,
                status="completed",
            )
            return {"accepted": True, "answer": answer_entry, "job_id": job.id, "transcript_ready": True}

        q_text = str((question or {}).get("text") or "")
        if answer_context == "final_feedback":
            from app.services.survey_wa_final_feedback_service import final_feedback_settings

            q_text = str(final_feedback_settings(config or {}).get("open_text_prompt") or q_text)

        answer_entry = enrich_answer_with_voice_fields(
            {
                "step_role": str((question or {}).get("step_role") or answer_context),
                "question": q_text,
                "answer": "",
                "answer_text": "",
                "reply_type": (question or {}).get("reply_type") if question else "long_text",
                "audio_file_path": job.audio_file_path,
                "audio_mime_type": job.audio_mime_type,
                "inbound_message_id": job.inbound_message_id,
                "provider_media_id": job.provider_media_id,
            },
            job_id=job.id,
            status="pending",
        )

        if job.transcription_status in {"pending", "failed", "retrying"}:
            db.commit()
            SurveyWaVoiceNoteService.enqueue_transcription(job.id)

        return {
            "accepted": True,
            "answer": answer_entry,
            "job_id": job.id,
            "transcript_ready": False,
            "normalized_value": "",
        }

    @staticmethod
    def job_to_dict(job: SurveyVoiceNoteJob) -> dict[str, Any]:
        audio_path = str(job.audio_file_path or "").strip()
        audio_deleted = job.audio_deleted_at is not None
        return {
            "id": job.id,
            "order_id": job.order_id,
            "recipient_id": job.recipient_id,
            "answer_context": job.answer_context,
            "step_index": job.step_index,
            "answer_index": job.answer_index,
            "question_id": job.question_id,
            "survey_id": job.order_id,
            "contact_id": job.recipient_id,
            "answer_text": job.answer_text,
            "answer_source": job.answer_source,
            "detected_language": job.detected_language,
            "transcription_status": job.transcription_status,
            "transcription_error": job.transcription_error,
            "transcription_model": job.transcription_model,
            "transcription_duration_ms": job.transcription_duration_ms,
            "inbound_message_id": job.inbound_message_id,
            "provider_media_id": job.provider_media_id,
            "audio_file_path": None if audio_deleted else audio_path or None,
            "audio_mime_type": job.audio_mime_type,
            "audio_file_size": job.audio_file_size,
            "audio_deleted_at": job.audio_deleted_at.isoformat() if job.audio_deleted_at else None,
            "transcribed_at": job.transcribed_at.isoformat() if job.transcribed_at else None,
            "processed_at": job.processed_at.isoformat() if job.processed_at else None,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "updated_at": job.updated_at.isoformat() if job.updated_at else None,
            "retry_count": int(job.retry_count or 0),
            "admin_audio_path": f"/admin/wa-survey/voice-notes/{job.id}/audio",
        }

    @staticmethod
    def retry_job(db: Session, job_id: str) -> dict[str, Any]:
        job = db.get(SurveyVoiceNoteJob, job_id)
        if job is None:
            raise ValueError("Voice note job not found")
        logger.info("%s retry_requested job_id=%s", LOG_PREFIX, job_id)
        job.transcription_status = "pending"
        job.transcription_error = None
        job.updated_at = datetime.utcnow()
        db.add(job)
        db.commit()
        SurveyWaVoiceNoteService.enqueue_transcription(job.id)
        return {"ok": True, "job_id": job.id}

    @staticmethod
    def retry_queued_jobs(
        db: Session,
        *,
        statuses: tuple[str, ...] = ("pending", "failed", "retrying"),
        order_id: str | None = None,
        limit: int = 200,
    ) -> dict[str, Any]:
        """Re-enqueue all voice-note jobs matching status (e.g. after Celery was down)."""
        clean_statuses = tuple(
            dict.fromkeys(str(s or "").strip().lower() for s in statuses if str(s or "").strip())
        )
        if not clean_statuses:
            clean_statuses = ("pending", "failed", "retrying")

        q = select(SurveyVoiceNoteJob).where(SurveyVoiceNoteJob.transcription_status.in_(clean_statuses))
        if order_id:
            q = q.where(SurveyVoiceNoteJob.order_id == str(order_id).strip())
        q = q.order_by(SurveyVoiceNoteJob.created_at.asc()).limit(max(1, min(int(limit or 200), 500)))

        jobs = list(db.execute(q).scalars().all())
        retried: list[str] = []
        for job in jobs:
            job.transcription_status = "pending"
            job.transcription_error = None
            job.updated_at = datetime.utcnow()
            db.add(job)
            db.flush()
            SurveyWaVoiceNoteService.enqueue_transcription(job.id)
            retried.append(job.id)
        if retried:
            db.commit()
        logger.info(
            "%s bulk_retry_queued count=%s statuses=%s order_id=%s",
            LOG_PREFIX,
            len(retried),
            clean_statuses,
            order_id,
        )
        return {
            "ok": True,
            "retried_count": len(retried),
            "job_ids": retried,
            "statuses": list(clean_statuses),
            "order_id": order_id,
        }

    @staticmethod
    def list_jobs_for_recipient(db: Session, recipient_id: str) -> list[SurveyVoiceNoteJob]:
        return list(
            db.execute(
                select(SurveyVoiceNoteJob)
                .where(SurveyVoiceNoteJob.recipient_id == recipient_id)
                .order_by(SurveyVoiceNoteJob.created_at.asc())
            )
            .scalars()
            .all()
        )

    @staticmethod
    def purge_expired_audio(db: Session) -> int:
        cfg = voice_note_settings()
        days = max(int(cfg.get("voice_note_retention_days") or 90), 1)
        cutoff = datetime.utcnow()
        from datetime import timedelta

        threshold = cutoff - timedelta(days=days)
        rows = list(
            db.execute(
                select(SurveyVoiceNoteJob).where(
                    SurveyVoiceNoteJob.audio_deleted_at.is_(None),
                    SurveyVoiceNoteJob.created_at < threshold,
                    SurveyVoiceNoteJob.audio_file_path.is_not(None),
                )
            )
            .scalars()
            .all()
        )
        removed = 0
        for row in rows:
            path = str(row.audio_file_path or "")
            if path:
                try:
                    from pathlib import Path

                    p = Path(path)
                    if p.exists():
                        p.unlink()
                    removed += 1
                except OSError:
                    pass
            row.audio_deleted_at = datetime.utcnow()
            row.updated_at = datetime.utcnow()
            db.add(row)
        if rows:
            db.commit()
        logger.info("%s retention_purge count=%s removed_files=%s", LOG_PREFIX, len(rows), removed)
        return len(rows)
