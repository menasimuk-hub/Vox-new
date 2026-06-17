"""Guards for voice-note transcripts before agent/orchestrator pipelines."""

from __future__ import annotations

from app.abuu.services.abuu_voice_service import AbuuVoiceTranscription, is_low_quality_transcript
from app.abuu.services.reply_service import voice_low_confidence_message, voice_unclear_transcript_message


def voice_transcript_usable(text: str, voice: AbuuVoiceTranscription | None = None) -> bool:
    stripped = str(text or "").strip()
    if not stripped:
        return False
    if is_low_quality_transcript(stripped):
        return False
    if voice is not None and not voice.ok:
        return False
    return True


def voice_clarification_reply(lang: str, *, voice: AbuuVoiceTranscription | None = None) -> str:
    if voice is not None and not voice.ok and voice.needs_clarification:
        return voice_low_confidence_message(lang)
    return voice_unclear_transcript_message(lang)
