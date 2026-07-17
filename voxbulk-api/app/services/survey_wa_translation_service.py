"""Translate WA survey inbound text and voice transcripts to English for reporting."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.service_order import ServiceOrderRecipient
from app.services.agents.base import AgentMessage
from app.services.providers.openai_service import OpenAIProviderService
from app.services.survey_wa_open_text_service import apply_transcript_to_answer, resolve_answer_text

logger = logging.getLogger(__name__)

_TRANSLATE_SYSTEM = (
    "You translate survey respondent messages into clear English. "
    "Return ONLY the English translation with no commentary or quotes."
)

_NON_ENGLISH_RE = re.compile(r"[^\x00-\x7F]")


class SurveyWaTranslationService:
    @staticmethod
    def needs_translation(text: str, detected_language: str | None = None) -> bool:
        """True when answer should be translated to English.

        Non-ASCII / non-English script wins over a false STT ``en`` label.
        """
        clean = str(text or "").strip()
        if not clean:
            return False
        if _NON_ENGLISH_RE.search(clean):
            return True
        lang = str(detected_language or "").strip().lower()
        if lang and not lang.startswith("en"):
            return True
        return False

    @staticmethod
    def resolve_source_text(answer: dict[str, Any]) -> str:
        """Original respondent text for translation (never prefer translated_text)."""
        if not isinstance(answer, dict):
            return ""
        return str(
            answer.get("original_text")
            or answer.get("answer_text")
            or answer.get("answer")
            or answer.get("final_additional_feedback")
            or ""
        ).strip()

    @staticmethod
    def merge_preserved_translations(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
        """Keep completed translation fields when a later full JSON save would drop them."""
        if not isinstance(incoming, dict):
            return incoming
        out = dict(incoming)
        ex_conv = existing.get("wa_conversation") if isinstance(existing.get("wa_conversation"), dict) else {}
        in_conv = out.get("wa_conversation") if isinstance(out.get("wa_conversation"), dict) else {}
        ex_answers = list(ex_conv.get("answers") or [])
        in_answers = list(in_conv.get("answers") or [])
        if not ex_answers or not in_answers:
            return out

        by_job: dict[str, dict[str, Any]] = {}
        for ans in ex_answers:
            if not isinstance(ans, dict):
                continue
            job_id = str(ans.get("voice_note_job_id") or "").strip()
            if job_id:
                by_job[job_id] = ans

        merged: list[Any] = []
        for idx, ans in enumerate(in_answers):
            if not isinstance(ans, dict):
                merged.append(ans)
                continue
            prev = None
            job_id = str(ans.get("voice_note_job_id") or "").strip()
            if job_id and job_id in by_job:
                prev = by_job[job_id]
            elif idx < len(ex_answers) and isinstance(ex_answers[idx], dict):
                prev = ex_answers[idx]
            row = dict(ans)
            if isinstance(prev, dict):
                for key in ("original_text", "translated_text", "translation_status", "detected_language"):
                    if row.get(key) in (None, "") and prev.get(key) not in (None, ""):
                        row[key] = prev[key]
                # Prefer completed English display when incoming lost it.
                if (
                    str(prev.get("translation_status") or "") == "completed"
                    and str(prev.get("translated_text") or "").strip()
                    and str(row.get("translation_status") or "") not in {"completed", "pending"}
                    and not str(row.get("translated_text") or "").strip()
                ):
                    en = str(prev.get("translated_text") or "").strip()
                    row["translated_text"] = en
                    row["translation_status"] = "completed"
                    row["answer_display"] = en
                    row["answer"] = en
                    row["answer_text"] = en
                    if prev.get("original_text"):
                        row["original_text"] = prev["original_text"]
            merged.append(row)
        in_conv = dict(in_conv)
        in_conv["answers"] = merged
        out["wa_conversation"] = in_conv
        return out

    @staticmethod
    def translate_to_english(
        db: Session,
        text: str,
        *,
        detected_language: str | None = None,
    ) -> dict[str, Any]:
        original = str(text or "").strip()
        if not original:
            return {
                "original_text": "",
                "translated_text": "",
                "detected_language": detected_language,
                "translation_status": "skipped",
            }
        if not SurveyWaTranslationService.needs_translation(original, detected_language):
            return {
                "original_text": original,
                "translated_text": original,
                "detected_language": detected_language,
                "translation_status": "not_needed",
            }
        try:
            result = OpenAIProviderService.complete(
                db,
                system_prompt=_TRANSLATE_SYSTEM,
                messages=[
                    AgentMessage(
                        role="user",
                        content=f"Source language hint: {detected_language or 'unknown'}\n\nMessage:\n{original}",
                    )
                ],
                max_tokens=900,
                temperature=0.1,
                provider="deepseek",
            )
            translated = str(result.assistant_text or "").strip()
            return {
                "original_text": original,
                "translated_text": translated or original,
                "detected_language": detected_language,
                "translation_status": "completed" if translated else "failed",
            }
        except Exception as exc:
            logger.warning("survey_wa_translation_failed: %s", str(exc)[:300])
            return {
                "original_text": original,
                "translated_text": None,
                "detected_language": detected_language,
                "translation_status": "failed",
            }

    @staticmethod
    def apply_to_answer(answer: dict[str, Any], translation: dict[str, Any]) -> dict[str, Any]:
        out = dict(answer)
        original = str(translation.get("original_text") or "").strip()
        translated = str(translation.get("translated_text") or "").strip()
        if original:
            out["original_text"] = original
        if translated:
            out["translated_text"] = translated
            out["answer_display"] = translated
            out["answer"] = translated
            out["answer_text"] = translated
        if translation.get("detected_language"):
            out["detected_language"] = translation["detected_language"]
        out["translation_status"] = translation.get("translation_status") or "pending"
        return out

    @staticmethod
    def enqueue_answer_translation(
        recipient_id: str,
        *,
        voice_note_job_id: str | None = None,
        answer_index: int | None = None,
    ) -> None:
        try:
            from app.workers.survey_wa_translation_tasks import translate_wa_answer_task

            translate_wa_answer_task.delay(
                recipient_id=recipient_id,
                voice_note_job_id=voice_note_job_id,
                answer_index=answer_index,
            )
        except Exception as exc:
            logger.warning(
                "survey_wa_translation_enqueue_failed recipient=%s err=%s",
                recipient_id,
                str(exc)[:200],
            )

    @staticmethod
    def _update_answer_in_payload(
        payload: dict[str, Any],
        *,
        voice_note_job_id: str | None,
        answer_index: int | None,
        updater,
    ) -> bool:
        conv = payload.get("wa_conversation") if isinstance(payload.get("wa_conversation"), dict) else {}
        answers = list(conv.get("answers") or [])
        updated = False
        for idx, item in enumerate(answers):
            if not isinstance(item, dict):
                continue
            if voice_note_job_id and str(item.get("voice_note_job_id") or "") != str(voice_note_job_id):
                continue
            if answer_index is not None and idx != answer_index:
                continue
            answers[idx] = updater(item)
            updated = True
            if voice_note_job_id or answer_index is not None:
                break
        if updated:
            conv["answers"] = answers
            payload["wa_conversation"] = conv
            extracted = [
                {
                    "question": a.get("question"),
                    "answer": a.get("answer_display") or a.get("translated_text") or a.get("answer"),
                    **({"original_text": a["original_text"]} if a.get("original_text") else {}),
                    **({"translated_text": a["translated_text"]} if a.get("translated_text") else {}),
                    **({"translation_status": a["translation_status"]} if a.get("translation_status") else {}),
                    **({"voice_note_job_id": a["voice_note_job_id"]} if a.get("voice_note_job_id") else {}),
                }
                for a in answers
                if isinstance(a, dict)
            ]
            payload["extracted_answers"] = extracted
        return updated

    @staticmethod
    def reconcile_missing_translations(recipient: ServiceOrderRecipient, payload: dict[str, Any]) -> None:
        """Enqueue translation for typed + voice answers still missing English."""
        conv = payload.get("wa_conversation") if isinstance(payload.get("wa_conversation"), dict) else {}
        answers = conv.get("answers") if isinstance(conv.get("answers"), list) else []
        for idx, answer in enumerate(answers):
            if not isinstance(answer, dict):
                continue
            status = str(answer.get("translation_status") or "")
            if status in {"completed", "not_needed"}:
                continue
            if str(answer.get("translated_text") or "").strip():
                continue
            if str(answer.get("transcription_status") or "") in {"pending", "retrying", "transcribing"}:
                continue
            text = SurveyWaTranslationService.resolve_source_text(answer)
            if not text:
                continue
            if not SurveyWaTranslationService.needs_translation(text, answer.get("detected_language")):
                continue
            job_id = str(answer.get("voice_note_job_id") or "").strip() or None
            SurveyWaTranslationService.enqueue_answer_translation(
                recipient.id,
                voice_note_job_id=job_id,
                answer_index=None if job_id else idx,
            )

    @staticmethod
    def process_recipient_translation(
        db: Session,
        recipient_id: str,
        *,
        voice_note_job_id: str | None = None,
        answer_index: int | None = None,
    ) -> dict[str, Any]:
        from app.models.survey_voice_note_job import SurveyVoiceNoteJob
        from app.services.survey_recipient_result_lock import recipient_result_lock

        with recipient_result_lock(recipient_id):
            recipient = db.get(ServiceOrderRecipient, recipient_id)
            if recipient is None:
                return {"ok": False, "error": "recipient_not_found"}
            db.refresh(recipient)

            try:
                payload = json.loads(recipient.result_json or "{}")
            except Exception:
                payload = {}
            if not isinstance(payload, dict):
                payload = {}

            conv = payload.get("wa_conversation") if isinstance(payload.get("wa_conversation"), dict) else {}
            answers = list(conv.get("answers") or [])
            target: dict[str, Any] | None = None
            target_index: int | None = None
            # Prefer voice_note_job_id over stale answer_index.
            if voice_note_job_id:
                for idx, item in enumerate(answers):
                    if isinstance(item, dict) and str(item.get("voice_note_job_id") or "") == str(
                        voice_note_job_id
                    ):
                        target = item
                        target_index = idx
                        break
            if target is None and answer_index is not None:
                if 0 <= int(answer_index) < len(answers) and isinstance(answers[int(answer_index)], dict):
                    target = answers[int(answer_index)]
                    target_index = int(answer_index)
            if target is None and answer_index is None and answers:
                for idx in range(len(answers) - 1, -1, -1):
                    item = answers[idx]
                    if not isinstance(item, dict):
                        continue
                    if SurveyWaTranslationService.resolve_source_text(item) or resolve_answer_text(item):
                        target = item
                        target_index = idx
                        break

            if target is None or target_index is None:
                return {"ok": False, "error": "answer_not_found"}

            text = SurveyWaTranslationService.resolve_source_text(target)
            if not text:
                return {"ok": False, "error": "empty_answer"}

            translation = SurveyWaTranslationService.translate_to_english(
                db,
                text,
                detected_language=str(target.get("detected_language") or "") or None,
            )

            def _apply(ans: dict[str, Any]) -> dict[str, Any]:
                if str(ans.get("answer_source") or "") == "voice_note":
                    base = apply_transcript_to_answer(
                        ans,
                        text=str(translation.get("original_text") or text),
                        detected_language=translation.get("detected_language"),
                        status=str(ans.get("transcription_status") or "completed"),
                    )
                    return SurveyWaTranslationService.apply_to_answer(base, translation)
                return SurveyWaTranslationService.apply_to_answer(ans, translation)

            if not SurveyWaTranslationService._update_answer_in_payload(
                payload,
                voice_note_job_id=voice_note_job_id,
                answer_index=None if voice_note_job_id else target_index,
                updater=_apply,
            ):
                return {"ok": False, "error": "update_failed"}

            if voice_note_job_id:
                job = db.get(SurveyVoiceNoteJob, voice_note_job_id)
                if job is not None:
                    job.original_text = str(translation.get("original_text") or text) or None
                    job.translated_text = str(translation.get("translated_text") or "") or None
                    job.translation_status = str(translation.get("translation_status") or "") or None
                    job.updated_at = datetime.utcnow()
                    db.add(job)

            recipient.result_json = json.dumps(payload, ensure_ascii=False)
            db.add(recipient)
            db.commit()
            return {
                "ok": True,
                "recipient_id": recipient_id,
                "translation_status": translation.get("translation_status"),
            }
