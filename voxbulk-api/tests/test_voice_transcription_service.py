"""Unit tests for neutral VoiceTranscriptionService."""

from __future__ import annotations

from app.services.voice_transcription_service import (
    VoiceTranscriptionService,
    is_low_quality_transcript,
    stt_provider_order,
)


def test_is_low_quality_transcript():
    assert is_low_quality_transcript("") is True
    assert is_low_quality_transcript("a") is True
    assert is_low_quality_transcript("hahaha") is True
    assert is_low_quality_transcript("good service today") is False


def test_stt_provider_order_default():
    assert stt_provider_order() == ("deepgram", "deepinfra", "whisper_cpp", "groq")


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
