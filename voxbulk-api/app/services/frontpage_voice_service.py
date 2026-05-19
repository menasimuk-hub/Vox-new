from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.services.providers.cartesia_service import CartesiaProviderService
from app.services.providers.elevenlabs_service import ElevenLabsProviderService
from app.services.telnyx_tts_service import synthesize_telnyx_speech


def synthesize_frontpage_voice(db: Session, payload: dict[str, Any], text: str) -> dict[str, Any]:
    """TTS for front-page Telnyx browser calls using the Telnyx assistant's voice when possible."""
    clean = str(text or "").strip()
    if not clean:
        raise ValueError("Text is required")

    tts_provider = str(payload.get("tts_provider") or "telnyx").strip().lower()
    if tts_provider == "telnyx":
        voice = str(payload.get("telnyx_voice") or "").strip()
        if not voice:
            raise ValueError("Telnyx assistant has no voice configured in the portal")
        speed = payload.get("telnyx_voice_speed")
        return synthesize_telnyx_speech(db, text=clean, voice=voice, voice_speed=speed)

    if tts_provider == "elevenlabs":
        voice_id = str(payload.get("elevenlabs_voice_id") or "").strip() or None
        settings = payload.get("elevenlabs_voice_settings")
        if not isinstance(settings, dict):
            settings = None
        return ElevenLabsProviderService.synthesize_text_result(
            db,
            text=clean,
            voice_id=voice_id,
            voice_settings=settings,
        )

    config = CartesiaProviderService._config(db)
    voice_id = str(payload.get("cartesia_voice_id") or payload.get("voice_id") or config.get("voice_id") or "").strip() or None
    session = CartesiaProviderService.realtime_session_from_config(config, voice_id=voice_id)
    with session:
        chunks = list(session.synthesize_chunks(clean))
    if not chunks or not chunks[0].get("ok"):
        detail = chunks[0] if chunks else {}
        raise ValueError(str(detail.get("error") or "Cartesia TTS failed"))
    merged = b"".join(bytes(chunk.get("audio_data") or b"") for chunk in chunks)
    first = chunks[0]
    return {
        "ok": True,
        "audio_data": merged,
        "audio_mime": first.get("audio_mime") or "audio/wav",
        "voice_id": first.get("voice_id") or voice_id,
        "timings": first.get("timings") or {},
    }
