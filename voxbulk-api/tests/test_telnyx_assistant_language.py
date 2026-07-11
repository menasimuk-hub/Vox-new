from app.services.telnyx_assistant_service import _voice_settings_for_language, _transcription_for_language, parse_telnyx_assistant_voice


def test_parse_telnyx_elevenlabs_composite_voice():
    provider, voice_id, extras = parse_telnyx_assistant_voice(
        "ElevenLabs.eleven_flash_v2_5.lUTamkMw7gOzZbFIwmq4"
    )
    assert provider == "elevenlabs"
    assert voice_id == "lUTamkMw7gOzZbFIwmq4"
    assert extras["model_id"] == "eleven_flash_v2_5"


def test_parse_telnyx_raw_elevenlabs_voice_with_api_key_ref():
    provider, voice_id, extras = parse_telnyx_assistant_voice(
        "cgSgspJ2msm6clMCkdW9",
        voice_settings={"api_key_ref": "elevenlabs-prod"},
    )
    assert provider == "elevenlabs"
    assert voice_id == "cgSgspJ2msm6clMCkdW9"
    assert extras == {}


def test_parse_telnyx_native_voice():
    provider, voice_id, extras = parse_telnyx_assistant_voice("telnyx.NaturalHD.astra")
    assert provider == "telnyx"
    assert voice_id == ""
    assert extras == {}


def test_normalize_elevenlabs_voice_id_strips_telnyx_prefix():
    from app.services.providers.elevenlabs_service import normalize_elevenlabs_voice_id

    voice_id, model = normalize_elevenlabs_voice_id("ElevenLabs.eleven_flash_v2_5.lUTamkMw7gOzZbFIwmq4")
    assert voice_id == "lUTamkMw7gOzZbFIwmq4"
    assert model == "eleven_flash_v2_5"


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
    out = _voice_settings_for_language(existing, "ar")
    assert out is not None
    assert out.get("language_boost") == "ar"
    assert out.get("voice") == "Azure.ar-SA-HamedNeural"


def test_transcription_switches_to_arabic_azure():
    existing = {"transcription": {"model": "deepgram/flux", "language": "en"}}
    out = _transcription_for_language(existing, "ar")
    assert out == {"model": "azure/fast", "language": "ar-SA", "region": "westeurope"}


def test_transcription_fills_missing_azure_region():
    existing = {"transcription": {"model": "azure/fast", "language": "ar-SA", "region": None}}
    out = _transcription_for_language(existing, "ar")
    assert out == {"model": "azure/fast", "language": "ar-SA", "region": "westeurope"}


def test_transcription_keeps_valid_existing_region():
    existing = {"transcription": {"model": "azure/fast", "language": "ar-SA", "region": "eastus"}}
    assert _transcription_for_language(existing, "ar") is None


def test_transcription_clears_sticky_arabic_for_english():
    existing = {"transcription": {"model": "azure/fast", "language": "ar-SA", "region": "westeurope"}}
    out = _transcription_for_language(existing, "en")
    assert out == {"model": "deepgram/flux", "language": "en"}


def test_transcription_english_noop_when_already_flux_en():
    existing = {"transcription": {"model": "deepgram/flux", "language": "en"}}
    assert _transcription_for_language(existing, "en") is None


def test_voice_settings_clears_arabic_boost_for_english_native():
    existing = {"voice_settings": {"voice": "Telnyx.NaturalHD.albion", "language_boost": "ar", "voice_speed": 1.0}}
    out = _voice_settings_for_language(existing, "en")
    assert out is not None
    assert out.get("language_boost") == "English"
    assert out.get("voice") == "Telnyx.NaturalHD.albion"
