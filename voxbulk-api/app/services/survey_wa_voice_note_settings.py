"""Config helpers for WhatsApp survey voice notes."""

from __future__ import annotations

from app.core.config import get_settings


def voice_note_settings() -> dict:
    s = get_settings()
    return {
        "allow_voice_notes_for_open_text": bool(s.allow_voice_notes_for_open_text),
        "transcribe_voice_notes": bool(s.transcribe_voice_notes),
        "voice_note_max_file_size_mb": int(s.voice_note_max_file_size_mb or 16),
        "voice_note_max_file_size_bytes": int(s.voice_note_max_file_size_mb or 16) * 1024 * 1024,
        "voice_note_allowed_mime_types": list(s.voice_note_allowed_mime_types),
        "voice_note_download_timeout_seconds": int(s.voice_note_download_timeout_seconds or 30),
        "voice_note_transcription_timeout_seconds": int(s.voice_note_transcription_timeout_seconds or 180),
        "voice_note_retention_days": int(s.voice_note_retention_days or 90),
        "voice_note_storage_dir": str(s.voice_note_storage_dir or "data/survey_voice_notes"),
        "whisper_cpp_binary": str(s.whisper_cpp_binary or "whisper-cli"),
        "whisper_cpp_model": str(s.whisper_cpp_model or "").strip(),
        "ffmpeg_binary": str(s.ffmpeg_binary or "ffmpeg"),
    }


def voice_notes_enabled() -> bool:
    cfg = voice_note_settings()
    return bool(cfg["allow_voice_notes_for_open_text"] and cfg["transcribe_voice_notes"])
