from __future__ import annotations

import base64
import time
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.core.http_ssl import httpx_ssl_verify
from app.services.telnyx_api_key import require_telnyx_api_key


def synthesize_telnyx_speech(
    db: Session,
    *,
    text: str,
    voice: str,
    voice_speed: float | None = None,
) -> dict[str, Any]:
    clean_text = str(text or "").strip()
    clean_voice = str(voice or "").strip()
    if not clean_text:
        raise ValueError("Text is required for Telnyx TTS")
    if not clean_voice:
        raise ValueError("Telnyx voice identifier is required")

    api_key, _source = require_telnyx_api_key(db)
    payload: dict[str, Any] = {
        "text": clean_text,
        "voice": clean_voice,
        "output_type": "base64_output",
    }
    telnyx_params: dict[str, Any] = {"response_format": "mp3", "sampling_rate": 24000}
    if voice_speed is not None:
        try:
            telnyx_params["voice_speed"] = max(0.25, min(2.0, float(voice_speed)))
        except (TypeError, ValueError):
            pass
    payload["telnyx"] = telnyx_params

    started = time.perf_counter()
    with httpx.Client(timeout=45.0, verify=httpx_ssl_verify()) as client:
        response = client.post(
            "https://api.telnyx.com/v2/text-to-speech",
            json=payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
    response.raise_for_status()
    body = response.json() if response.content else {}
    audio_b64 = ""
    if isinstance(body, dict):
        audio_b64 = str(body.get("base64_audio") or body.get("data", {}).get("base64_audio") or "").strip()
        if not audio_b64 and isinstance(body.get("data"), dict):
            audio_b64 = str(body["data"].get("base64_audio") or "").strip()
    if not audio_b64:
        raise ValueError("Telnyx TTS returned no audio")
    audio_data = base64.b64decode(audio_b64)
    return {
        "ok": True,
        "audio_data": audio_data,
        "audio_mime": "audio/mpeg",
        "voice_id": clean_voice,
        "timings": {"telnyx_tts_ms": int((time.perf_counter() - started) * 1000)},
    }
