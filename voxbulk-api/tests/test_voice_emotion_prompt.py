"""Tests for shared voice emotion prompt helpers."""

from app.services.voice_emotion_prompt import (
    VOICE_EMOTION_INSTRUCTIONS,
    ensure_voice_emotion_instructions,
)


def test_ensure_voice_emotion_appends_once():
    first = ensure_voice_emotion_instructions("You are Jode.")
    assert "## Human emotion" in first
    assert "<emotion value=" in first
    second = ensure_voice_emotion_instructions(first)
    assert second.count("## Human emotion") == 1


def test_ensure_voice_emotion_on_empty_uses_block():
    out = ensure_voice_emotion_instructions("")
    assert out == VOICE_EMOTION_INSTRUCTIONS
