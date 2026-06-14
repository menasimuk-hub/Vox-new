from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.encryption import get_encryptor
from app.models.provider_config import ProviderConfig


class ProviderUnknown(ValueError):
    pass


class ProviderSettingsService:
    PROVIDERS = {
        "dentally",
        "vapi",
        "deepseek",
        "groq",
        "elevenlabs",
        "deepgram",
        "deepinfra",
        "cartesia",
        "gocardless",
        "stripe",
        "airwallex",
        "telnyx",
        "azure_speech",
        "openai",
        "google",
        "apple",
        "linkedin",
        "zoom",
        "calendly",
        "cronofy",
        "hubspot",
        "apollo",
        "resend",
    }

    # Keys we expect for "configured" status (per provider). Secrets are stored encrypted and never returned.
    REQUIRED_FIELDS: dict[str, set[str]] = {
        "dentally": {"base_url", "api_key"},
        "vapi": {"public_key", "assistant_id"},
        "deepseek": {"api_key", "base_url", "model"},
        "groq": {"api_key", "base_url", "stt_model", "tts_model", "tts_voice"},
        "elevenlabs": {"api_key", "default_voice_id"},
        "deepgram": {"api_key", "base_url", "ws_url", "model"},
        "deepinfra": {"api_key", "base_url", "model_name"},
        "cartesia": {"api_key", "base_url", "model_id", "voice_id"},
        "gocardless": {"access_token", "webhook_secret"},
        "stripe": {"secret_key", "publishable_key"},
        "airwallex": {"client_id", "api_key"},
        "telnyx": {"api_key", "connection_id", "default_outbound_number", "fallback_caller_id", "media_stream_url"},
        "azure_speech": {"api_key", "region", "default_voice_id"},
        "openai": {"api_key", "default_model", "realtime_model", "temperature", "max_output_tokens"},
        # Social OAuth providers. These settings are consumed by the FastAPI OAuth start/callback flow.
        "google": {"client_id", "client_secret", "redirect_uri"},
        "apple": {"client_id", "redirect_uri", "team_id", "key_id", "private_key"},
        "linkedin": {"client_id", "client_secret", "redirect_uri"},
        "zoom": {"account_id", "client_id", "client_secret"},
        "calendly": {"client_id", "client_secret", "redirect_uri"},
        "cronofy": {"client_id", "client_secret", "redirect_uri"},
        "hubspot": set(),
        "apollo": {"api_key"},
        "resend": {"api_key"},
    }

    SECRET_KEYS: dict[str, set[str]] = {
        "dentally": {"api_key"},
        "vapi": {"api_key"},
        "deepseek": {"api_key"},
        "groq": {"api_key"},
        "elevenlabs": {"api_key"},
        "deepgram": {"api_key"},
        "deepinfra": {"api_key"},
        "cartesia": {"api_key"},
        "gocardless": {"access_token", "webhook_secret"},
        "stripe": {"secret_key", "webhook_secret"},
        "airwallex": {"api_key", "webhook_secret"},
        "telnyx": {"api_key"},
        "azure_speech": {"api_key"},
        "openai": {"api_key"},
        "google": {"client_secret"},
        "apple": {"private_key"},
        "linkedin": {"client_secret"},
        "zoom": {"client_secret"},
        "calendly": {"client_secret"},
        "cronofy": {"client_secret"},
        "hubspot": {"client_secret"},
        "apollo": {"api_key"},
        "resend": {"api_key"},
    }

    @staticmethod
    def _assert_provider(provider: str) -> None:
        provider = provider.lower()
        if provider not in ProviderSettingsService.PROVIDERS:
            raise ProviderUnknown("Unknown provider")

    @staticmethod
    def upsert_platform_config(db: Session, *, provider: str, is_enabled: bool, config: dict[str, Any]) -> ProviderConfig:
        provider = provider.lower()
        ProviderSettingsService._assert_provider(provider)
        enc = get_encryptor()
        existing = ProviderSettingsService.get_platform_config(db, provider=provider)
        if existing is not None:
            try:
                current = json.loads(enc.decrypt_str(existing.encrypted_json))
            except Exception:
                current = {}
            if isinstance(current, dict):
                merged = {**current, **config}
                for secret_key in ProviderSettingsService._secret_keys(provider):
                    incoming = config.get(secret_key)
                    if (incoming is None or (isinstance(incoming, str) and not incoming.strip())) and current.get(secret_key):
                        merged[secret_key] = current[secret_key]
                config = merged

        if provider == "openai":
            config = ProviderSettingsService._validate_openai_config(config)
        if provider == "deepseek":
            config = ProviderSettingsService._validate_deepseek_config(config)
        if provider == "groq":
            config = ProviderSettingsService._validate_groq_config(config)
        if provider == "deepgram":
            config = ProviderSettingsService._validate_deepgram_config(config)
        if provider == "cartesia":
            config = ProviderSettingsService._validate_cartesia_config(config)
        if provider == "elevenlabs":
            config = ProviderSettingsService._validate_elevenlabs_config(config)
        if provider == "vapi":
            config = ProviderSettingsService._validate_vapi_config(config)
        if provider == "azure_speech":
            config = ProviderSettingsService._validate_azure_speech_config(config)
        if provider == "telnyx":
            config = ProviderSettingsService._validate_telnyx_config(config)
            from app.services.telnyx_api_key import normalize_telnyx_api_key, telnyx_key_fingerprint

            incoming_key = normalize_telnyx_api_key(str(config.get("api_key") or ""))
            if incoming_key:
                fp = telnyx_key_fingerprint(incoming_key)
                if fp.get("too_short"):
                    raise ValueError(
                        f"Telnyx API key is too short ({fp['length']} characters). "
                        f"Copy the full secret key from Telnyx Portal → API Keys (about {fp['expected_length']} characters)."
                    )
                if not fp["looks_valid"]:
                    raise ValueError(
                        "Telnyx API key must be the full secret key from Telnyx Portal → API Keys (starts with KEY). "
                        "You may have pasted the Connection ID or another value by mistake."
                    )
                config["api_key"] = incoming_key
        if provider == "stripe":
            config = ProviderSettingsService._validate_stripe_config(config)
        if provider == "airwallex":
            config = ProviderSettingsService._validate_airwallex_config(config)
        if provider == "gocardless":
            config = ProviderSettingsService._validate_gocardless_config(config)
        if provider == "zoom":
            config = ProviderSettingsService._validate_zoom_config(config)
        if provider == "calendly":
            config = ProviderSettingsService._validate_calendly_config(config)
        if provider == "cronofy":
            config = ProviderSettingsService._validate_cronofy_config(config)
        if provider == "hubspot":
            config = ProviderSettingsService._validate_hubspot_config(config)
        if provider == "deepinfra":
            config = ProviderSettingsService._validate_deepinfra_config(config)

        payload = json.dumps(config, ensure_ascii=False, separators=(",", ":"))
        cipher = enc.encrypt_str(payload)

        obj = existing

        if obj is None:
            obj = ProviderConfig(scope="platform", org_id=None, provider=provider, is_enabled=is_enabled, encrypted_json=cipher)
        else:
            obj.is_enabled = is_enabled
            obj.encrypted_json = cipher
            obj.updated_at = datetime.utcnow()

        db.add(obj)
        db.commit()
        db.refresh(obj)
        return obj

    @staticmethod
    def get_platform_config(db: Session, *, provider: str) -> ProviderConfig | None:
        provider = provider.lower()
        ProviderSettingsService._assert_provider(provider)
        return db.execute(
            select(ProviderConfig).where(ProviderConfig.scope == "platform", ProviderConfig.org_id.is_(None), ProviderConfig.provider == provider)
        ).scalar_one_or_none()

    @staticmethod
    def get_platform_config_decrypted(db: Session, *, provider: str) -> tuple[dict[str, Any] | None, bool]:
        provider = provider.lower()
        obj = ProviderSettingsService.get_platform_config(db, provider=provider)
        if obj is None:
            return None, False
        enc = get_encryptor()
        raw = enc.decrypt_str(obj.encrypted_json)
        return json.loads(raw), obj.is_enabled

    @staticmethod
    def _required_fields(provider: str) -> set[str]:
        return set(ProviderSettingsService.REQUIRED_FIELDS.get(provider.lower(), set()))

    @staticmethod
    def _secret_keys(provider: str) -> set[str]:
        return set(ProviderSettingsService.SECRET_KEYS.get(provider.lower(), set()))

    @staticmethod
    def _validate_openai_config(config: dict[str, Any]) -> dict[str, Any]:
        cfg = {**config}
        errors: dict[str, str] = {}

        api_key = str(cfg.get("api_key") or "").strip()
        default_model = str(cfg.get("default_model") or "").strip()
        realtime_model = str(cfg.get("realtime_model") or "").strip()
        if not api_key:
            errors["api_key"] = "API key is required"
        if not default_model:
            errors["default_model"] = "Default model is required"
        if not realtime_model:
            errors["realtime_model"] = "Realtime / response model is required"

        try:
            temperature = float(cfg.get("temperature"))
        except (TypeError, ValueError):
            errors["temperature"] = "Temperature must be a number between 0.0 and 1.0"
        else:
            if not 0.0 <= temperature <= 1.0:
                errors["temperature"] = "Temperature must be between 0.0 and 1.0"
            else:
                cfg["temperature"] = temperature

        try:
            max_output_tokens = int(cfg.get("max_output_tokens"))
        except (TypeError, ValueError):
            errors["max_output_tokens"] = "Max output tokens must be a positive integer"
        else:
            if max_output_tokens <= 0:
                errors["max_output_tokens"] = "Max output tokens must be a positive integer"
            else:
                cfg["max_output_tokens"] = max_output_tokens

        if errors:
            details = "; ".join(f"{field}: {message}" for field, message in errors.items())
            raise ValueError(f"OpenAI settings validation failed: {details}")

        cfg["api_key"] = api_key
        cfg["default_model"] = default_model
        cfg["model"] = default_model
        cfg["realtime_model"] = realtime_model
        return cfg

    @staticmethod
    def _validate_deepseek_config(config: dict[str, Any]) -> dict[str, Any]:
        cfg = {**config}
        errors: dict[str, str] = {}
        api_key = str(cfg.get("api_key") or "").strip()
        base_url = str(cfg.get("base_url") or "https://api.deepseek.com").strip()
        model = str(cfg.get("model") or cfg.get("default_model") or "deepseek-chat").strip()

        if not api_key:
            errors["api_key"] = "API key is required"
        if not base_url:
            errors["base_url"] = "Base URL is required"
        if not model:
            errors["model"] = "Model is required"
        if errors:
            details = "; ".join(f"{field}: {message}" for field, message in errors.items())
            raise ValueError(f"DeepSeek settings validation failed: {details}")

        cfg["api_key"] = api_key
        cfg["base_url"] = base_url
        cfg["model"] = model
        cfg["default_model"] = model
        cfg["temperature"] = float(cfg.get("temperature") or 0.45)
        cfg["max_output_tokens"] = int(cfg.get("max_output_tokens") or 120)
        return cfg

    @staticmethod
    def _validate_groq_config(config: dict[str, Any]) -> dict[str, Any]:
        cfg = {**config}
        errors: dict[str, str] = {}
        api_key = str(cfg.get("api_key") or "").strip()
        base_url = str(cfg.get("base_url") or "https://api.groq.com/openai").strip().rstrip("/")
        stt_model = str(cfg.get("stt_model") or cfg.get("default_stt_model") or "whisper-large-v3-turbo").strip()
        llm_model = str(cfg.get("llm_model") or cfg.get("default_llm_model") or "llama-3.3-70b-versatile").strip()
        tts_model = str(cfg.get("tts_model") or cfg.get("default_tts_model") or "canopylabs/orpheus-v1-english").strip()
        tts_voice = str(cfg.get("tts_voice") or cfg.get("default_tts_voice") or "austin").strip().lower()

        if not api_key:
            errors["api_key"] = "API key is required"
        if not base_url:
            errors["base_url"] = "Base URL is required"
        if not stt_model:
            errors["stt_model"] = "STT model is required"
        if not llm_model:
            errors["llm_model"] = "LLM model is required"
        if not tts_model:
            errors["tts_model"] = "TTS model is required"
        if not tts_voice:
            errors["tts_voice"] = "TTS voice is required"
        if errors:
            details = "; ".join(f"{field}: {message}" for field, message in errors.items())
            raise ValueError(f"Groq settings validation failed: {details}")

        while base_url.endswith("/v1"):
            base_url = base_url[:-3].rstrip("/")
        cfg["api_key"] = api_key
        cfg["base_url"] = base_url or "https://api.groq.com/openai"
        cfg["stt_model"] = stt_model
        cfg["default_stt_model"] = stt_model
        cfg["llm_model"] = llm_model
        cfg["default_llm_model"] = llm_model
        cfg["tts_model"] = tts_model
        cfg["default_tts_model"] = tts_model
        cfg["tts_voice"] = tts_voice
        cfg["default_tts_voice"] = tts_voice
        cfg["temperature"] = float(cfg.get("temperature") or 0.45)
        cfg["max_output_tokens"] = int(cfg.get("max_output_tokens") or 120)
        return cfg

    @staticmethod
    def _validate_deepgram_config(config: dict[str, Any]) -> dict[str, Any]:
        cfg = {**config}
        errors: dict[str, str] = {}
        api_key = str(cfg.get("api_key") or "").strip()
        base_url = str(cfg.get("base_url") or "https://api.deepgram.com").strip().rstrip("/")
        ws_url = str(cfg.get("ws_url") or "wss://api.deepgram.com").strip().rstrip("/")
        model = str(cfg.get("model") or "nova-3").strip()
        language = str(cfg.get("language") or "en").strip()

        if not api_key:
            errors["api_key"] = "API key is required"
        if not base_url:
            errors["base_url"] = "Base URL is required"
        if not ws_url:
            errors["ws_url"] = "WebSocket URL is required"
        if not model:
            errors["model"] = "Model is required"
        if not language:
            errors["language"] = "Language is required"
        try:
            endpointing = int(cfg.get("endpointing") or 250)
            if endpointing < 0:
                errors["endpointing"] = "Endpointing must be zero or greater"
        except (TypeError, ValueError):
            errors["endpointing"] = "Endpointing must be an integer"
            endpointing = 250
        if errors:
            details = "; ".join(f"{field}: {message}" for field, message in errors.items())
            raise ValueError(f"Deepgram settings validation failed: {details}")

        cfg["api_key"] = api_key
        cfg["base_url"] = base_url
        cfg["ws_url"] = ws_url
        cfg["model"] = model
        cfg["language"] = language
        cfg["endpointing"] = endpointing
        cfg["interim_results"] = ProviderSettingsService._bool_config(cfg.get("interim_results"), default=True)
        return cfg

    @staticmethod
    def _validate_deepinfra_config(config: dict[str, Any]) -> dict[str, Any]:
        from app.services.moderation import normalize_moderation_config

        cfg = normalize_moderation_config(config)
        errors: dict[str, str] = {}
        api_key = str(cfg.get("api_key") or "").strip()
        base_url = str(cfg.get("base_url") or "").strip()
        model_name = str(cfg.get("model_name") or "").strip()
        if not api_key:
            errors["api_key"] = "API key is required"
        if not base_url:
            errors["base_url"] = "Base URL is required"
        if not model_name:
            errors["model_name"] = "Model name is required"
        if errors:
            details = "; ".join(f"{field}: {message}" for field, message in errors.items())
            raise ValueError(f"DeepInfra settings validation failed: {details}")
        cfg["api_key"] = api_key
        cfg["base_url"] = base_url
        cfg["model_name"] = model_name
        return cfg

    @staticmethod
    def _validate_cartesia_config(config: dict[str, Any]) -> dict[str, Any]:
        cfg = {**config}
        errors: dict[str, str] = {}
        api_key = str(cfg.get("api_key") or "").strip()
        base_url = str(cfg.get("base_url") or "https://api.cartesia.ai").strip().rstrip("/")
        model_id = str(cfg.get("model_id") or "sonic-2").strip()
        voice_id = str(cfg.get("voice_id") or "").strip()
        encoding = str(cfg.get("encoding") or "mp3").strip()
        container = str(cfg.get("container") or "mp3").strip()

        if not api_key:
            errors["api_key"] = "API key is required"
        if not base_url:
            errors["base_url"] = "Base URL is required"
        if not model_id:
            errors["model_id"] = "Model ID is required"
        if not voice_id:
            errors["voice_id"] = "Voice ID is required"
        try:
            sample_rate = int(cfg.get("sample_rate") or 44100)
            if sample_rate <= 0:
                errors["sample_rate"] = "Sample rate must be positive"
        except (TypeError, ValueError):
            errors["sample_rate"] = "Sample rate must be an integer"
            sample_rate = 44100
        if errors:
            details = "; ".join(f"{field}: {message}" for field, message in errors.items())
            raise ValueError(f"Cartesia settings validation failed: {details}")

        cfg["api_key"] = api_key
        cfg["base_url"] = base_url
        cfg["model_id"] = model_id
        cfg["voice_id"] = voice_id
        cfg["encoding"] = encoding
        cfg["container"] = container
        cfg["sample_rate"] = sample_rate
        return cfg

    @staticmethod
    def _optional_float(
        cfg: dict[str, Any],
        key: str,
        *,
        min_value: float | None = None,
        max_value: float | None = None,
    ) -> None:
        raw = cfg.get(key)
        if raw is None or raw == "":
            return
        value = float(raw)
        if min_value is not None and value < min_value:
            raise ValueError(f"{key} must be at least {min_value}")
        if max_value is not None and value > max_value:
            raise ValueError(f"{key} must be at most {max_value}")
        cfg[key] = value

    @staticmethod
    def _validate_elevenlabs_config(config: dict[str, Any]) -> dict[str, Any]:
        cfg = {**config}
        errors: dict[str, str] = {}
        api_key = str(cfg.get("api_key") or "").strip()
        default_voice_id = str(cfg.get("default_voice_id") or cfg.get("voice_id") or "").strip()
        base_url = str(cfg.get("base_url") or "https://api.elevenlabs.io").strip().rstrip("/")

        if not api_key:
            errors["api_key"] = "API key is required"
        if not default_voice_id:
            errors["default_voice_id"] = "Default voice ID is required"
        if errors:
            details = "; ".join(f"{field}: {message}" for field, message in errors.items())
            raise ValueError(f"ElevenLabs settings validation failed: {details}")

        try:
            ProviderSettingsService._optional_float(cfg, "stability", min_value=0.0, max_value=1.0)
            ProviderSettingsService._optional_float(cfg, "similarity_boost", min_value=0.0, max_value=1.0)
            ProviderSettingsService._optional_float(cfg, "style", min_value=0.0, max_value=1.0)
            ProviderSettingsService._optional_float(cfg, "speed", min_value=0.7, max_value=1.2)
        except (TypeError, ValueError) as e:
            raise ValueError(f"ElevenLabs settings validation failed: {e}") from e

        cfg["api_key"] = api_key
        cfg["default_voice_id"] = default_voice_id
        cfg["voice_id"] = default_voice_id
        cfg["base_url"] = base_url
        cfg["model_id"] = str(cfg.get("model_id") or "eleven_multilingual_v2").strip()
        cfg["speaker_boost"] = ProviderSettingsService._bool_config(cfg.get("speaker_boost"), default=True)
        return cfg

    @staticmethod
    def _validate_vapi_config(config: dict[str, Any]) -> dict[str, Any]:
        cfg = {**config}
        errors: dict[str, str] = {}
        public_key = str(cfg.get("public_key") or "").strip()
        assistant_id = str(cfg.get("assistant_id") or "").strip()
        api_key = str(cfg.get("api_key") or "").strip()
        base_url = str(cfg.get("base_url") or "https://api.vapi.ai").strip()

        if not public_key:
            errors["public_key"] = "Public key is required for browser calls"
        if not assistant_id:
            errors["assistant_id"] = "Assistant ID is required for browser calls"
        if not api_key:
            errors["api_key"] = "Private API key is required for lead transcripts and recordings"
        if errors:
            details = "; ".join(f"{field}: {message}" for field, message in errors.items())
            raise ValueError(f"Vapi settings validation failed: {details}")

        cfg["public_key"] = public_key
        cfg["assistant_id"] = assistant_id
        cfg["api_key"] = api_key
        cfg["base_url"] = base_url
        return cfg

    @staticmethod
    def _bool_config(value: Any, *, default: bool) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)

    @staticmethod
    def _validate_azure_speech_config(config: dict[str, Any]) -> dict[str, Any]:
        cfg = {**config}
        errors: dict[str, str] = {}

        api_key = str(cfg.get("api_key") or "").strip()
        region = str(cfg.get("region") or "").strip().lower()
        tts_enabled = ProviderSettingsService._bool_config(cfg.get("tts_enabled"), default=True)
        stt_enabled = ProviderSettingsService._bool_config(cfg.get("stt_enabled"), default=False)
        default_voice_id = str(cfg.get("default_voice_id") or "").strip()

        if not api_key:
            errors["api_key"] = "API key is required"
        if not region:
            errors["region"] = "Region is required"
        if tts_enabled and not default_voice_id:
            errors["default_voice_id"] = "Default voice ID is required when TTS is enabled"

        if errors:
            details = "; ".join(f"{field}: {message}" for field, message in errors.items())
            raise ValueError(f"Azure Speech settings validation failed: {details}")

        cfg["api_key"] = api_key
        cfg["region"] = region
        cfg["default_voice_id"] = default_voice_id
        cfg["tts_enabled"] = tts_enabled
        cfg["stt_enabled"] = stt_enabled
        return cfg

    @staticmethod
    def _normalize_telnyx_webhook_base(url: str) -> str:
        """Strip Telnyx path segments so base is only scheme + host (avoids doubled /telnyx/webhooks/voice)."""
        base = str(url or "").strip().rstrip("/")
        for suffix in (
            "/telnyx/webhooks/messages",
            "/telnyx/webhooks/verified-numbers",
            "/telnyx/webhooks/status",
            "/telnyx/webhooks/voice",
            "/telnyx/media-stream",
        ):
            if base.lower().endswith(suffix):
                base = base[: -len(suffix)].rstrip("/")
        marker = "/telnyx/webhooks/voice"
        while marker in base.lower():
            idx = base.lower().find(marker)
            tail = base[idx + len(marker) :]
            if tail.lower().startswith(marker):
                base = base[: idx + len(marker)]
            else:
                break
        return base.rstrip("/") or "https://localhost"

    @staticmethod
    def _canonical_telnyx_webhook_url(url: str, *, suffix: str, base: str) -> str:
        clean = str(url or "").strip()
        marker = suffix
        if clean.count(marker) > 1:
            pos = clean.find(marker)
            clean = clean[: pos + len(marker)]
        expected = f"{base.rstrip('/')}{suffix}"
        if clean.lower() == expected.lower():
            return expected
        if clean.lower().endswith(marker.lower()) and clean.lower().startswith(base.lower()):
            return expected
        return expected

    @staticmethod
    def _validate_telnyx_config(config: dict[str, Any]) -> dict[str, Any]:
        from app.services.telnyx_api_key import normalize_telnyx_api_key, normalize_telnyx_e164

        cfg = {**config}
        connection_id = str(cfg.get("connection_id") or cfg.get("voice_api_application_id") or "").strip()
        from_number = str(cfg.get("default_outbound_number") or cfg.get("from_phone_number") or "").strip()
        raw_base = str(cfg.get("webhook_base_url") or cfg.get("voice_webhook_url") or "").strip()
        webhook_base = ProviderSettingsService._normalize_telnyx_webhook_base(raw_base)
        cfg["webhook_base_url"] = webhook_base
        cfg["voice_webhook_url"] = ProviderSettingsService._canonical_telnyx_webhook_url(
            str(cfg.get("voice_webhook_url") or ""),
            suffix="/telnyx/webhooks/voice",
            base=webhook_base,
        )
        cfg["status_callback_url"] = ProviderSettingsService._canonical_telnyx_webhook_url(
            str(cfg.get("status_callback_url") or ""),
            suffix="/telnyx/webhooks/status",
            base=webhook_base,
        )
        cfg["verified_number_webhook_url"] = ProviderSettingsService._canonical_telnyx_webhook_url(
            str(cfg.get("verified_number_webhook_url") or ""),
            suffix="/telnyx/webhooks/verified-numbers",
            base=webhook_base,
        )
        cfg["messaging_webhook_url"] = ProviderSettingsService._canonical_telnyx_webhook_url(
            str(cfg.get("messaging_webhook_url") or ""),
            suffix="/telnyx/webhooks/messages",
            base=webhook_base,
        )
        ws_base = webhook_base.replace("https://", "wss://").replace("http://", "ws://")
        cfg["media_stream_url"] = ProviderSettingsService._canonical_telnyx_webhook_url(
            str(cfg.get("media_stream_url") or ""),
            suffix="/telnyx/media-stream",
            base=ws_base,
        )
        if connection_id:
            cfg["connection_id"] = connection_id
            cfg["voice_api_application_id"] = connection_id
        if from_number:
            try:
                from_number = normalize_telnyx_e164(from_number)
            except ValueError:
                pass
            cfg["default_outbound_number"] = from_number
            cfg["from_phone_number"] = from_number
            cfg["fallback_caller_id"] = from_number
        sms_from = str(cfg.get("sms_from") or "").strip()
        if sms_from:
            try:
                sms_from = normalize_telnyx_e164(sms_from)
            except ValueError:
                pass
            cfg["sms_from"] = sms_from
        wa_from = str(cfg.get("whatsapp_from") or "").strip()
        if wa_from:
            try:
                wa_from = normalize_telnyx_e164(wa_from)
            except ValueError:
                pass
            cfg["whatsapp_from"] = wa_from
        cfg["messaging_profile_id"] = str(cfg.get("messaging_profile_id") or "").strip()
        cfg["whatsapp_messaging_profile_id"] = str(cfg.get("whatsapp_messaging_profile_id") or "").strip()
        waba_id = str(cfg.get("whatsapp_waba_id") or cfg.get("waba_id") or "").strip()
        if waba_id:
            cfg["whatsapp_waba_id"] = waba_id
            cfg["waba_id"] = waba_id
        cfg["messaging_org_id"] = str(cfg.get("messaging_org_id") or cfg.get("default_messaging_org_id") or "").strip()
        cfg["api_key"] = normalize_telnyx_api_key(str(cfg.get("api_key") or ""))
        from app.services.telnyx_phone_allowlist_service import TelnyxPhoneAllowlistService

        allowlist, enabled = TelnyxPhoneAllowlistService.load_from_telnyx_config(cfg)
        cfg["phone_allowlist"] = allowlist
        cfg["phone_allowlist_enabled"] = enabled
        return cfg

    @staticmethod
    def _validate_stripe_config(config: dict[str, Any]) -> dict[str, Any]:
        cfg = {**config}
        errors: dict[str, str] = {}
        secret_key = str(cfg.get("secret_key") or "").strip()
        publishable_key = str(cfg.get("publishable_key") or "").strip()
        if not secret_key:
            errors["secret_key"] = "Secret key is required"
        elif not secret_key.startswith(("sk_test_", "sk_live_", "rk_test_", "rk_live_")):
            errors["secret_key"] = "Secret key must start with sk_test_ or sk_live_"
        if not publishable_key:
            errors["publishable_key"] = "Publishable key is required"
        elif not publishable_key.startswith(("pk_test_", "pk_live_")):
            errors["publishable_key"] = "Publishable key must start with pk_test_ or pk_live_"
        if errors:
            details = "; ".join(f"{field}: {message}" for field, message in errors.items())
            raise ValueError(f"Stripe settings validation failed: {details}")
        cfg["secret_key"] = secret_key
        cfg["publishable_key"] = publishable_key
        cfg["webhook_secret"] = str(cfg.get("webhook_secret") or "").strip()
        cfg["environment"] = "live" if secret_key.startswith(("sk_live_", "rk_live_")) else "test"
        return cfg

    @staticmethod
    def _validate_airwallex_config(config: dict[str, Any]) -> dict[str, Any]:
        cfg = {**config}
        errors: dict[str, str] = {}
        client_id = str(cfg.get("client_id") or "").strip()
        api_key = str(cfg.get("api_key") or "").strip()
        if not client_id:
            errors["client_id"] = "Client ID is required"
        if not api_key:
            errors["api_key"] = "API key is required"
        if errors:
            details = "; ".join(f"{field}: {message}" for field, message in errors.items())
            raise ValueError(f"Airwallex settings validation failed: {details}")
        env = str(cfg.get("environment") or "demo").strip().lower()
        cfg["client_id"] = client_id
        cfg["api_key"] = api_key
        cfg["webhook_secret"] = str(cfg.get("webhook_secret") or "").strip()
        cfg["environment"] = env if env in {"demo", "prod"} else "demo"
        return cfg

    @staticmethod
    def _validate_gocardless_config(config: dict[str, Any]) -> dict[str, Any]:
        cfg = {**config}
        access_token = str(cfg.get("access_token") or "").strip()
        if not access_token:
            raise ValueError("GoCardless settings validation failed: access_token: Access token is required")
        env = str(cfg.get("environment") or "").strip().lower()
        if env not in {"sandbox", "live"}:
            env = "live" if access_token.startswith("live_") else "sandbox"
        cfg["access_token"] = access_token
        cfg["environment"] = env
        cfg["webhook_secret"] = str(cfg.get("webhook_secret") or "").strip()
        return cfg

    @staticmethod
    def _validate_zoom_config(config: dict[str, Any]) -> dict[str, Any]:
        cfg = {**config}
        errors: dict[str, str] = {}
        account_id = str(cfg.get("account_id") or "").strip()
        client_id = str(cfg.get("client_id") or "").strip()
        client_secret = str(cfg.get("client_secret") or "").strip()
        if not account_id:
            errors["account_id"] = "Account ID is required"
        if not client_id:
            errors["client_id"] = "Client ID is required"
        if not client_secret:
            errors["client_secret"] = "Client secret is required"
        if errors:
            details = "; ".join(f"{field}: {message}" for field, message in errors.items())
            raise ValueError(f"Zoom settings validation failed: {details}")
        cfg["account_id"] = account_id
        cfg["client_id"] = client_id
        cfg["client_secret"] = client_secret
        cfg["base_url"] = str(cfg.get("base_url") or "https://api.zoom.us/v2").strip().rstrip("/")
        return cfg

    @staticmethod
    def _validate_calendly_config(config: dict[str, Any]) -> dict[str, Any]:
        cfg = {**config}
        errors: dict[str, str] = {}
        client_id = str(cfg.get("client_id") or "").strip()
        client_secret = str(cfg.get("client_secret") or "").strip()
        redirect_uri = str(cfg.get("redirect_uri") or "").strip()
        if not client_id:
            errors["client_id"] = "Client ID is required"
        if not client_secret:
            errors["client_secret"] = "Client secret is required"
        if not redirect_uri:
            errors["redirect_uri"] = "Redirect URI is required"
        if errors:
            details = "; ".join(f"{field}: {message}" for field, message in errors.items())
            raise ValueError(f"Calendly settings validation failed: {details}")
        cfg["client_id"] = client_id
        cfg["client_secret"] = client_secret
        cfg["redirect_uri"] = redirect_uri
        return cfg

    @staticmethod
    def _validate_cronofy_config(config: dict[str, Any]) -> dict[str, Any]:
        cfg = {**config}
        errors: dict[str, str] = {}
        client_id = str(cfg.get("client_id") or "").strip()
        client_secret = str(cfg.get("client_secret") or "").strip()
        redirect_uri = str(cfg.get("redirect_uri") or "").strip()
        if not client_id:
            errors["client_id"] = "Client ID is required"
        if not client_secret:
            errors["client_secret"] = "Client secret is required"
        if not redirect_uri:
            errors["redirect_uri"] = "Redirect URI is required"
        if errors:
            details = "; ".join(f"{field}: {message}" for field, message in errors.items())
            raise ValueError(f"Cronofy settings validation failed: {details}")
        cfg["client_id"] = client_id
        cfg["client_secret"] = client_secret
        cfg["redirect_uri"] = redirect_uri
        dc = str(cfg.get("data_center") or "uk").strip().lower()
        cfg["data_center"] = dc if dc in {"us", "uk", "de", "au", "ca", "sg"} else "uk"
        return cfg

    @staticmethod
    def _validate_hubspot_config(config: dict[str, Any]) -> dict[str, Any]:
        cfg = {**config}
        mode = str(cfg.get("auth_mode") or "private_app").strip().lower()
        cfg["auth_mode"] = mode if mode in {"oauth", "private_app"} else "private_app"
        if cfg.get("contact_sync_v1_enabled") is not None:
            cfg["contact_sync_v1_enabled"] = bool(cfg.get("contact_sync_v1_enabled"))
        if cfg["auth_mode"] != "oauth":
            return cfg
        errors: dict[str, str] = {}
        client_id = str(cfg.get("client_id") or "").strip()
        client_secret = str(cfg.get("client_secret") or "").strip()
        redirect_uri = str(cfg.get("redirect_uri") or "").strip()
        if not client_id:
            errors["client_id"] = "Client ID is required for OAuth mode"
        if not client_secret:
            errors["client_secret"] = "Client secret is required for OAuth mode"
        if not redirect_uri:
            errors["redirect_uri"] = "Redirect URI is required for OAuth mode"
        if errors:
            details = "; ".join(f"{field}: {message}" for field, message in errors.items())
            raise ValueError(f"HubSpot settings validation failed: {details}")
        cfg["client_id"] = client_id
        cfg["client_secret"] = client_secret
        cfg["redirect_uri"] = redirect_uri
        return cfg

    @staticmethod
    def _missing_fields(provider: str, config: dict[str, Any] | None) -> list[str]:
        if provider.lower() == "hubspot":
            cfg = config or {}
            mode = str(cfg.get("auth_mode") or "private_app").strip().lower()
            if mode != "oauth":
                return []
            missing: list[str] = []
            for key in ("client_id", "client_secret", "redirect_uri"):
                if not str(cfg.get(key) or "").strip():
                    missing.append(key)
            return missing
        if provider.lower() == "telnyx":
            cfg = config or {}
            missing: list[str] = []
            if not str(cfg.get("api_key") or "").strip():
                missing.append("api_key")
            if not str(cfg.get("connection_id") or cfg.get("voice_api_application_id") or "").strip():
                missing.append("connection_id")
            if not str(cfg.get("default_outbound_number") or cfg.get("from_phone_number") or "").strip():
                missing.append("default_outbound_number")
            if not str(cfg.get("fallback_caller_id") or "").strip():
                missing.append("fallback_caller_id")
            if not str(cfg.get("media_stream_url") or "").strip():
                missing.append("media_stream_url")
            return missing
        if provider.lower() == "azure_speech":
            cfg = config or {}
            missing: list[str] = []
            if not str(cfg.get("api_key") or "").strip():
                missing.append("api_key")
            if not str(cfg.get("region") or "").strip():
                missing.append("region")
            tts_enabled = ProviderSettingsService._bool_config(cfg.get("tts_enabled"), default=True)
            if tts_enabled and not str(cfg.get("default_voice_id") or "").strip():
                missing.append("default_voice_id")
            return missing

        required = ProviderSettingsService._required_fields(provider)
        if not required:
            return []
        cfg = config or {}
        missing: list[str] = []
        for k in sorted(required):
            v = cfg.get(k)
            if v is None:
                missing.append(k)
                continue
            if isinstance(v, str) and not v.strip():
                missing.append(k)
                continue
        return missing

    @staticmethod
    def summary(db: Session, *, provider: str) -> dict[str, Any]:
        provider = provider.lower()
        obj = ProviderSettingsService.get_platform_config(db, provider=provider)
        if obj is None:
            return {
                "provider": provider,
                "exists": False,
                "is_enabled": False,
                "updated_at": None,
                "configured": False,
                "missing_fields": sorted(list(ProviderSettingsService._required_fields(provider))),
            }
        # We never reveal secrets; just report presence heuristics.
        decrypted, enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider=provider)
        cfg = decrypted or {}
        if provider == "telnyx":
            cfg = ProviderSettingsService._validate_telnyx_config(cfg)
            from app.services.telnyx_api_key import resolve_telnyx_api_key

            api_key, _source = resolve_telnyx_api_key(db, cfg)
            if api_key:
                cfg = {**cfg, "api_key": api_key}
        missing = ProviderSettingsService._missing_fields(provider, cfg)
        configured = bool(enabled) and len(missing) == 0
        return {
            "provider": provider,
            "exists": True,
            "is_enabled": bool(obj.is_enabled),
            "updated_at": obj.updated_at,
            "configured": configured,
            "missing_fields": missing,
        }

    @staticmethod
    def get_platform_config_admin_view(db: Session, *, provider: str) -> dict[str, Any]:
        """
        Admin-safe view of provider settings.

        - Never returns secret values.
        - Returns non-secret config fields where possible + secret presence booleans.
        """
        provider = provider.lower()
        summary = ProviderSettingsService.summary(db, provider=provider)
        decrypted, _enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider=provider)
        cfg = decrypted or {}
        if provider == "telnyx":
            cfg = ProviderSettingsService._validate_telnyx_config(cfg)
        secret_keys = ProviderSettingsService._secret_keys(provider)

        safe_config: dict[str, Any] = {}
        for k, v in cfg.items():
            if str(k).lower() in secret_keys:
                continue
            safe_config[k] = v

        secret_set: dict[str, bool] = {}
        for k in sorted(secret_keys):
            v = cfg.get(k)
            if k == "api_key" and provider == "telnyx":
                from app.services.telnyx_api_key import normalize_telnyx_api_key, telnyx_key_fingerprint

                normalized = normalize_telnyx_api_key(str(v or ""))
                fp = telnyx_key_fingerprint(normalized)
                secret_set[k] = fp["looks_valid"]
            else:
                secret_set[k] = bool(v) and (not isinstance(v, str) or bool(str(v).strip()))

        view: dict[str, Any] = {**summary, "config": safe_config, "secret_set": secret_set}
        if provider == "telnyx":
            from app.services.telnyx_api_key import normalize_telnyx_api_key, telnyx_key_fingerprint

            normalized = normalize_telnyx_api_key(str((cfg or {}).get("api_key") or ""))
            fp = telnyx_key_fingerprint(normalized)
            view["api_key_meta"] = {
                "length": fp["length"],
                "prefix": fp["prefix"],
                "looks_valid": fp["looks_valid"],
            }
        return view

    @staticmethod
    def social_login_public_availability(db: Session) -> list[dict[str, Any]]:
        """
        Public-safe availability info for the sign-in page.

        Note: OAuth login is supported when enabled + configured.
        """
        out: list[dict[str, Any]] = []
        for provider in ["google", "apple", "linkedin"]:
            s = ProviderSettingsService.summary(db, provider=provider)
            enabled = bool(s.get("exists")) and bool(s.get("is_enabled"))
            configured = bool(s.get("configured"))
            missing_fields = s.get("missing_fields") or []
            login_supported = bool(enabled and configured)
            if not enabled:
                reason = "Disabled in admin settings" if s.get("exists") else "Not configured"
            elif not configured:
                reason = "Missing required settings"
            else:
                reason = ""
            out.append(
                {
                    "provider": provider,
                    "enabled": enabled,
                    "configured": configured,
                    "missing_fields": missing_fields,
                    "login_supported": login_supported,
                    "reason": reason,
                }
            )
        return out

