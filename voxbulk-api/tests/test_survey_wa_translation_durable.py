"""Translation durability + any-language detection helpers."""

from __future__ import annotations

from app.services.survey_wa_open_text_service import apply_transcript_to_answer, merge_voice_metadata
from app.services.survey_wa_translation_service import SurveyWaTranslationService
from app.services.voice_transcription_service import _stt_language


def test_needs_translation_script_beats_false_en_label():
    arabic = "الصراحة لما دخلت المكان ما كان فيه ورد"
    assert SurveyWaTranslationService.needs_translation(arabic, "en") is True
    assert SurveyWaTranslationService.needs_translation(arabic, "en-US") is True


def test_needs_translation_english_ascii_skips():
    assert SurveyWaTranslationService.needs_translation("Thank you very much.", "en") is False
    assert SurveyWaTranslationService.needs_translation("Thank you very much.", None) is False


def test_needs_translation_non_en_lang_code():
    assert SurveyWaTranslationService.needs_translation("Bonjour", "fr") is True
    assert SurveyWaTranslationService.needs_translation("Hola", "es") is True


def test_merge_preserved_translations_keeps_sibling_english():
    existing = {
        "wa_conversation": {
            "answers": [
                {
                    "voice_note_job_id": "job-a",
                    "answer": "Hello flowers",
                    "original_text": "الورود",
                    "translated_text": "Hello flowers",
                    "translation_status": "completed",
                },
                {"voice_note_job_id": "job-b", "answer": "pending"},
            ]
        }
    }
    incoming = {
        "wa_conversation": {
            "answers": [
                {"voice_note_job_id": "job-a", "answer": "الورود", "answer_text": "الورود"},
                {
                    "voice_note_job_id": "job-b",
                    "answer": "Actually no",
                    "translation_status": "not_needed",
                },
            ]
        }
    }
    merged = SurveyWaTranslationService.merge_preserved_translations(existing, incoming)
    a0 = merged["wa_conversation"]["answers"][0]
    assert a0["translated_text"] == "Hello flowers"
    assert a0["translation_status"] == "completed"
    assert a0["answer"] == "Hello flowers"


def test_apply_transcript_clears_stale_translation():
    ans = {
        "answer": "old",
        "translated_text": "Old English",
        "translation_status": "completed",
        "original_text": "قديم",
    }
    out = apply_transcript_to_answer(ans, text="جديد", detected_language="ar", status="completed")
    assert out["original_text"] == "جديد"
    assert "translated_text" not in out
    assert out["translation_status"] == "pending"


def test_merge_voice_metadata_skips_empty_clobber():
    target = {"answer_text": "good transcript", "translated_text": "Good"}
    source = {"answer_text": "", "translated_text": None, "transcription_status": "pending"}
    out = merge_voice_metadata(target, source)
    assert out["answer_text"] == "good transcript"
    assert out["translated_text"] == "Good"
    assert out["transcription_status"] == "pending"


def test_stt_language_defaults_auto_not_arabic():
    assert _stt_language(None) == "auto"
    assert _stt_language("fr") == "auto"
    assert _stt_language("es-ES") == "auto"
    assert _stt_language("ar") == "ar"
    assert _stt_language("en_GB") == "en"
