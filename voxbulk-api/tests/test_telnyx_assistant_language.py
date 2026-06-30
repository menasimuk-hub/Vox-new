from app.services.telnyx_assistant_service import _voice_settings_for_language, _transcription_for_language


def test_voice_settings_skips_elevenlabs_assistant():
    existing = {
        "voice_settings": {
            "voice": "cgSgspJ2msm6clMCkdW9",
            "api_key_ref": "elevenlabs-prod",
        }
    }
    assert _voice_settings_for_language(existing, "ar") is None


def test_voice_settings_sets_boost_for_azure_voice():
    existing = {"voice_settings": {"voice": "Azure.ar-SA-HamedNeural"}}
    assert _voice_settings_for_language(existing, "ar") == {"language_boost": "ar"}


def test_transcription_switches_to_arabic_azure():
    existing = {"transcription": {"model": "deepgram/flux", "language": "en"}}
    out = _transcription_for_language(existing, "ar")
    assert out == {"model": "azure/fast", "language": "ar-SA"}
