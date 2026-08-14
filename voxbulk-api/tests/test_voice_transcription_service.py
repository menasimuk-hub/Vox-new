"""Unit tests for neutral VoiceTranscriptionService."""

from __future__ import annotations

import pytest

from app.services.voice_transcription_service import (
    VoiceTranscriptionService,
    is_low_quality_transcript,
    is_usable_feedback_reason,
    stt_provider_order,
)


def test_is_low_quality_transcript():
    assert is_low_quality_transcript("") is True
    assert is_low_quality_transcript("a") is True
    assert is_low_quality_transcript("hahaha") is True
    assert is_low_quality_transcript("good service today") is False


@pytest.mark.parametrize(
    "text",
    ["", "skip", "ok", "xdvds", "asdf", "12345", "aaaaaaa", "!!!!!!!!", "k", "n/a", "nothing"],
)
def test_is_usable_feedback_reason_rejects_gibberish_and_fillers(text):
    assert is_usable_feedback_reason(text) is False


def test_is_usable_feedback_reason_accepts_real_reasons():
    assert is_usable_feedback_reason("Service was slow and rude") is True
    assert is_usable_feedback_reason("Waiting too long at reception") is True


def test_stt_provider_order_default():
    assert stt_provider_order() == ("deepinfra", "deepgram", "whisper_cpp", "groq")


def test_transcribe_inbound_no_media():
    class _Db:
        pass

    result = VoiceTranscriptionService.transcribe_inbound(
        _Db(),  # type: ignore[arg-type]
        record={"type": "text"},
        customer_phone="+447700900000",
    )
    assert result.ok is False
    assert result.error == "no_media"
