from __future__ import annotations

import logging
import ssl
import time
from pathlib import Path
from typing import Any

import certifi
import httpx
from sqlalchemy.orm import Session

from app.services.provider_settings import ProviderSettingsService

logger = logging.getLogger(__name__)

# Full large-v3 is more accurate on dialect / noisy WhatsApp audio than turbo.
DEEPINFRA_DEFAULT_MODEL = "openai/whisper-large-v3"
DEEPINFRA_DEFAULT_BASE_URL = "https://api.deepinfra.com/v1/inference/openai/whisper-large-v3"
# Prefer this for WA survey voice notes unless Admin config sets a non-turbo model.
WA_SURVEY_WHISPER_MODEL = "openai/whisper-large-v3"


class DeepInfraProviderService:
    @staticmethod
    def _ssl_context() -> ssl.SSLContext | str:
        try:
            import truststore

            return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        except Exception:
            return certifi.where()

    @staticmethod
    def _resolve_base_url(raw: Any, model_name: str) -> str:
        base = str(raw or "").strip().rstrip("/")
        if base:
            return base
        model = str(model_name or DEEPINFRA_DEFAULT_MODEL).strip().strip("/")
        return f"https://api.deepinfra.com/v1/inference/{model}"

    @staticmethod
    def _config(db: Session) -> dict[str, Any]:
        cfg, enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="deepinfra")
        config = cfg or {}
        api_key = str(config.get("api_key") or "").strip()
        if not enabled:
            raise ValueError("DeepInfra integration is disabled")
        if not api_key:
            raise ValueError("DeepInfra API key is required")
        model_name = str(config.get("model_name") or DEEPINFRA_DEFAULT_MODEL).strip()
        return {
            "api_key": api_key,
            "integration_name": str(config.get("integration_name") or "DeepInfra API").strip(),
            "model_name": model_name,
            "base_url": DeepInfraProviderService._resolve_base_url(config.get("base_url"), model_name),
        }

    @staticmethod
    def is_configured(db: Session) -> bool:
        try:
            DeepInfraProviderService._config(db)
            return True
        except Exception:
            return False

    @staticmethod
    def resolve_wa_survey_model(db: Session) -> str:
        """WA surveys use full large-v3; keep Admin turbo only when explicitly configured."""
        try:
            config = DeepInfraProviderService._config(db)
            configured = str(config.get("model_name") or "").strip()
        except Exception:
            return WA_SURVEY_WHISPER_MODEL
        if not configured or "turbo" in configured.lower():
            return WA_SURVEY_WHISPER_MODEL
        return configured

    @staticmethod
    def transcribe_audio_file(
        db: Session,
        *,
        audio_path: Path,
        language: str | None = None,
        prompt: str | None = None,
        model_name: str | None = None,
    ) -> dict[str, Any]:
        start = time.perf_counter()
        config = DeepInfraProviderService._config(db)
        override = str(model_name or "").strip()
        if override:
            config = {
                **config,
                "model_name": override,
                "base_url": DeepInfraProviderService._resolve_base_url(None, override),
            }
        headers = {"Authorization": f"Bearer {config['api_key']}"}

        mime = "audio/wav"
        suffix = audio_path.suffix.lower()
        if suffix in {".ogg", ".oga"}:
            mime = "audio/ogg"
        elif suffix == ".mp3":
            mime = "audio/mpeg"
        elif suffix in {".m4a", ".mp4"}:
            mime = "audio/mp4"

        def _post(data: dict[str, str]) -> httpx.Response:
            with audio_path.open("rb") as handle:
                files = {"audio": (audio_path.name, handle, mime)}
                with httpx.Client(timeout=120.0, verify=DeepInfraProviderService._ssl_context()) as client:
                    return client.post(config["base_url"], headers=headers, data=data or None, files=files)

        data: dict[str, str] = {}
        if language:
            data["language"] = str(language).strip().lower()
        if prompt:
            data["prompt"] = str(prompt).strip()

        response = _post(data)
        if not response.is_success and prompt:
            logger.warning(
                "voice_stt_prompt_unsupported provider=deepinfra status=%s retrying_without_prompt",
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
            raise RuntimeError(f"DeepInfra STT failed ({response.status_code}): {str(body)[:500]}")

        payload = response.json()
        text = str(payload.get("text") or "").strip()
        if not text and isinstance(payload.get("segments"), list):
            text = " ".join(str(seg.get("text") or "").strip() for seg in payload["segments"] if isinstance(seg, dict)).strip()

        return {
            "text": text,
            "detected_language": payload.get("language"),
            "transcription_model": config["model_name"],
            "transcription_duration_ms": elapsed,
        }

    @staticmethod
    def test_connection(db: Session) -> dict[str, Any]:
        start = time.perf_counter()
        config = DeepInfraProviderService._config(db)
        headers = {"Authorization": f"Bearer {config['api_key']}"}

        # Minimal valid WAV (silence) for a real inference ping.
        wav_bytes = (
            b"RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00"
            b"\x80>\x00\x00\x00}\x00\x00\x02\x00\x10\x00data\x00\x00\x00\x00"
        )
        files = {"audio": ("deepinfra-test.wav", wav_bytes, "audio/wav")}

        with httpx.Client(timeout=60.0, verify=DeepInfraProviderService._ssl_context()) as client:
            response = client.post(config["base_url"], headers=headers, files=files)

        elapsed = int((time.perf_counter() - start) * 1000)
        ok = response.is_success
        body: Any
        try:
            body = response.json()
        except Exception:
            body = response.text

        result = {
            "ok": ok,
            "connection_status": "connected" if ok else "failed",
            "model_reached": ok,
            "api_key_valid": response.status_code != 401,
            "response_time_ms": elapsed,
            "model_name": config["model_name"],
            "base_url": config["base_url"],
            "last_tested_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "last_test_status": "success" if ok else "failed",
        }
        if not ok:
            result["error"] = str(body)[:500]
        return result
