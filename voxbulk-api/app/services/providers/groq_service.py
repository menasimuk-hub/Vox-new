from __future__ import annotations

import logging
import os
import ssl
import time
from typing import Any

import certifi
import httpx
from sqlalchemy.orm import Session

from app.services.provider_settings import ProviderSettingsService

logger = logging.getLogger(__name__)


GROQ_DEFAULT_BASE_URL = "https://api.groq.com/openai"
GROQ_DEFAULT_STT_MODEL = "whisper-large-v3-turbo"
GROQ_DEFAULT_TTS_MODEL = "canopylabs/orpheus-v1-english"
GROQ_ORPHEUS_VOICES = {"austin", "diana"}


class GroqProviderService:
    @staticmethod
    def _ssl_context() -> ssl.SSLContext | str:
        try:
            import truststore

            return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        except Exception:
            return certifi.where()

    @staticmethod
    def _base_url(raw: Any = None) -> str:
        base = str(raw or GROQ_DEFAULT_BASE_URL).strip().rstrip("/")
        while base.endswith("/v1"):
            base = base[:-3].rstrip("/")
        return base or GROQ_DEFAULT_BASE_URL

    @staticmethod
    def _voice(raw: Any = None) -> str:
        voice = str(raw or "austin").strip().lower()
        return voice if voice in GROQ_ORPHEUS_VOICES else "austin"

    @staticmethod
    def _config(db: Session) -> dict[str, Any]:
        cfg, enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="groq")
        config = cfg or {}
        api_key = str(config.get("api_key") or os.getenv("GROQ_API_KEY") or "").strip()
        if not enabled and not api_key:
            raise ValueError("Groq is not configured or enabled")
        if not api_key:
            raise ValueError("Groq API key is required")
        return {
            "api_key": api_key,
            "base_url": GroqProviderService._base_url(config.get("base_url") or os.getenv("GROQ_BASE_URL")),
            "stt_model": str(config.get("stt_model") or config.get("default_stt_model") or os.getenv("GROQ_STT_MODEL") or GROQ_DEFAULT_STT_MODEL).strip(),
            "tts_model": str(config.get("tts_model") or config.get("default_tts_model") or os.getenv("GROQ_TTS_MODEL") or GROQ_DEFAULT_TTS_MODEL).strip(),
            "tts_voice": GroqProviderService._voice(config.get("tts_voice") or config.get("default_tts_voice") or os.getenv("GROQ_TTS_VOICE")),
        }

    @staticmethod
    def diagnostics(db: Session) -> dict[str, Any]:
        config = GroqProviderService._config(db)
        return {
            "base_url": config["base_url"],
            "stt_model": config["stt_model"],
            "tts_model": config["tts_model"],
            "tts_voice": config["tts_voice"],
            "api_key_set": bool(config["api_key"]),
            "api_key_length": len(config["api_key"]),
        }

    @staticmethod
    def transcribe_audio_result(
        db: Session,
        *,
        audio: bytes,
        filename: str = "audio.webm",
        content_type: str = "audio/webm",
        language: str | None = None,
        prompt: str | None = None,
    ) -> dict[str, Any]:
        start = time.perf_counter()
        config = GroqProviderService._config(db)
        files = {"file": (filename, audio, content_type)}
        stt_lang = str(language or "ar").strip().lower() or "ar"
        data = {
            "model": config["stt_model"] or GROQ_DEFAULT_STT_MODEL,
            "language": stt_lang,
            "response_format": "json",
        }
        if prompt:
            data["prompt"] = str(prompt).strip()
        headers = {"Authorization": f"Bearer {config['api_key']}"}

        def _post(form_data: dict[str, str]) -> httpx.Response:
            with httpx.Client(timeout=45.0, verify=GroqProviderService._ssl_context()) as client:
                return client.post(
                    f"{config['base_url']}/v1/audio/transcriptions",
                    data=form_data,
                    files=files,
                    headers=headers,
                )

        response = _post(data)
        elapsed = int((time.perf_counter() - start) * 1000)
        if not response.is_success and prompt:
            logger.warning(
                "voice_stt_prompt_unsupported provider=groq status=%s retrying_without_prompt",
                response.status_code,
            )
            retry_data = {k: v for k, v in data.items() if k != "prompt"}
            response = _post(retry_data)
            elapsed = int((time.perf_counter() - start) * 1000)

        if not response.is_success:
            body: Any
            try:
                body = response.json()
            except Exception:
                body = response.text
            return {"ok": False, "status_code": response.status_code, "error": body, "timings": {"groq_stt_total_ms": elapsed}}
        body = response.json()
        return {"ok": True, "text": str(body.get("text") or "").strip(), "model": data["model"], "language": stt_lang, "timings": {"groq_stt_total_ms": elapsed}}

    @staticmethod
    def synthesize_orpheus_result(db: Session, *, text: str, voice: str | None = None) -> dict[str, Any]:
        start = time.perf_counter()
        config = GroqProviderService._config(db)
        selected_voice = GroqProviderService._voice(voice or config.get("tts_voice"))
        payload = {
            "model": config["tts_model"] or GROQ_DEFAULT_TTS_MODEL,
            "voice": selected_voice,
            "input": str(text or ""),
            "response_format": "wav",
        }
        headers = {"Authorization": f"Bearer {config['api_key']}", "Accept": "audio/wav", "Content-Type": "application/json"}
        with httpx.Client(timeout=45.0, verify=GroqProviderService._ssl_context()) as client:
            response = client.post(f"{config['base_url']}/v1/audio/speech", json=payload, headers=headers)
        elapsed = int((time.perf_counter() - start) * 1000)
        if not response.is_success:
            try:
                body = response.json()
            except Exception:
                body = response.text
            return {"ok": False, "status_code": response.status_code, "error": body, "voice_id": selected_voice, "model_id": payload["model"], "timings": {"groq_tts_total_ms": elapsed}}
        audio = response.content or b""
        return {"ok": True, "audio_data": audio, "audio_bytes": len(audio), "audio_mime": "audio/wav", "voice_id": selected_voice, "model_id": payload["model"], "timings": {"groq_tts_total_ms": elapsed}}
