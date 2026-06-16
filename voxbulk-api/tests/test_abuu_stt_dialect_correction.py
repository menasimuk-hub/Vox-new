"""Tests for Abuu STT dialect hint + DeepSeek correction."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.abuu.services.abuu_voice_service import AbuuVoiceService
from app.abuu.voice_interpretation.stt_dialect_correction import (
    correct_stt_transcript,
    is_stt_garbage,
    rescore_after_correction,
)
from app.abuu.waiter.deepseek_client import DeepSeekResult
from app.abuu.waiter.interpretation import STT_CLARIFY_MESSAGE_AR, WaiterInterpretation


def test_is_stt_garbage_detects_non_arabic_noise():
    assert is_stt_garbage("hello world xyz abc", language="ar") is True


def test_is_stt_garbage_allows_arabic_order():
    assert is_stt_garbage("بدي شاورما دجاج", language="ar") is False


def test_is_stt_garbage_skips_english_profile():
    assert is_stt_garbage("hello pizza", language="en") is False


def test_rescore_after_correction_applies_075_on_change():
    score = rescore_after_correction(
        raw="إيدي دجاج",
        corrected="بدي دجاج",
        raw_confidence=0.9,
    )
    assert score == 0.75


def test_rescore_after_correction_keeps_raw_confidence_when_unchanged():
    score = rescore_after_correction(
        raw="بدي بيتزا",
        corrected="بدي بيتزا",
        raw_confidence=0.9,
    )
    assert score == 0.9


def test_rescore_after_correction_low_on_failure():
    score = rescore_after_correction(
        raw="إيدي دجاج",
        corrected="إيدي دجاج",
        raw_confidence=0.9,
        correction_failed=True,
    )
    assert score == 0.2


@patch("app.abuu.voice_interpretation.stt_dialect_correction.WaiterDeepSeekClient.complete")
def test_correct_stt_transcript_applies_deepseek(mock_complete):
    mock_complete.return_value = DeepSeekResult(text="بدي شاورما دجاج", fallback_used=False)
    corrected, failed = correct_stt_transcript(
        MagicMock(),
        raw="إيدي دجاج شاور ماذا جاج عندك",
        phone="+972501234567",
        language="ar",
    )
    assert failed is False
    assert corrected == "بدي شاورما دجاج"


@patch("app.abuu.voice_interpretation.stt_dialect_correction.WaiterDeepSeekClient.complete")
def test_correct_stt_transcript_falls_back_on_unclear(mock_complete):
    mock_complete.return_value = DeepSeekResult(text="UNCLEAR", fallback_used=False)
    corrected, failed = correct_stt_transcript(
        MagicMock(),
        raw="إيدي دجاج شاور ماذا",
        phone="+972501234567",
        language="ar",
    )
    assert failed is True
    assert corrected == "إيدي دجاج شاور ماذا"


@patch("app.abuu.voice_interpretation.stt_dialect_correction.WaiterDeepSeekClient.complete")
def test_correct_stt_transcript_falls_back_on_exception(mock_complete):
    mock_complete.side_effect = TimeoutError("deepseek timeout")
    corrected, failed = correct_stt_transcript(
        MagicMock(),
        raw="بدي بيتزا",
        phone="+972501234567",
        language="ar",
    )
    assert failed is True
    assert corrected == "بدي بيتزا"


@patch("app.abuu.services.abuu_voice_service.correct_stt_transcript")
@patch("app.abuu.services.abuu_voice_service.download_media_file")
@patch("app.abuu.services.abuu_voice_service.DeepInfraProviderService.is_configured", return_value=True)
@patch("app.abuu.services.abuu_voice_service.DeepInfraProviderService.transcribe_audio_file")
def test_transcribe_inbound_applies_correction(
    mock_transcribe,
    _mock_configured,
    mock_download,
    mock_correct,
):
    mock_download.return_value = (Path("/tmp/voice.ogg"), 1000, "audio/ogg")
    mock_transcribe.return_value = {"text": "إيدي دجاج شاور ماذا جاج عندك"}
    mock_correct.return_value = ("بدي شاورما دجاج", False)

    result = AbuuVoiceService.transcribe_inbound(
        MagicMock(),
        record={"media": [{"url": "https://example.com/v.ogg", "content_type": "audio/ogg"}]},
        customer_phone="+972501234567",
        language="ar",
    )

    assert result.transcript == "بدي شاورما دجاج"
    assert result.raw_transcript == "إيدي دجاج شاور ماذا جاج عندك"
    assert result.correction_applied is True
    assert result.confidence == 0.75
    mock_transcribe.assert_called_once()
    call_kwargs = mock_transcribe.call_args.kwargs
    assert call_kwargs["language"] == "ar"
    assert call_kwargs.get("prompt")


@patch("app.abuu.services.abuu_voice_service.correct_stt_transcript")
@patch("app.abuu.services.abuu_voice_service.download_media_file")
@patch("app.abuu.services.abuu_voice_service.DeepInfraProviderService.is_configured", return_value=True)
@patch("app.abuu.services.abuu_voice_service.DeepInfraProviderService.transcribe_audio_file")
def test_transcribe_inbound_skips_deepseek_on_garbage(
    mock_transcribe,
    _mock_configured,
    mock_download,
    mock_correct,
):
    mock_download.return_value = (Path("/tmp/voice.ogg"), 1000, "audio/ogg")
    mock_transcribe.return_value = {"text": "hello world xyz abc"}

    result = AbuuVoiceService.transcribe_inbound(
        MagicMock(),
        record={"media": [{"url": "https://example.com/v.ogg", "content_type": "audio/ogg"}]},
        customer_phone="+972501234567",
        language="ar",
    )

    mock_correct.assert_not_called()
    assert result.garbage_detected is True
    assert result.needs_clarification is True
    assert result.confidence == 0.2


@patch("app.abuu.services.abuu_voice_service.correct_stt_transcript")
@patch("app.abuu.services.abuu_voice_service.download_media_file")
@patch("app.abuu.services.abuu_voice_service.DeepInfraProviderService.is_configured", return_value=True)
@patch("app.abuu.services.abuu_voice_service.DeepInfraProviderService.transcribe_audio_file")
def test_transcribe_inbound_unchanged_correct_text(
    mock_transcribe,
    _mock_configured,
    mock_download,
    mock_correct,
):
    mock_download.return_value = (Path("/tmp/voice.ogg"), 1000, "audio/ogg")
    mock_transcribe.return_value = {"text": "بدي بيتزا مرغريتا"}
    mock_correct.return_value = ("بدي بيتزا مرغريتا", False)

    result = AbuuVoiceService.transcribe_inbound(
        MagicMock(),
        record={"media": [{"url": "https://example.com/v.ogg", "content_type": "audio/ogg"}]},
        customer_phone="+972501234567",
        language="ar",
    )

    assert result.transcript == "بدي بيتزا مرغريتا"
    assert result.correction_applied is False
    assert result.confidence == 0.9


@patch("app.abuu.waiter.interpretation.build_menu_haystack", return_value=[])
@patch("app.abuu.waiter.interpretation.best_fuzzy_match", return_value=(None, 0, []))
def test_waiter_interpretation_stt_clarify_first_time(_mock_fuzzy, _mock_haystack):
    from app.abuu.agent.session import Session as AgentSession

    session = AgentSession(customer_wa_number="+972501234567", language="ar", context={})
    result = WaiterInterpretation.interpret(
        MagicMock(),
        MagicMock(),
        transcript="إيدي دجاج شاور ماذا",
        stt_confidence=0.2,
        session=session,
        lang="ar",
        is_voice=True,
        stt_needs_clarification=True,
    )
    assert result.needs_clarification is True
    assert result.clarification_reason == "stt_low_quality"
    assert result.clarification_prompt == STT_CLARIFY_MESSAGE_AR


@patch("app.abuu.waiter.interpretation.build_menu_haystack", return_value=[])
@patch("app.abuu.waiter.interpretation.best_fuzzy_match", return_value=(None, 0, []))
def test_waiter_interpretation_stt_clarify_skipped_after_repeat(_mock_fuzzy, _mock_haystack):
    from app.abuu.agent.session import Session as AgentSession

    session = AgentSession(
        customer_wa_number="+972501234567",
        language="ar",
        context={"clarification_count": 1},
    )
    result = WaiterInterpretation.interpret(
        MagicMock(),
        MagicMock(),
        transcript="إيدي دجاج شاور ماذا",
        stt_confidence=0.2,
        session=session,
        lang="ar",
        is_voice=True,
        stt_needs_clarification=True,
    )
    assert result.needs_clarification is False
