from __future__ import annotations

import json
import os
import ssl
import time
from typing import Any

import certifi
import httpx
from sqlalchemy.orm import Session

from app.services.provider_settings import ProviderSettingsService

DEEPGRAM_DEFAULT_BASE_URL = "https://api.deepgram.com"
DEEPGRAM_DEFAULT_WS_URL = "wss://api.deepgram.com"
DEEPGRAM_DEFAULT_MODEL = "nova-3"
DEEPGRAM_DEFAULT_LANGUAGE = "en"


class DeepgramProviderService:
    @staticmethod
    def is_configured(db: Session) -> bool:
        try:
            DeepgramProviderService._config(db)
            return True
        except Exception:
            return False

    @staticmethod
    def _ssl_context() -> ssl.SSLContext | str:
        try:
            import truststore

            return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        except Exception:
            return certifi.where()

    @staticmethod
    def _config(db: Session) -> dict[str, Any]:
        cfg, enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="deepgram")
        config = cfg or {}
        api_key = str(config.get("api_key") or os.getenv("DEEPGRAM_API_KEY") or "").strip()
        if not enabled and not api_key:
            raise ValueError("Deepgram is not configured or enabled")
        if not api_key:
            raise ValueError("Deepgram API key is required")
        return {
            "api_key": api_key,
            "base_url": str(config.get("base_url") or os.getenv("DEEPGRAM_BASE_URL") or DEEPGRAM_DEFAULT_BASE_URL).strip().rstrip("/"),
            "ws_url": str(config.get("ws_url") or os.getenv("DEEPGRAM_WS_URL") or DEEPGRAM_DEFAULT_WS_URL).strip().rstrip("/"),
            "model": str(config.get("model") or os.getenv("DEEPGRAM_MODEL") or DEEPGRAM_DEFAULT_MODEL).strip(),
            "language": str(config.get("language") or os.getenv("DEEPGRAM_LANGUAGE") or DEEPGRAM_DEFAULT_LANGUAGE).strip(),
            "endpointing": int(config.get("endpointing") or os.getenv("DEEPGRAM_ENDPOINTING") or 250),
            "interim_results": ProviderSettingsService._bool_config(config.get("interim_results"), default=True),
        }

    @staticmethod
    def listen_params(config: dict[str, Any]) -> dict[str, str]:
        return {
            "model": config["model"],
            "language": config["language"],
            "interim_results": "true" if config["interim_results"] else "false",
            "endpointing": str(config["endpointing"]),
            "smart_format": "true",
            "punctuate": "true",
        }

    @staticmethod
    def websocket_url(db: Session) -> tuple[str, dict[str, str]]:
        config = DeepgramProviderService._config(db)
        params = DeepgramProviderService.listen_params(config)
        query = "&".join(f"{k}={v}" for k, v in params.items())
        return f"{config['ws_url']}/v1/listen?{query}", {"Authorization": f"Token {config['api_key']}"}

    @staticmethod
    def transcribe_audio_result(
        db: Session,
        *,
        audio: bytes,
        filename: str = "audio.webm",
        content_type: str = "audio/webm",
        language: str | None = None,
    ) -> dict[str, Any]:
        start = time.perf_counter()
        config = DeepgramProviderService._config(db)
        auto_detect = str(language or "").strip().lower() in {"auto", "detect", "multi"}
        stt_language = str(language or config["language"] or DEEPGRAM_DEFAULT_LANGUAGE).strip()
        params: dict[str, str] = {
            "model": config["model"],
            "smart_format": "true",
            "punctuate": "true",
        }
        if auto_detect:
            params["detect_language"] = "true"
            stt_language = "auto"
        else:
            params["language"] = stt_language
        headers = {"Authorization": f"Token {config['api_key']}", "Content-Type": content_type}
        with httpx.Client(timeout=45.0, verify=DeepgramProviderService._ssl_context()) as client:
            response = client.post(f"{config['base_url']}/v1/listen", params=params, content=audio, headers=headers)
        elapsed = int((time.perf_counter() - start) * 1000)
        try:
            body = response.json()
        except Exception:
            body = {"raw_text": response.text}
        if not response.is_success:
            return {"ok": False, "status_code": response.status_code, "error": body, "timings": {"deepgram_stt_total_ms": elapsed}}
        text = ""
        try:
            text = str((((body.get("results") or {}).get("channels") or [{}])[0].get("alternatives") or [{}])[0].get("transcript") or "").strip()
        except Exception:
            text = ""
        return {
            "ok": True,
            "provider": "deepgram",
            "text": text,
            "language": stt_language,
            "model": config["model"],
            "raw": body,
            "timings": {"deepgram_stt_total_ms": elapsed},
        }

    @staticmethod
    def diagnostics(db: Session) -> dict[str, Any]:
        config = DeepgramProviderService._config(db)
        return {k: v for k, v in config.items() if k != "api_key"} | {"api_key_set": bool(config["api_key"]), "api_key_length": len(config["api_key"])}

    @staticmethod
    def test_connection(db: Session) -> dict[str, Any]:
        config = DeepgramProviderService._config(db)
        headers = {"Authorization": f"Token {config['api_key']}"}
        with httpx.Client(timeout=20.0, verify=DeepgramProviderService._ssl_context()) as client:
            response = client.get(f"{config['base_url']}/v1/projects", headers=headers)
        body: Any
        try:
            body = response.json()
        except Exception:
            body = response.text
        if not response.is_success:
            return {"ok": False, "status_code": response.status_code, "payload": body, **DeepgramProviderService.diagnostics(db)}
        return {"ok": True, "status_code": response.status_code, **DeepgramProviderService.diagnostics(db)}


def deepgram_transcript_from_ws_message(raw: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(raw)
    except Exception:
        return None
    channel = (payload.get("channel") or {})
    alt = ((channel.get("alternatives") or [{}])[0]) if isinstance(channel, dict) else {}
    transcript = str(alt.get("transcript") or "").strip()
    if not transcript:
        return None
    return {
        "type": "transcript",
        "text": transcript,
        "confidence": alt.get("confidence"),
        "is_final": bool(payload.get("is_final")),
        "speech_final": bool(payload.get("speech_final")),
    }
