from __future__ import annotations

import logging
import ssl
import time
from typing import Any

import certifi
import httpx
from sqlalchemy.orm import Session

from app.services.provider_settings import ProviderSettingsService

logger = logging.getLogger(__name__)


def normalize_elevenlabs_voice_id(voice_id: str) -> tuple[str, str | None]:
    """Telnyx stores ElevenLabs as ``ElevenLabs.{model}.{voice_id}`` — API needs the last segment."""
    raw = str(voice_id or "").strip()
    if raw.lower().startswith("elevenlabs."):
        parts = raw.split(".")
        if len(parts) >= 3:
            return parts[-1], parts[1]
        if len(parts) == 2 and parts[1].strip():
            return parts[1].strip(), None
    return raw, None


class ElevenLabsProviderService:
    TEST_PHRASE = "Hello, this is your ElevenLabs voice test."

    @staticmethod
    def _ssl_context() -> ssl.SSLContext | str:
        try:
            import truststore

            return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        except Exception:
            return certifi.where()

    @staticmethod
    def _config(db: Session) -> dict[str, Any]:
        cfg, enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="elevenlabs")
        if not enabled:
            raise ValueError("ElevenLabs is not configured or enabled")
        return ProviderSettingsService._validate_elevenlabs_config(cfg or {})

    @staticmethod
    def _voice_settings(config: dict[str, Any], overrides: dict[str, Any] | None = None) -> dict[str, Any]:
        merged = {**config, **(overrides or {})}
        settings: dict[str, Any] = {}
        for key in ["stability", "similarity_boost", "style", "speed"]:
            value = merged.get(key)
            if value is not None and value != "":
                settings[key] = float(value)
        settings["use_speaker_boost"] = ProviderSettingsService._bool_config(merged.get("speaker_boost"), default=True)
        return settings

    @staticmethod
    def synthesize_text_result(
        db: Session,
        *,
        text: str,
        voice_id: str | None = None,
        voice_settings: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        total_start = time.perf_counter()
        config = ElevenLabsProviderService._config(db)
        raw_voice_id = str(voice_id or config.get("default_voice_id") or "").strip()
        selected_voice_id, composite_model = normalize_elevenlabs_voice_id(raw_voice_id)
        if not selected_voice_id:
            raise ValueError("ElevenLabs voice_id is required")
        merged_settings = dict(voice_settings or {})
        if composite_model and not merged_settings.get("model_id"):
            merged_settings["model_id"] = composite_model
        base_url = str(config.get("base_url") or "https://api.elevenlabs.io").rstrip("/")
        model_id = str(merged_settings.get("model_id") or config.get("model_id") or "eleven_multilingual_v2")
        output_format = str(merged_settings.get("output_format") or config.get("output_format") or "mp3_44100_128")
        url = f"{base_url}/v1/text-to-speech/{selected_voice_id}"
        payload = {
            "text": str(text or ""),
            "model_id": model_id,
            "voice_settings": ElevenLabsProviderService._voice_settings(config, merged_settings),
        }
        headers = {
            "xi-api-key": config["api_key"],
            "Accept": "audio/mpeg",
            "Content-Type": "application/json",
        }
        request_start = time.perf_counter()
        with httpx.Client(timeout=45.0, verify=ElevenLabsProviderService._ssl_context()) as client:
            response = client.post(url, params={"output_format": output_format}, json=payload, headers=headers)
        request_ms = int((time.perf_counter() - request_start) * 1000)
        total_ms = int((time.perf_counter() - total_start) * 1000)
        if not response.is_success:
            try:
                detail: Any = response.json()
            except Exception:
                detail = response.text
            logger.error("elevenlabs_tts_failed", extra={"status_code": response.status_code, "voice_id": selected_voice_id, "detail": detail})
            return {
                "ok": False,
                "error": detail,
                "status_code": response.status_code,
                "voice_id": selected_voice_id,
                "timings": {"elevenlabs_request_ms": request_ms, "elevenlabs_total_ms": total_ms},
            }
        audio_data = bytes(response.content or b"")
        return {
            "ok": True,
            "audio_data": audio_data,
            "audio_bytes": len(audio_data),
            "audio_mime": "audio/mpeg",
            "voice_id": selected_voice_id,
            "model_id": model_id,
            "voice_settings": payload["voice_settings"],
            "timings": {"elevenlabs_request_ms": request_ms, "elevenlabs_total_ms": total_ms},
        }

    @staticmethod
    def test_tts(db: Session, *, text: str | None = None, voice_id: str | None = None) -> dict[str, Any]:
        result = ElevenLabsProviderService.synthesize_text_result(db, text=text or ElevenLabsProviderService.TEST_PHRASE, voice_id=voice_id)
        return {k: v for k, v in result.items() if k != "audio_data"}

    @staticmethod
    def transcribe_audio_result(
        db: Session,
        *,
        audio_data: bytes,
        filename: str = "speech.webm",
        content_type: str = "audio/webm",
        model_id: str = "scribe_v1",
        language_code: str | None = None,
    ) -> dict[str, Any]:
        total_start = time.perf_counter()
        config = ElevenLabsProviderService._config(db)
        base_url = str(config.get("base_url") or "https://api.elevenlabs.io").rstrip("/")
        data: dict[str, str] = {"model_id": model_id}
        if language_code:
            data["language_code"] = language_code
        files = {"file": (filename, audio_data, content_type)}
        request_start = time.perf_counter()
        with httpx.Client(timeout=45.0, verify=ElevenLabsProviderService._ssl_context()) as client:
            response = client.post(
                f"{base_url}/v1/speech-to-text",
                headers={"xi-api-key": config["api_key"]},
                data=data,
                files=files,
            )
        request_ms = int((time.perf_counter() - request_start) * 1000)
        total_ms = int((time.perf_counter() - total_start) * 1000)
        try:
            body: Any = response.json()
        except Exception:
            body = {"raw_text": response.text}
        if not response.is_success:
            logger.error("elevenlabs_stt_failed", extra={"status_code": response.status_code, "detail": body})
            return {
                "ok": False,
                "error": body,
                "status_code": response.status_code,
                "timings": {"elevenlabs_stt_request_ms": request_ms, "elevenlabs_stt_total_ms": total_ms},
            }
        return {
            "ok": True,
            "text": str(body.get("text") or "").strip() if isinstance(body, dict) else "",
            "raw": body,
            "model_id": model_id,
            "audio_bytes": len(audio_data),
            "timings": {"elevenlabs_stt_request_ms": request_ms, "elevenlabs_stt_total_ms": total_ms},
        }

    @staticmethod
    def voices(db: Session) -> dict[str, Any]:
        config = ElevenLabsProviderService._config(db)
        base_url = str(config.get("base_url") or "https://api.elevenlabs.io").rstrip("/")
        with httpx.Client(timeout=20.0, verify=ElevenLabsProviderService._ssl_context()) as client:
            response = client.get(f"{base_url}/v1/voices", headers={"xi-api-key": config["api_key"]})
        try:
            body: Any = response.json()
        except Exception:
            body = {"raw_text": response.text}
        if not response.is_success:
            raise ValueError(f"ElevenLabs voices request failed ({response.status_code}): {body}")
        return body

