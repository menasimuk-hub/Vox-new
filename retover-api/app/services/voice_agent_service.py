from __future__ import annotations

import base64
import html
import logging
import os
import re
import ssl
import time
from dataclasses import dataclass
from threading import Lock
from typing import Any

import certifi
import httpx
from sqlalchemy.orm import Session

from app.services.providers.openai_service import OpenAIProviderService
from app.services.provider_settings import ProviderSettingsService

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class VoiceAgentTurn:
    transcript: str
    response_text: str
    response_audio_b64: str | None = None


class VoiceAgentConfigError(ValueError):
    pass


class AzureSpeechSynthesisError(VoiceAgentConfigError):
    def __init__(self, message: str, *, error_code: str = "", error_details: str = "", cancellation_reason: str = ""):
        super().__init__(message)
        self.error_code = error_code
        self.error_details = error_details
        self.cancellation_reason = cancellation_reason


class AzureSpeechService:
    TTS_TEST_PHRASE = "Hello, this is your clinic assistant speaking."
    BROWSER_VOICE_ID = os.getenv("MORGAN_VOICE") or os.getenv("VOX_DEMO_VOICE") or "en-GB-RyanNeural"
    BROWSER_BACKUP_VOICE_ID = "en-GB-ThomasNeural"
    _speechsdk: Any = None
    _speechsdk_lock = Lock()
    _speech_config_cache: dict[tuple[str, str, str, str], Any] = {}
    _speech_config_lock = Lock()
    _synthesizer_pool: dict[tuple[str, str, str, str, str], list[Any]] = {}
    _synthesizer_pool_lock = Lock()
    _synthesizer_pool_max = 3
    _SENTENCE_RE = re.compile(r"^(.+?[.!?])(\s+|$)", re.DOTALL)
    _CLAUSE_RE = re.compile(r"^(.+?[,;:])(\s+|$)", re.DOTALL)

    @staticmethod
    def _config(db: Session) -> dict[str, Any]:
        cfg, enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="azure_speech")
        config = cfg or {}
        if not enabled:
            raise VoiceAgentConfigError("Azure Speech is not configured or enabled")
        try:
            validated = ProviderSettingsService._validate_azure_speech_config(config)
        except ValueError as e:
            raise VoiceAgentConfigError(str(e)) from e
        return validated

    @staticmethod
    def _tts_rest_url(region: str) -> str:
        return f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1"

    @staticmethod
    def _prosody_rate(speaking_rate: str | None = None) -> str:
        value = str(speaking_rate or "").strip().lower()
        if value in {"slightly_fast", "fast", "+12%"}:
            return "+8%"
        return "medium"

    @staticmethod
    def _ssml(text: str, *, voice_id: str, speaking_rate: str | None = None) -> str:
        escaped = html.escape(str(text or ""), quote=False)
        rate = AzureSpeechService._prosody_rate(speaking_rate)
        return (
            "<speak version='1.0' xml:lang='en-GB'>"
            f"<voice xml:lang='en-GB' name='{voice_id}'>"
            f"<prosody rate='{rate}' pitch='default' volume='medium'>"
            "<break time='90ms'/>"
            f"{escaped}"
            "</prosody>"
            "</voice></speak>"
        )

    @staticmethod
    def pop_speakable_chunk(buffer: str, *, final: bool = False, force: bool = False, min_words: int = 10) -> tuple[str | None, str]:
        text = str(buffer or "").strip()
        if not text:
            return None, ""

        sentence_match = AzureSpeechService._SENTENCE_RE.match(text)
        if sentence_match:
            chunk = sentence_match.group(1).strip()
            if len(chunk) >= 8:
                return chunk, text[len(sentence_match.group(0)) :].strip()

        clause_match = AzureSpeechService._CLAUSE_RE.match(text)
        if clause_match:
            chunk = clause_match.group(1).strip()
            # Avoid robotic micro-fragments like "Yes," unless flushing at the end.
            if len(chunk) >= 32:
                return chunk, text[len(clause_match.group(0)) :].strip()

        words = text.split()
        if len(words) >= min_words:
            chunk = " ".join(words[: min(12, len(words))]).strip()
            if len(chunk) >= 24:
                return chunk, text[len(chunk) :].strip()

        if len(text) >= 140:
            split_at = max(text.rfind(" ", 0, 120), 60)
            return text[:split_at].strip(), text[split_at:].strip()

        if (final or force) and len(text) >= 3:
            if len(words) <= 2 and not final:
                return None, text
            return text, ""
        return None, text

    @staticmethod
    def synthesize_demo_chunk_result(
        db: Session,
        *,
        text: str,
        voice_id: str | None = None,
        output_format: str = "browser_fast",
        speaking_rate: str | None = None,
    ) -> dict[str, Any]:
        return AzureSpeechService.synthesize_text_result(
            db,
            text=text,
            voice_id=voice_id or AzureSpeechService.BROWSER_VOICE_ID,
            output_format=output_format,
            use_ssml=True,
            speaking_rate=speaking_rate,
        )

    @staticmethod
    def _diagnostics(config: dict[str, Any], *, phrase: str | None = None) -> dict[str, Any]:
        region = str(config.get("region") or "").strip().lower()
        voice_id = str(config.get("default_voice_id") or "").strip()
        key_length = len(str(config.get("api_key") or ""))
        return {
            "region": region,
            "region_is_northeurope": region == "northeurope",
            "api_key_set": key_length > 0,
            "api_key_length": key_length,
            "default_voice_id": voice_id,
            "tts_enabled": bool(config.get("tts_enabled")),
            "stt_enabled": bool(config.get("stt_enabled")),
            "sdk_config": {
                "subscription": f"<redacted length={key_length}>",
                "region": region,
                "speech_synthesis_voice_name": voice_id,
            },
            "rest_equivalent": {
                "url": AzureSpeechService._tts_rest_url(region),
                "headers": {
                    "Ocp-Apim-Subscription-Key": f"<redacted length={key_length}>",
                    "Content-Type": "application/ssml+xml",
                    "X-Microsoft-OutputFormat": "riff-8khz-8bit-mono-mulaw",
                    "User-Agent": "retover-voice-agent",
                },
                "body": AzureSpeechService._ssml(phrase or AzureSpeechService.TTS_TEST_PHRASE, voice_id=voice_id),
            },
        }

    @staticmethod
    def diagnostics(db: Session) -> dict[str, Any]:
        config = AzureSpeechService._config(db)
        return AzureSpeechService._diagnostics(config, phrase=AzureSpeechService.TTS_TEST_PHRASE)

    @staticmethod
    def _speechsdk_module():
        if AzureSpeechService._speechsdk is None:
            with AzureSpeechService._speechsdk_lock:
                if AzureSpeechService._speechsdk is None:
                    try:
                        import azure.cognitiveservices.speech as speechsdk
                    except ImportError as e:
                        raise VoiceAgentConfigError("Azure Speech SDK is not installed") from e
                    AzureSpeechService._speechsdk = speechsdk
        return AzureSpeechService._speechsdk

    @staticmethod
    def _speech_config(config: dict[str, Any], *, voice_id: str | None = None, output_format: str = "telephony"):
        speechsdk = AzureSpeechService._speechsdk_module()
        selected_voice = voice_id or config["default_voice_id"]
        if output_format == "browser_fast":
            selected_format = speechsdk.SpeechSynthesisOutputFormat.Audio24Khz160KBitRateMonoMp3
        elif output_format == "browser":
            selected_format = speechsdk.SpeechSynthesisOutputFormat.Riff24Khz16BitMonoPcm
        else:
            selected_format = speechsdk.SpeechSynthesisOutputFormat.Riff8Khz8BitMonoMULaw
        cache_key = (config["api_key"], config["region"], selected_voice, output_format)
        with AzureSpeechService._speech_config_lock:
            cached = AzureSpeechService._speech_config_cache.get(cache_key)
            if cached is not None:
                return speechsdk, cached
        speech_config = speechsdk.SpeechConfig(subscription=config["api_key"], region=config["region"])
        speech_config.speech_synthesis_voice_name = selected_voice
        speech_config.set_speech_synthesis_output_format(selected_format)
        with AzureSpeechService._speech_config_lock:
            AzureSpeechService._speech_config_cache[cache_key] = speech_config
        return speechsdk, speech_config

    @staticmethod
    def _synthesizer_key(config: dict[str, Any], *, voice_id: str, output_format: str, speaking_rate: str | None = None) -> tuple[str, str, str, str, str]:
        return (
            config["api_key"],
            config["region"],
            voice_id,
            output_format,
            AzureSpeechService._prosody_rate(speaking_rate),
        )

    @staticmethod
    def _borrow_synthesizer(config: dict[str, Any], *, voice_id: str, output_format: str, speaking_rate: str | None = None):
        speechsdk, speech_config = AzureSpeechService._speech_config(config, voice_id=voice_id, output_format=output_format)
        key = AzureSpeechService._synthesizer_key(config, voice_id=voice_id, output_format=output_format, speaking_rate=speaking_rate)
        with AzureSpeechService._synthesizer_pool_lock:
            pool = AzureSpeechService._synthesizer_pool.get(key) or []
            if pool:
                return speechsdk, pool.pop(), key, True
        return speechsdk, speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=None), key, False

    @staticmethod
    def _return_synthesizer(key: tuple[str, str, str, str, str], synthesizer: Any) -> None:
        if synthesizer is None:
            return
        with AzureSpeechService._synthesizer_pool_lock:
            pool = AzureSpeechService._synthesizer_pool.setdefault(key, [])
            if len(pool) < AzureSpeechService._synthesizer_pool_max:
                pool.append(synthesizer)

    @staticmethod
    def _latency_property(speechsdk: Any, result: Any, name: str) -> int | None:
        prop_id = getattr(getattr(speechsdk, "PropertyId", None), name, None)
        props = getattr(result, "properties", None)
        if prop_id is None or props is None:
            return None
        try:
            raw = props.get_property(prop_id)
            return int(raw) if raw not in (None, "") else None
        except Exception:
            return None

    @staticmethod
    def _cancellation_payload(result: Any) -> dict[str, str]:
        cancellation = getattr(result, "cancellation_details", None)
        return {
            "cancellation_reason": str(getattr(cancellation, "reason", "") or ""),
            "error_code": str(getattr(cancellation, "error_code", "") or ""),
            "error_details": str(getattr(cancellation, "error_details", "") or ""),
        }

    @staticmethod
    def synthesize_text_result(
        db: Session,
        *,
        text: str,
        voice_id: str | None = None,
        output_format: str = "telephony",
        use_ssml: bool = True,
        speaking_rate: str | None = None,
    ) -> dict[str, Any]:
        total_start = time.perf_counter()
        config_start = time.perf_counter()
        config = AzureSpeechService._config(db)
        config_ms = int((time.perf_counter() - config_start) * 1000)
        if not config["tts_enabled"]:
            raise VoiceAgentConfigError("Azure Speech TTS is disabled")
        selected_voice = voice_id or config["default_voice_id"]
        diagnostics = AzureSpeechService._diagnostics({**config, "default_voice_id": selected_voice}, phrase=text)
        diagnostics["output_format"] = output_format
        diagnostics["ssml_enabled"] = bool(use_ssml)
        diagnostics["speaking_rate"] = AzureSpeechService._prosody_rate(speaking_rate)
        if output_format == "browser_fast":
            diagnostics["rest_equivalent"]["headers"]["X-Microsoft-OutputFormat"] = "audio-24khz-160kbitrate-mono-mp3"
        elif output_format == "browser":
            diagnostics["rest_equivalent"]["headers"]["X-Microsoft-OutputFormat"] = "riff-24khz-16bit-mono-pcm"
        logger.info(
            "Azure Speech TTS request: region=%s key_length=%s voice=%s output_format=%s ssml=%s sdk_config=%s rest_url=%s",
            diagnostics["region"],
            diagnostics["api_key_length"],
            diagnostics["default_voice_id"],
            output_format,
            use_ssml,
            diagnostics["sdk_config"],
            diagnostics["rest_equivalent"]["url"],
        )
        speech_config_start = time.perf_counter()
        speechsdk, synthesizer, synthesizer_key, reused_synthesizer = AzureSpeechService._borrow_synthesizer(
            config,
            voice_id=selected_voice,
            output_format=output_format,
            speaking_rate=speaking_rate,
        )
        speech_config_ms = int((time.perf_counter() - speech_config_start) * 1000)
        synthesis_start = time.perf_counter()
        try:
            result = (
                synthesizer.speak_ssml_async(AzureSpeechService._ssml(text, voice_id=selected_voice, speaking_rate=speaking_rate)).get()
                if use_ssml
                else synthesizer.speak_text_async(text).get()
            )
        finally:
            AzureSpeechService._return_synthesizer(synthesizer_key, synthesizer)
        synthesis_ms = int((time.perf_counter() - synthesis_start) * 1000)
        total_ms = int((time.perf_counter() - total_start) * 1000)
        first_byte_ms = AzureSpeechService._latency_property(speechsdk, result, "SpeechServiceResponse_SynthesisFirstByteLatencyMs")
        finish_latency_ms = AzureSpeechService._latency_property(speechsdk, result, "SpeechServiceResponse_SynthesisFinishLatencyMs")
        if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
            audio_data = bytes(result.audio_data or b"")
            timings = {
                "azure_config_ms": config_ms,
                "azure_speech_config_ms": speech_config_ms,
                "azure_reused_synthesizer": int(bool(reused_synthesizer)),
                "azure_first_byte_ms": first_byte_ms if first_byte_ms is not None else synthesis_ms,
                "azure_chunk_finish_ms": finish_latency_ms if finish_latency_ms is not None else synthesis_ms,
                "azure_synthesis_finish_ms": synthesis_ms,
                "azure_provider_total_ms": total_ms,
            }
            logger.info("azure_tts_timings", extra={**timings, "audio_bytes": len(audio_data), "output_format": output_format})
            return {
                "ok": True,
                "audio_data": audio_data,
                "audio_bytes": len(audio_data),
                "diagnostics": diagnostics,
                "timings": timings,
            }

        cancellation = AzureSpeechService._cancellation_payload(result)
        timings = {
            "azure_config_ms": config_ms,
            "azure_speech_config_ms": speech_config_ms,
            "azure_reused_synthesizer": int(bool(reused_synthesizer)),
            "azure_first_byte_ms": first_byte_ms if first_byte_ms is not None else synthesis_ms,
            "azure_chunk_finish_ms": finish_latency_ms if finish_latency_ms is not None else synthesis_ms,
            "azure_synthesis_finish_ms": synthesis_ms,
            "azure_provider_total_ms": total_ms,
        }
        logger.error("Azure Speech TTS canceled/failed: cancellation=%s diagnostics=%s timings=%s", cancellation, diagnostics, timings)
        return {
            "ok": False,
            "audio_data": b"",
            "audio_bytes": 0,
            **cancellation,
            "diagnostics": diagnostics,
            "timings": timings,
        }

    @staticmethod
    def synthesize_text(db: Session, *, text: str) -> bytes:
        result = AzureSpeechService.synthesize_text_result(db, text=text)
        if result["ok"]:
            return bytes(result["audio_data"] or b"")
        message = "Azure Speech TTS failed"
        if result.get("error_code") or result.get("error_details"):
            message = f"{message}: {result.get('error_code') or 'unknown'} {result.get('error_details') or ''}".strip()
        raise AzureSpeechSynthesisError(
            message,
            error_code=str(result.get("error_code") or ""),
            error_details=str(result.get("error_details") or ""),
            cancellation_reason=str(result.get("cancellation_reason") or ""),
        )

    @staticmethod
    def test_tts(db: Session, *, text: str | None = None) -> dict[str, Any]:
        phrase = text or AzureSpeechService.TTS_TEST_PHRASE
        config = AzureSpeechService._config(db)
        diagnostics = AzureSpeechService._diagnostics(config, phrase=phrase)
        try:
            result = AzureSpeechService.synthesize_text_result(db, text=phrase)
        except Exception as e:
            logger.exception("Azure Speech TTS smoke test failed: diagnostics=%s", diagnostics)
            return {
                "ok": False,
                "phrase": phrase,
                "error": str(e),
                "diagnostics": diagnostics,
                "persisted_audio": False,
            }
        if not result["ok"]:
            return {
                "ok": False,
                "phrase": phrase,
                "error_code": result.get("error_code") or "",
                "error_details": result.get("error_details") or "",
                "cancellation_reason": result.get("cancellation_reason") or "",
                "diagnostics": result["diagnostics"],
                "persisted_audio": False,
            }
        return {
            "ok": True,
            "phrase": phrase,
            "audio_bytes": result["audio_bytes"],
            "diagnostics": result["diagnostics"],
            "persisted_audio": False,
        }

    @staticmethod
    def transcribe_audio(db: Session, *, audio: bytes, content_type: str = "audio/wav") -> str:
        config = AzureSpeechService._config(db)
        if not config["stt_enabled"]:
            return ""
        url = f"https://{config['region']}.stt.speech.microsoft.com/speech/recognition/conversation/cognitiveservices/v1"
        headers = {"Ocp-Apim-Subscription-Key": config["api_key"], "Content-Type": content_type, "Accept": "application/json"}
        with httpx.Client(timeout=20.0) as client:
            response = client.post(url, params={"language": "en-GB"}, content=audio, headers=headers)
        response.raise_for_status()
        payload = response.json()
        return str(payload.get("DisplayText") or payload.get("text") or "").strip()


class OpenAICallReasoningService:
    @staticmethod
    def _verify_path() -> str:
        return certifi.where()

    @staticmethod
    def _ssl_context() -> ssl.SSLContext | str:
        try:
            import truststore

            return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        except Exception:
            return OpenAICallReasoningService._verify_path()

    @staticmethod
    def _config(db: Session) -> dict[str, Any]:
        cfg, enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="openai")
        config = cfg or {}
        if not enabled:
            raise VoiceAgentConfigError("OpenAI is not configured or enabled")
        try:
            config = ProviderSettingsService._validate_openai_config(config)
        except ValueError as e:
            raise VoiceAgentConfigError(str(e)) from e
        return {
            **config,
            "api_key": str(config.get("api_key") or "").strip(),
            "model": str(config.get("default_model") or "").strip(),
            "default_model": str(config.get("default_model") or "").strip(),
            "realtime_model": str(config.get("realtime_model") or "").strip(),
            "base_url": OpenAIProviderService._normalize_base_url(config.get("base_url")),
        }

    @staticmethod
    def generate_reply(db: Session, *, transcript: str, system_prompt: str | None = None) -> str:
        config = OpenAICallReasoningService._config(db)
        prompt = system_prompt or (
            "You are VOXBULK.COM's polite British dental recovery voice agent. "
            "Keep replies concise, helpful, and suitable for a phone call."
        )
        model = OpenAIProviderService._select_text_model(config, config["model"])
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": transcript},
            ],
            "temperature": float(config["temperature"]),
            "max_tokens": int(config["max_output_tokens"]),
        }
        url = f"{config['base_url']}/v1/chat/completions"
        headers = {"Authorization": f"Bearer {config['api_key']}", "Content-Type": "application/json"}
        with httpx.Client(timeout=30.0, verify=OpenAICallReasoningService._ssl_context()) as client:
            response = client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        body = response.json()
        return str(((body.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()


class VoiceAgentService:
    @staticmethod
    def handle_transcript_turn(db: Session, *, transcript: str, system_prompt: str | None = None) -> VoiceAgentTurn:
        response_text = OpenAICallReasoningService.generate_reply(db, transcript=transcript, system_prompt=system_prompt)
        audio_b64 = None
        try:
            audio = AzureSpeechService.synthesize_text(db, text=response_text)
            audio_b64 = base64.b64encode(audio).decode("ascii")
        except Exception:
            # Keep the conversation state even if audio synthesis fails; the call log records the text.
            audio_b64 = None
        return VoiceAgentTurn(transcript=transcript, response_text=response_text, response_audio_b64=audio_b64)
