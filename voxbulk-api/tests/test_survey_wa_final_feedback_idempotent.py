"""Final feedback persist must update by voice_note_job_id, not double-append."""

from __future__ import annotations

from app.services.survey_wa_final_feedback_service import FINAL_FEEDBACK_TEXT_ROLE, persist_final_feedback_text


def test_persist_final_feedback_text_idempotent_by_job_id():
    payload = {"wa_conversation": {"answers": []}}
    settings = {"open_text_prompt": "Anything else?"}
    voice = {
        "answer_source": "voice_note",
        "voice_note_job_id": "job-ff-1",
        "transcription_status": "completed",
        "detected_language": "ar",
        "answer_text": "شكرا",
    }
    persist_final_feedback_text(payload, text="شكرا", settings=settings, voice_answer=voice)
    persist_final_feedback_text(
        payload,
        text="شكرا جدا",
        settings=settings,
        voice_answer={**voice, "answer_text": "شكرا جدا"},
    )
    answers = payload["wa_conversation"]["answers"]
    ff = [a for a in answers if a.get("step_role") == FINAL_FEEDBACK_TEXT_ROLE]
    assert len(ff) == 1
    assert ff[0]["answer"] == "شكرا جدا"
    assert ff[0]["voice_note_job_id"] == "job-ff-1"
