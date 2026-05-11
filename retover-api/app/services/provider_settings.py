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
        "twilio",
        "dentally",
        "carestack",
        "pabau",
        "cliniko",
        "optix",
        "ocuco",
        "vapi",
        "deepseek",
        "elevenlabs",
        "gocardless",
        "telnyx",
        "azure_speech",
        "openai",
        "google",
        "facebook",
        "linkedin",
    }

    # Keys we expect for "configured" status (per provider). Secrets are stored encrypted and never returned.
    REQUIRED_FIELDS: dict[str, set[str]] = {
        "twilio": {"account_sid", "auth_token", "whatsapp_from", "from_number", "twiml_url"},
        "dentally": {"base_url", "api_key"},
        "carestack": {"base_url", "api_key"},
        "pabau": {"base_url", "api_key"},
        "cliniko": {"base_url", "api_key"},
        "optix": {"base_url", "api_key"},
        "ocuco": {"base_url", "api_key"},
        "vapi": {"public_key", "assistant_id"},
        "deepseek": {"api_key", "base_url", "model"},
        "elevenlabs": {"api_key", "default_voice_id"},
        "gocardless": {"access_token", "webhook_secret"},
        "telnyx": {"api_key", "connection_id", "default_outbound_number", "outbound_voice_profile_id", "voice_webhook_url"},
        "azure_speech": {"api_key", "region", "default_voice_id"},
        "openai": {"api_key", "default_model", "realtime_model", "temperature", "max_output_tokens"},
        # Social OAuth providers. These settings are consumed by the FastAPI OAuth start/callback flow.
        "google": {"client_id", "client_secret", "redirect_uri"},
        "facebook": {"client_id", "client_secret", "redirect_uri"},
        "linkedin": {"client_id", "client_secret", "redirect_uri"},
    }

    SECRET_KEYS: dict[str, set[str]] = {
        "twilio": {"auth_token"},
        "dentally": {"api_key"},
        "carestack": {"api_key"},
        "pabau": {"api_key"},
        "cliniko": {"api_key"},
        "optix": {"api_key"},
        "ocuco": {"api_key"},
        "vapi": {"api_key"},
        "deepseek": {"api_key"},
        "elevenlabs": {"api_key"},
        "gocardless": {"access_token", "webhook_secret"},
        "telnyx": {"api_key"},
        "azure_speech": {"api_key"},
        "openai": {"api_key"},
        "google": {"client_secret"},
        "facebook": {"client_secret"},
        "linkedin": {"client_secret"},
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
        if provider == "vapi":
            config = ProviderSettingsService._validate_vapi_config(config)
        if provider == "elevenlabs":
            config = ProviderSettingsService._validate_elevenlabs_config(config)
        if provider == "azure_speech":
            config = ProviderSettingsService._validate_azure_speech_config(config)
        if provider == "telnyx":
            config = ProviderSettingsService._validate_telnyx_config(config)

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
        if errors:
            details = "; ".join(f"{field}: {message}" for field, message in errors.items())
            raise ValueError(f"Vapi settings validation failed: {details}")

        cfg["public_key"] = public_key
        cfg["assistant_id"] = assistant_id
        cfg["api_key"] = api_key
        cfg["base_url"] = base_url
        return cfg

    @staticmethod
    def _optional_float(cfg: dict[str, Any], key: str, *, min_value: float | None = None, max_value: float | None = None) -> None:
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
    def _validate_telnyx_config(config: dict[str, Any]) -> dict[str, Any]:
        cfg = {**config}
        errors: dict[str, str] = {}

        api_key = str(cfg.get("api_key") or "").strip()
        connection_id = str(
            cfg.get("connection_id")
            or cfg.get("voice_api_application_id")
            or cfg.get("call_control_connection_id")
            or ""
        ).strip()
        default_outbound_number = str(
            cfg.get("default_outbound_number")
            or cfg.get("from_phone_number")
            or cfg.get("from_number")
            or ""
        ).strip()
        outbound_voice_profile_id = str(cfg.get("outbound_voice_profile_id") or "").strip()
        webhook_base_url = str(cfg.get("webhook_base_url") or "").strip().rstrip("/")
        voice_webhook_url = str(cfg.get("voice_webhook_url") or "").strip()
        status_callback_url = str(cfg.get("status_callback_url") or "").strip()
        verified_number_webhook_url = str(cfg.get("verified_number_webhook_url") or "").strip()

        if webhook_base_url:
            voice_webhook_url = voice_webhook_url or f"{webhook_base_url}/telnyx/webhooks/voice"
            status_callback_url = status_callback_url or f"{webhook_base_url}/telnyx/webhooks/status"
            verified_number_webhook_url = verified_number_webhook_url or f"{webhook_base_url}/telnyx/webhooks/verified-numbers"

        if not api_key:
            errors["api_key"] = "API key is required"
        if not connection_id:
            errors["connection_id"] = "Voice API application / connection ID is required"
        if not default_outbound_number:
            errors["default_outbound_number"] = "From phone number is required"
        if not outbound_voice_profile_id:
            errors["outbound_voice_profile_id"] = "Outbound voice profile ID is required"
        if not voice_webhook_url:
            errors["voice_webhook_url"] = "Voice webhook URL is required"

        if errors:
            details = "; ".join(f"{field}: {message}" for field, message in errors.items())
            raise ValueError(f"Telnyx settings validation failed: {details}")

        cfg["api_key"] = api_key
        cfg["connection_id"] = connection_id
        cfg["voice_api_application_id"] = connection_id
        cfg["call_control_connection_id"] = connection_id
        cfg["default_outbound_number"] = default_outbound_number
        cfg["from_phone_number"] = default_outbound_number
        cfg["from_number"] = default_outbound_number
        cfg["fallback_caller_id"] = str(cfg.get("fallback_caller_id") or default_outbound_number).strip()
        cfg["outbound_voice_profile_id"] = outbound_voice_profile_id
        cfg["webhook_base_url"] = webhook_base_url
        cfg["voice_webhook_url"] = voice_webhook_url
        cfg["status_callback_url"] = status_callback_url
        cfg["verified_number_webhook_url"] = verified_number_webhook_url
        cfg["media_stream_url"] = str(cfg.get("media_stream_url") or "").strip()
        return cfg

    @staticmethod
    def _missing_fields(provider: str, config: dict[str, Any] | None) -> list[str]:
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
        missing = ProviderSettingsService._missing_fields(provider, decrypted)
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
        secret_keys = ProviderSettingsService._secret_keys(provider)

        safe_config: dict[str, Any] = {}
        for k, v in cfg.items():
            if str(k).lower() in secret_keys:
                continue
            safe_config[k] = v

        secret_set = {k: bool(cfg.get(k)) for k in sorted(secret_keys)}

        return {**summary, "config": safe_config, "secret_set": secret_set}

    @staticmethod
    def social_login_public_availability(db: Session) -> list[dict[str, Any]]:
        """
        Public-safe availability info for the sign-in page.

        Note: OAuth login is supported when enabled + configured.
        """
        out: list[dict[str, Any]] = []
        for provider in ["google", "facebook", "linkedin"]:
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

