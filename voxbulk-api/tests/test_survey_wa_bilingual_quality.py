"""Franco-Arabic translation detection and bilingual results serialize."""

from __future__ import annotations


def test_needs_translation_franco_arabic_latin():
    from app.services.survey_wa_translation_service import SurveyWaTranslationService as S

    assert S.needs_translation("Wallahi dindya harri jidden jidden") is True
    assert S.looks_like_franco_arabic("Wallahi dindya harri jidden") is True
    assert S.needs_translation("Everything is fine thanks") is False
    assert S.needs_translation("تلازة خربانا") is True


def test_needs_translation_false_en_label_with_arabic_script():
    from app.services.survey_wa_translation_service import SurveyWaTranslationService as S

    # Non-ASCII wins over a false STT English label
    assert S.needs_translation("التكييف خربان", detected_language="en") is True


def test_serialize_open_answer_keeps_original_and_english():
    from app.services.survey_results_service import _serialize_open_answer

    row = _serialize_open_answer(
        {
            "question": "Why?",
            "step_role": "tell_us_more",
            "answer_source": "text",
            "original_text": "Wallahi dindya harri jidden",
            "translated_text": "I swear the weather/world is very hot",
            "answer": "I swear the weather/world is very hot",
            "translation_status": "completed",
        },
        order_id="ord-1",
    )
    assert row["original_text"] == "Wallahi dindya harri jidden"
    assert row["translated_text"] == "I swear the weather/world is very hot"
    assert row["english_text"] == "I swear the weather/world is very hot"
    assert row["text"] == "I swear the weather/world is very hot"


def test_normalize_wa_answer_bilingual():
    from app.services.survey_results_service import _normalize_wa_answer_bilingual

    out = _normalize_wa_answer_bilingual(
        {
            "question": "Q",
            "original_text": "تلازة خربانا",
            "translated_text": "The fridge is broken",
            "answer": "The fridge is broken",
            "translation_status": "completed",
        }
    )
    assert out["original_text"] == "تلازة خربانا"
    assert out["translated_text"] == "The fridge is broken"
    assert out["english_text"] == "The fridge is broken"


def test_wa_survey_whisper_model_prefers_large_v3_over_turbo(monkeypatch):
    from app.services.providers import deepinfra_service as di
    from app.services.providers.deepinfra_service import (
        WA_SURVEY_WHISPER_MODEL,
        DeepInfraProviderService,
    )

    class _Db:
        pass

    monkeypatch.setattr(
        DeepInfraProviderService,
        "_config",
        staticmethod(
            lambda db: {
                "api_key": "x",
                "model_name": "openai/whisper-large-v3-turbo",
                "base_url": "https://api.deepinfra.com/v1/inference/openai/whisper-large-v3-turbo",
            }
        ),
    )
    assert DeepInfraProviderService.resolve_wa_survey_model(_Db()) == WA_SURVEY_WHISPER_MODEL
    assert "turbo" not in WA_SURVEY_WHISPER_MODEL
    assert di.DEEPINFRA_DEFAULT_MODEL == "openai/whisper-large-v3"
