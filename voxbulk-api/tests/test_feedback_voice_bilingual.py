"""Customer Feedback bilingual + async voice note jobs."""

from __future__ import annotations

import uuid
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.models.customer_feedback import FeedbackResponse, FeedbackSession, FeedbackVoiceNoteJob
from app.services.customer_feedback.feedback_results_aggregate import build_open_comments
from app.services.customer_feedback.feedback_voice_note_service import process_voice_job


def test_build_open_comments_exposes_bilingual_and_pending_voice():
    pending = SimpleNamespace(
        id="r1",
        session_id="s1",
        answer_text=None,
        answer_text_en=None,
        original_text=None,
        translation_status="pending",
        transcription_status="pending",
        detected_language=None,
        answer_source="voice",
        survey_type_id="st1",
        question_key="topic__tell_us_more",
        created_at=datetime.utcnow(),
    )
    done = SimpleNamespace(
        id="r2",
        session_id="s1",
        answer_text="The flowers were nice",
        answer_text_en="The flowers were nice",
        original_text="الورود كانت جميلة",
        translation_status="completed",
        transcription_status="completed",
        detected_language="ar",
        answer_source="voice",
        survey_type_id="st1",
        question_key="topic__tell_us_more",
        created_at=datetime.utcnow(),
    )
    tpl = SimpleNamespace(
        survey_type_id="st1",
        template_key="topic__tell_us_more",
        body="Tell us more",
        step_role="tell_us_more",
        buttons_json=None,
    )
    templates = {("st1", "topic__tell_us_more"): tpl}
    rows = build_open_comments([pending, done], templates)
    assert len(rows) == 2
    by_id = {r["id"]: r for r in rows}
    assert by_id["r1"]["text"] == "Transcribing…"
    assert by_id["r1"]["transcription_status"] == "pending"
    assert by_id["r2"]["original_text"] == "الورود كانت جميلة"
    assert by_id["r2"]["translated_text"] == "The flowers were nice"
    assert by_id["r2"]["translation_status"] == "completed"


def test_process_voice_job_fills_original_and_english():
    job_id = str(uuid.uuid4())
    response_id = str(uuid.uuid4())
    session_id = str(uuid.uuid4())
    job = FeedbackVoiceNoteJob(
        id=job_id,
        org_id="org1",
        session_id=session_id,
        response_id=response_id,
        inbound_message_id=f"web:{response_id}",
        provider_media_id="path:/tmp/x.webm",
        audio_file_path="/tmp/x.webm",
        audio_original_filename="x.webm",
        audio_mime_type="audio/webm",
        transcription_status="pending",
        translation_status="pending",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    response = FeedbackResponse(
        id=response_id,
        session_id=session_id,
        org_id="org1",
        location_id="loc1",
        survey_type_id="st1",
        question_key="topic__tell_us_more",
        translation_status="pending",
        transcription_status="pending",
        answer_source="voice",
        step_order=1,
        created_at=datetime.utcnow(),
    )
    session = FeedbackSession(
        id=session_id,
        org_id="org1",
        location_id="loc1",
        visitor_phone="+447000000000",
        status="active",
        current_step=1,
        started_at=datetime.utcnow(),
    )

    db = MagicMock()

    def _get(model, pk):
        if model is FeedbackVoiceNoteJob and pk == job_id:
            return job
        if model is FeedbackResponse and pk == response_id:
            return response
        if model is FeedbackSession and pk == session_id:
            return session
        return None

    db.get.side_effect = _get

    with (
        patch("app.services.customer_feedback.feedback_voice_note_service.Path") as path_cls,
        patch(
            "app.services.customer_feedback.feedback_voice_note_service.VoiceTranscriptionService.transcribe_uploaded_audio"
        ) as stt,
        patch(
            "app.services.customer_feedback.feedback_voice_note_service.translate_answer_to_english"
        ) as translate,
    ):
        path_inst = MagicMock()
        path_inst.is_file.return_value = True
        path_inst.read_bytes.return_value = b"audio"
        path_inst.name = "x.webm"
        path_cls.return_value = path_inst
        stt.return_value = SimpleNamespace(
            ok=True,
            transcript="الورود كانت جميلة",
            detected_language="ar",
            error=None,
        )
        translate.return_value = {
            "original_text": "الورود كانت جميلة",
            "answer_text_en": "The flowers were nice",
            "translation_status": "completed",
        }
        result = process_voice_job(db, job_id)

    assert result["ok"] is True
    assert job.transcription_status == "completed"
    assert job.translation_status == "completed"
    assert job.original_text == "الورود كانت جميلة"
    assert job.translated_text == "The flowers were nice"
    assert response.original_text == "الورود كانت جميلة"
    assert response.answer_text_en == "The flowers were nice"
    assert response.answer_text == "The flowers were nice"
    assert response.transcription_status == "completed"
    assert response.translation_status == "completed"


def test_process_voice_job_stt_fail_sets_failed_without_blanking_later_completed():
    job_id = str(uuid.uuid4())
    response_id = str(uuid.uuid4())
    session_id = str(uuid.uuid4())
    job = FeedbackVoiceNoteJob(
        id=job_id,
        org_id="org1",
        session_id=session_id,
        response_id=response_id,
        inbound_message_id=f"web:{response_id}",
        provider_media_id="path:/tmp/x.webm",
        audio_file_path="/tmp/x.webm",
        transcription_status="pending",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    response = FeedbackResponse(
        id=response_id,
        session_id=session_id,
        org_id="org1",
        location_id="loc1",
        survey_type_id="st1",
        question_key="topic__tell_us_more",
        translation_status="pending",
        transcription_status="pending",
        answer_source="voice",
        step_order=1,
        created_at=datetime.utcnow(),
    )
    db = MagicMock()
    db.get.side_effect = lambda model, pk: (
        job if model is FeedbackVoiceNoteJob else response if model is FeedbackResponse else None
    )

    with (
        patch("app.services.customer_feedback.feedback_voice_note_service.Path") as path_cls,
        patch(
            "app.services.customer_feedback.feedback_voice_note_service.VoiceTranscriptionService.transcribe_uploaded_audio"
        ) as stt,
    ):
        path_inst = MagicMock()
        path_inst.is_file.return_value = True
        path_inst.read_bytes.return_value = b"audio"
        path_inst.name = "x.webm"
        path_cls.return_value = path_inst
        stt.return_value = SimpleNamespace(ok=False, transcript="", detected_language=None, error="boom")
        result = process_voice_job(db, job_id)

    assert result["ok"] is False
    assert job.transcription_status == "failed"
    assert response.transcription_status == "failed"
    assert response.answer_text_en is None
    assert response.original_text is None

    # Completed row must not be blanked by a later failure path.
    job.transcription_status = "completed"
    job.original_text = "kept"
    job.translated_text = "Kept EN"
    response.transcription_status = "completed"
    response.original_text = "kept"
    response.answer_text_en = "Kept EN"
    response.answer_text = "Kept EN"
    with patch("app.services.customer_feedback.feedback_voice_note_service.Path") as path_cls:
        path_inst = MagicMock()
        path_inst.is_file.return_value = False
        path_cls.return_value = path_inst
        # Early-return on completed+original
        result2 = process_voice_job(db, job_id)
    assert result2.get("ok") is True
    assert result2.get("duplicate") is True
    assert response.answer_text_en == "Kept EN"
    assert response.original_text == "kept"


def test_translate_answer_arabic_sets_completed_status():
    from app.services.customer_feedback.feedback_answer_service import translate_answer_to_english
    from app.services.survey_wa_translation_service import SurveyWaTranslationService

    db = MagicMock()
    with patch.object(
        SurveyWaTranslationService,
        "translate_to_english",
        return_value={"translated_text": "The service was slow", "translation_status": "completed"},
    ):
        out = translate_answer_to_english(
            db,
            answer="الخدمة كانت بطيئة",
            detected_language="ar",
            tpl=None,
            source_language="ar",
        )
    assert out["original_text"] == "الخدمة كانت بطيئة"
    assert out["answer_text_en"] == "The service was slow"
    assert out["translation_status"] == "completed"
