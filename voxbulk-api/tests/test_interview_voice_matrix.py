"""Tests for interview voice matrix helpers."""

from __future__ import annotations

from app.services.interview_voice_matrix_service import (
    load_voice_matrix,
    matrix_entry_for_slug,
    pick_telnyx_voice,
    voice_settings_from_entry,
)


def test_load_voice_matrix_has_twelve_english_agents():
    rows = load_voice_matrix()
    assert len(rows) == 12
    slugs = {r["slug"] for r in rows}
    assert "interview-gb-leo" in slugs
    assert "interview-au-chloe" in slugs
    assert not any(s.startswith("interview-ar-") for s in slugs)


def test_voice_settings_telnyx_no_api_key_ref():
    entry = matrix_entry_for_slug("interview-gb-leo")
    assert entry is not None
    settings = voice_settings_from_entry(entry)
    assert settings["voice"] == "Telnyx.Ultra.Asher"
    assert "api_key_ref" not in settings


def test_voice_settings_elevenlabs_has_api_key_ref():
    entry = matrix_entry_for_slug("interview-au-jack")
    assert entry is not None
    settings = voice_settings_from_entry(entry)
    assert settings["voice"].startswith("ElevenLabs.")
    assert settings["api_key_ref"] == "elevenlabs-paid"


def test_voice_settings_jode_elevenlabs_female():
    entry = matrix_entry_for_slug("interview-gb-jode")
    assert entry is not None
    assert entry["provider"] == "elevenlabs"
    assert entry["gender"] == "female"
    settings = voice_settings_from_entry(entry)
    assert settings["voice"].startswith("ElevenLabs.")
    assert "Xb7hH8MSUJpSbSDYk0k2" in settings["voice"]


def test_voice_settings_ie_sean_valid_elevenlabs_id():
    entry = matrix_entry_for_slug("interview-ie-sean")
    assert entry is not None
    assert entry["gender"] == "male"
    settings = voice_settings_from_entry(entry)
    assert "TX3LPaxmHKxFdv7VOQQH" not in settings["voice"]
    assert "D38z5RcWu1voky8WS1ja" not in settings["voice"]
    assert "onwK4e9ZLuTAKqWW03F9" in settings["voice"]


def test_pick_telnyx_voice_skips_uuid():
    voices = [
        {"voice_id": "00967b2f-88a6-4a31-8153-110a92134b9f", "gender": "male", "language": "en"},
        {"voice_id": "albion", "gender": "male", "language": "en-US", "model_id": "NaturalHD"},
    ]
    picked, score = pick_telnyx_voice(voices, region="US", gender="male")
    assert picked == "Telnyx.NaturalHD.albion"
    assert score > 0
