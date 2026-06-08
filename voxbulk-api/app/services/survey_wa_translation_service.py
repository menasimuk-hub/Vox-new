"""Translate WA survey inbound text and voice transcripts to English for reporting."""

from __future__ import annotations

import json
import logging
import re
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
        clean = str(text or "").strip()
        if not clean:
            return False
        lang = str(detected_language or "").strip().lower()
        if lang.startswith("en"):
            return False
        if lang and not lang.startswith("en"):
            return True
        return bool(_NON_ENGLISH_RE.search(clean))

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
                "detected_language": detected_language or "en",
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
                }
                for a in answers
                if isinstance(a, dict)
            ]
            payload["extracted_answers"] = extracted
        return updated

    @staticmethod
    def process_recipient_translation(
        db: Session,
        recipient_id: str,
        *,
        voice_note_job_id: str | None = None,
        answer_index: int | None = None,
    ) -> dict[str, Any]:
        recipient = db.get(ServiceOrderRecipient, recipient_id)
        if recipient is None:
            return {"ok": False, "error": "recipient_not_found"}

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
        for idx, item in enumerate(answers):
            if not isinstance(item, dict):
                continue
            if voice_note_job_id and str(item.get("voice_note_job_id") or "") == str(voice_note_job_id):
                target = item
                target_index = idx
                break
            if answer_index is not None and idx == answer_index:
                target = item
                target_index = idx
                break
        if target is None and answer_index is None and answers:
            for idx in range(len(answers) - 1, -1, -1):
                item = answers[idx]
                if not isinstance(item, dict):
                    continue
                if resolve_answer_text(item):
                    target = item
                    target_index = idx
                    break

        if target is None or target_index is None:
            return {"ok": False, "error": "answer_not_found"}

        text = resolve_answer_text(target)
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
            answer_index=target_index,
            updater=_apply,
        ):
            return {"ok": False, "error": "update_failed"}

        recipient.result_json = json.dumps(payload, ensure_ascii=False)
        db.add(recipient)
        db.commit()
        return {
            "ok": True,
            "recipient_id": recipient_id,
            "translation_status": translation.get("translation_status"),
        }
