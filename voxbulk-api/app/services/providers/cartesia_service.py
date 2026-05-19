from __future__ import annotations

import base64
import json
import os
import ssl
import time
import uuid
import wave
from io import BytesIO
from typing import Any

import certifi
import httpx
from websockets.sync.client import connect
from sqlalchemy.orm import Session

from app.services.provider_settings import ProviderSettingsService

CARTESIA_DEFAULT_BASE_URL = "https://api.cartesia.ai"
CARTESIA_DEFAULT_MODEL = "sonic-2"
CARTESIA_DEFAULT_VOICE_ID = "a0e99841-438c-4a64-b679-ae501e7d6091"
CARTESIA_VERSION = "2026-03-01"
CARTESIA_REALTIME_ENCODING = "pcm_s16le"
CARTESIA_REALTIME_CONTAINER = "raw"


class CartesiaProviderService:
    @staticmethod
    def _ssl_context() -> ssl.SSLContext | str:
        try:
            import truststore

            return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        except Exception:
            return certifi.where()

    @staticmethod
    def _config(db: Session) -> dict[str, Any]:
        cfg, enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="cartesia")
        config = cfg or {}
        api_key = str(config.get("api_key") or os.getenv("CARTESIA_API_KEY") or "").strip()
        if not enabled and not api_key:
            raise ValueError("Cartesia is not configured or enabled")
        if not api_key:
            raise ValueError("Cartesia API key is required")
        return {
            "api_key": api_key,
            "base_url": str(config.get("base_url") or os.getenv("CARTESIA_BASE_URL") or CARTESIA_DEFAULT_BASE_URL).strip().rstrip("/"),
            "ws_url": str(config.get("ws_url") or os.getenv("CARTESIA_WS_URL") or "wss://api.cartesia.ai").strip().rstrip("/"),
            "model_id": str(config.get("model_id") or os.getenv("CARTESIA_MODEL_ID") or CARTESIA_DEFAULT_MODEL).strip(),
            "voice_id": str(config.get("voice_id") or os.getenv("CARTESIA_VOICE_ID") or CARTESIA_DEFAULT_VOICE_ID).strip(),
            "sample_rate": int(config.get("sample_rate") or os.getenv("CARTESIA_SAMPLE_RATE") or 44100),
            "encoding": str(config.get("encoding") or os.getenv("CARTESIA_ENCODING") or "mp3").strip(),
            "container": str(config.get("container") or os.getenv("CARTESIA_CONTAINER") or "mp3").strip(),
        }

    @staticmethod
    def diagnostics(db: Session) -> dict[str, Any]:
        config = CartesiaProviderService._config(db)
        return {k: v for k, v in config.items() if k != "api_key"} | {"api_key_set": bool(config["api_key"]), "api_key_length": len(config["api_key"])}

    @staticmethod
    def _headers(config: dict[str, Any]) -> dict[str, str]:
        return {
            "X-API-Key": config["api_key"],
            "Cartesia-Version": CARTESIA_VERSION,
            "Content-Type": "application/json",
        }

    @staticmethod
    def synthesize_text_result(db: Session, *, text: str, voice_id: str | None = None) -> dict[str, Any]:
        start = time.perf_counter()
        config = CartesiaProviderService._config(db)
        selected_voice = str(voice_id or config["voice_id"]).strip()
        payload = {
            "model_id": config["model_id"],
            "transcript": str(text or ""),
            "voice": {"mode": "id", "id": selected_voice},
            "output_format": {
                "container": config["container"],
                "encoding": config["encoding"],
                "sample_rate": config["sample_rate"],
            },
        }
        with httpx.Client(timeout=45.0, verify=CartesiaProviderService._ssl_context()) as client:
            response = client.post(f"{config['base_url']}/tts/bytes", json=payload, headers=CartesiaProviderService._headers(config))
        elapsed = int((time.perf_counter() - start) * 1000)
        if not response.is_success:
            try:
                body: Any = response.json()
            except Exception:
                body = response.text
            return {"ok": False, "status_code": response.status_code, "error": body, "voice_id": selected_voice, "model_id": config["model_id"], "timings": {"cartesia_tts_total_ms": elapsed}}
        audio = response.content or b""
        mime = "audio/mpeg" if config["container"] == "mp3" else f"audio/{config['container']}"
        return {"ok": True, "audio_data": audio, "audio_bytes": len(audio), "audio_mime": mime, "voice_id": selected_voice, "model_id": config["model_id"], "timings": {"cartesia_tts_total_ms": elapsed}}

    @staticmethod
    def _wav_bytes_from_pcm(pcm: bytes, *, sample_rate: int) -> bytes:
        out = BytesIO()
        with wave.open(out, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            wav.writeframes(pcm)
        return out.getvalue()

    @staticmethod
    def realtime_session(db: Session, *, voice_id: str | None = None) -> "CartesiaRealtimeSession":
        config = CartesiaProviderService._config(db)
        return CartesiaRealtimeSession(config, voice_id=voice_id)

    @staticmethod
    def realtime_session_from_config(config: dict[str, Any], *, voice_id: str | None = None) -> "CartesiaRealtimeSession":
        return CartesiaRealtimeSession(config, voice_id=voice_id)

    @staticmethod
    def test_connection(db: Session) -> dict[str, Any]:
        result = CartesiaProviderService.synthesize_text_result(db, text="Connection test.")
        if not result.get("ok"):
            return {**result, **CartesiaProviderService.diagnostics(db)}
        return {"ok": True, "audio_bytes": result.get("audio_bytes"), **CartesiaProviderService.diagnostics(db)}


class CartesiaRealtimeSession:
    def __init__(self, config: dict[str, Any], *, voice_id: str | None = None):
        self.config = config
        self.voice_id = str(voice_id or config["voice_id"]).strip()
        self.ws = None
        self._last_ping = 0.0

    def __enter__(self) -> "CartesiaRealtimeSession":
        url = f"{self.config['ws_url']}/tts/websocket?cartesia_version={CARTESIA_VERSION}"
        self.ws = connect(
            url,
            additional_headers={
                "X-API-Key": self.config["api_key"],
                "Cartesia-Version": CARTESIA_VERSION,
            },
            open_timeout=10,
            close_timeout=2,
        )
        self._last_ping = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            self.ws.close()
        except Exception:
            pass

    def keepalive_ping(self) -> None:
        if self.ws is None:
            return
        if time.perf_counter() - self._last_ping < 10:
            return
        try:
            self.ws.ping()
            self._last_ping = time.perf_counter()
        except Exception:
            pass

    def iter_synthesize_chunks(self, text: str):
        if self.ws is None:
            raise RuntimeError("Cartesia realtime session is not open")
        self.keepalive_ping()
        started = time.perf_counter()
        context_id = str(uuid.uuid4())
        payload = {
            "model_id": self.config["model_id"],
            "transcript": str(text or ""),
            "voice": {"mode": "id", "id": self.voice_id},
            "language": "en",
            "context_id": context_id,
            "output_format": {
                "container": CARTESIA_REALTIME_CONTAINER,
                "encoding": CARTESIA_REALTIME_ENCODING,
                "sample_rate": int(self.config["sample_rate"]),
            },
            "continue": False,
            "max_buffer_delay_ms": 0,
        }
        self.ws.send(json.dumps(payload))
        first_chunk_ms: int | None = None
        while True:
            raw = self.ws.recv(timeout=30)
            msg = json.loads(raw)
            if msg.get("context_id") != context_id:
                continue
            if msg.get("type") == "error":
                yield {
                    "ok": False,
                    "status_code": msg.get("status_code"),
                    "error": msg,
                    "voice_id": self.voice_id,
                    "model_id": self.config["model_id"],
                    "timings": {"cartesia_ws_total_ms": int((time.perf_counter() - started) * 1000)},
                }
                return
            if msg.get("type") == "chunk" and msg.get("data"):
                if first_chunk_ms is None:
                    first_chunk_ms = int((time.perf_counter() - started) * 1000)
                pcm = base64.b64decode(str(msg.get("data") or ""))
                audio = CartesiaProviderService._wav_bytes_from_pcm(pcm, sample_rate=int(self.config["sample_rate"]))
                yield {
                    "ok": True,
                    "audio_data": audio,
                    "audio_bytes": len(audio),
                    "audio_mime": "audio/wav",
                    "voice_id": self.voice_id,
                    "model_id": self.config["model_id"],
                    "context_id": context_id,
                    "done": bool(msg.get("done")),
                    "timings": {
                        "cartesia_ws_first_chunk_ms": first_chunk_ms,
                        "cartesia_ws_chunk_step_ms": msg.get("step_time"),
                        "cartesia_ws_total_ms": int((time.perf_counter() - started) * 1000),
                    },
                }
                if msg.get("done"):
                    break
            elif msg.get("type") in {"done", "flush_done"} or msg.get("done"):
                break

    def synthesize_chunks(self, text: str) -> list[dict[str, Any]]:
        chunks: list[dict[str, Any]] = []
        for chunk in self.iter_synthesize_chunks(text):
            chunks.append(chunk)
        return chunks
