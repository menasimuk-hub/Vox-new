from __future__ import annotations

import logging
import os
import ssl
import time
import json
from dataclasses import dataclass, field
from threading import Lock
from typing import Any

import certifi
import httpx
from sqlalchemy.orm import Session

from app.services.agents.base import AgentMessage, AgentToolCall
from app.services.provider_settings import ProviderSettingsService

logger = logging.getLogger(__name__)
OPENAI_DEFAULT_BASE_URL = "https://api.openai.com"
DEEPSEEK_DEFAULT_BASE_URL = "https://api.deepseek.com"


@dataclass(frozen=True)
class OpenAIResponse:
    assistant_text: str
    tool_calls: list[AgentToolCall] = field(default_factory=list)
    usage: dict[str, Any] = field(default_factory=dict)
    timings: dict[str, int] = field(default_factory=dict)


class OpenAIProviderService:
    TEST_PROMPT = "Say hello in one short sentence."
    _client: httpx.Client | None = None
    _client_lock = Lock()

    @staticmethod
    def _verify_path() -> str:
        return certifi.where()

    @staticmethod
    def _ssl_context() -> ssl.SSLContext | str:
        try:
            import truststore

            return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        except Exception:
            return OpenAIProviderService._verify_path()

    @staticmethod
    def _tls_diagnostics() -> dict[str, str]:
        verify = OpenAIProviderService._ssl_context()
        if isinstance(verify, str):
            return {"tls_verify_mode": "certifi", "tls_verify": verify}
        return {"tls_verify_mode": "windows/system truststore", "tls_verify": "truststore.SSLContext"}

    @staticmethod
    def _normalize_base_url(raw: Any) -> str:
        base = str(raw or "").strip().rstrip("/")
        if not base:
            return OPENAI_DEFAULT_BASE_URL
        while base.endswith("/v1"):
            base = base[:-3].rstrip("/")
        return base or OPENAI_DEFAULT_BASE_URL

    @staticmethod
    def _endpoint_url(config: dict[str, Any], endpoint_path: str) -> str:
        return f"{config['base_url']}{endpoint_path}"

    @staticmethod
    def _is_realtime_model(model: str) -> bool:
        return "realtime" in str(model or "").lower()

    @staticmethod
    def _select_text_model(config: dict[str, Any], override: str | None = None) -> str:
        candidate = str(override or "").strip() or str(config.get("default_model") or "").strip()
        if OpenAIProviderService._is_realtime_model(candidate):
            fallback = str(config.get("default_model") or "").strip()
            if fallback and fallback != candidate and not OpenAIProviderService._is_realtime_model(fallback):
                return fallback
            raise ValueError(
                "Configured OpenAI text model is a realtime model. "
                "Use a normal text model for Default model, e.g. gpt-4o-mini. "
                "Keep realtime models only in Realtime / response model."
            )
        return candidate

    @staticmethod
    def _request_diagnostics(config: dict[str, Any], *, endpoint_path: str, model: str, style: str) -> dict[str, Any]:
        return {
            "base_url": config["base_url"],
            "endpoint_path": endpoint_path,
            "final_url": OpenAIProviderService._endpoint_url(config, endpoint_path),
            "model": model,
            "request_style": style,
            "api_key_set": bool(config["api_key"]),
            "api_key_length": len(config["api_key"]),
            **OpenAIProviderService._tls_diagnostics(),
        }

    @staticmethod
    def _headers(config: dict[str, Any]) -> dict[str, str]:
        return {"Authorization": f"Bearer {config['api_key']}", "Content-Type": "application/json"}

    @staticmethod
    def _http_client() -> httpx.Client:
        if OpenAIProviderService._client is None:
            with OpenAIProviderService._client_lock:
                if OpenAIProviderService._client is None:
                    OpenAIProviderService._client = httpx.Client(timeout=30.0, verify=OpenAIProviderService._ssl_context())
        return OpenAIProviderService._client

    @staticmethod
    def _config(db: Session) -> dict[str, Any]:
        cfg, enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="openai")
        config = cfg or {}
        if not enabled:
            env_api_key = str(os.getenv("OPENAI_API_KEY") or "").strip()
            if not env_api_key:
                raise ValueError("OpenAI is not configured or enabled")
            return {
                "api_key": env_api_key,
                "default_model": str(os.getenv("OPENAI_MODEL") or os.getenv("OPENAI_DEFAULT_MODEL") or "gpt-4o-mini").strip(),
                "realtime_model": str(os.getenv("OPENAI_REALTIME_MODEL") or "").strip(),
                "temperature": float(os.getenv("OPENAI_TEMPERATURE") or 0.45),
                "max_output_tokens": int(os.getenv("OPENAI_MAX_OUTPUT_TOKENS") or 120),
                "base_url": OpenAIProviderService._normalize_base_url(os.getenv("OPENAI_BASE_URL")),
            }
        config = ProviderSettingsService._validate_openai_config(config)
        return {
            **config,
            "api_key": str(config.get("api_key") or "").strip(),
            "default_model": str(os.getenv("OPENAI_MODEL") or config.get("default_model") or "").strip(),
            "realtime_model": str(config.get("realtime_model") or "").strip(),
            "temperature": float(config.get("temperature")),
            "max_output_tokens": int(config.get("max_output_tokens")),
            "base_url": OpenAIProviderService._normalize_base_url(config.get("base_url")),
        }

    @staticmethod
    def _deepseek_config() -> dict[str, Any]:
        # Prefer admin-saved config when present; env vars remain useful for quick local tests.
        api_key = str(os.getenv("DEEPSEEK_API_KEY") or "").strip()
        model = str(os.getenv("DEEPSEEK_MODEL") or "deepseek-chat").strip()
        base_url = OpenAIProviderService._normalize_base_url(os.getenv("DEEPSEEK_BASE_URL") or DEEPSEEK_DEFAULT_BASE_URL)
        return {
            "api_key": api_key,
            "default_model": model,
            "realtime_model": "",
            "temperature": float(os.getenv("DEEPSEEK_TEMPERATURE") or 0.45),
            "max_output_tokens": int(os.getenv("DEEPSEEK_MAX_OUTPUT_TOKENS") or 120),
            "base_url": base_url,
        }

    @staticmethod
    def _deepseek_config_from_db_or_env(db: Session) -> dict[str, Any]:
        cfg, enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="deepseek")
        if enabled and cfg:
            config = ProviderSettingsService._validate_deepseek_config(cfg)
            return {
                "api_key": str(config.get("api_key") or "").strip(),
                "default_model": str(config.get("model") or config.get("default_model") or "deepseek-chat").strip(),
                "realtime_model": "",
                "temperature": float(config.get("temperature") or 0.45),
                "max_output_tokens": int(config.get("max_output_tokens") or 120),
                "base_url": OpenAIProviderService._normalize_base_url(config.get("base_url") or DEEPSEEK_DEFAULT_BASE_URL),
            }
        api_key = str(os.getenv("DEEPSEEK_API_KEY") or "").strip()
        model = str(os.getenv("DEEPSEEK_MODEL") or "deepseek-chat").strip()
        base_url = OpenAIProviderService._normalize_base_url(os.getenv("DEEPSEEK_BASE_URL") or DEEPSEEK_DEFAULT_BASE_URL)
        if not api_key:
            raise ValueError("DeepSeek is not configured. Set DEEPSEEK_API_KEY for local provider comparison.")
        return {
            "api_key": api_key,
            "default_model": model,
            "realtime_model": "",
            "temperature": float(os.getenv("DEEPSEEK_TEMPERATURE") or 0.45),
            "max_output_tokens": int(os.getenv("DEEPSEEK_MAX_OUTPUT_TOKENS") or 120),
            "base_url": base_url,
        }

    @staticmethod
    def _config_for_provider(db: Session, provider: str | None = None) -> dict[str, Any]:
        selected = str(provider or "openai").strip().lower()
        if selected == "deepseek":
            config = OpenAIProviderService._deepseek_config_from_db_or_env(db)
            return {**config, "provider": "deepseek"}
        config = OpenAIProviderService._config(db)
        return {**config, "provider": "openai"}

    @staticmethod
    def complete(
        db: Session,
        *,
        system_prompt: str,
        messages: list[AgentMessage],
        model: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        provider: str | None = None,
    ) -> OpenAIResponse:
        total_start = time.perf_counter()
        config_start = time.perf_counter()
        config = OpenAIProviderService._config_for_provider(db, provider)
        config_ms = int((time.perf_counter() - config_start) * 1000)
        text_model = OpenAIProviderService._select_text_model(config, model)
        endpoint_path = "/v1/chat/completions"
        selected_max_tokens = max(1, min(int(max_tokens or config["max_output_tokens"]), config["max_output_tokens"]))
        selected_temperature = config["temperature"] if temperature is None else max(0.0, min(float(temperature), 1.0))
        payload: dict[str, Any] = {
            "model": text_model,
            "messages": [{"role": "system", "content": system_prompt}]
            + [{"role": m.role, "content": m.content} for m in messages],
            "temperature": selected_temperature,
            "max_tokens": selected_max_tokens,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        diagnostics = OpenAIProviderService._request_diagnostics(config, endpoint_path=endpoint_path, model=text_model, style="chat")
        logger.info(
            f"{config['provider']}_request",
            extra={
                "base_url": diagnostics["base_url"],
                "endpoint_path": endpoint_path,
                "model": text_model,
                "request_style": "chat",
                "api_key_length": diagnostics["api_key_length"],
                "max_tokens": selected_max_tokens,
                "temperature": selected_temperature,
            },
        )
        http_start = time.perf_counter()
        response = OpenAIProviderService._http_client().post(
            OpenAIProviderService._endpoint_url(config, endpoint_path),
            json=payload,
            headers=OpenAIProviderService._headers(config),
        )
        http_ms = int((time.perf_counter() - http_start) * 1000)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            body: Any
            try:
                body = response.json()
            except Exception:
                body = response.text
            logger.error(f"{config['provider']}_request_failed", extra={"status_code": response.status_code, "model": text_model, "endpoint_path": endpoint_path, "provider_body": body})
            raise ValueError(f"{config['provider'].title()} request failed ({response.status_code}) at {diagnostics['final_url']}: {body}") from e
        parse_start = time.perf_counter()
        body = response.json()
        choice = (body.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        calls: list[AgentToolCall] = []
        for raw in msg.get("tool_calls") or []:
            fn = raw.get("function") or {}
            calls.append(AgentToolCall(name=str(fn.get("name") or ""), arguments={"raw": fn.get("arguments")}))
        parse_ms = int((time.perf_counter() - parse_start) * 1000)
        total_ms = int((time.perf_counter() - total_start) * 1000)
        logger.info(
            f"{config['provider']}_request_timings",
            extra={
                "model": text_model,
                "config_ms": config_ms,
                "http_ms": http_ms,
                "parse_ms": parse_ms,
                "total_ms": total_ms,
                "max_tokens": selected_max_tokens,
            },
        )
        return OpenAIResponse(
            assistant_text=str(msg.get("content") or "").strip(),
            tool_calls=calls,
            usage=body.get("usage") or {},
            timings={
                "openai_config_ms": config_ms,
                "openai_http_ms": http_ms,
                "openai_parse_ms": parse_ms,
                "openai_provider_total_ms": total_ms,
                "llm_provider": config["provider"],
            },
        )

    @staticmethod
    def stream_complete(
        db: Session,
        *,
        system_prompt: str,
        messages: list[AgentMessage],
        model: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        provider: str | None = None,
    ):
        config = OpenAIProviderService._config_for_provider(db, provider)
        text_model = OpenAIProviderService._select_text_model(config, model)
        endpoint_path = "/v1/chat/completions"
        selected_max_tokens = max(1, min(int(max_tokens or config["max_output_tokens"]), config["max_output_tokens"]))
        selected_temperature = config["temperature"] if temperature is None else max(0.0, min(float(temperature), 1.0))
        payload: dict[str, Any] = {
            "model": text_model,
            "messages": [{"role": "system", "content": system_prompt}]
            + [{"role": m.role, "content": m.content} for m in messages],
            "temperature": selected_temperature,
            "max_tokens": selected_max_tokens,
            "stream": True,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        logger.info(
            f"{config['provider']}_stream_request",
            extra={
                "base_url": config["base_url"],
                "endpoint_path": endpoint_path,
                "model": text_model,
                "request_style": "chat_stream",
                "api_key_length": len(config["api_key"]),
                "max_tokens": selected_max_tokens,
                "temperature": selected_temperature,
            },
        )
        with OpenAIProviderService._http_client().stream(
            "POST",
            OpenAIProviderService._endpoint_url(config, endpoint_path),
            json=payload,
            headers=OpenAIProviderService._headers(config),
        ) as response:
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as e:
                body = response.read().decode("utf-8", errors="replace")
                logger.error(f"{config['provider']}_stream_failed", extra={"status_code": response.status_code, "model": text_model, "endpoint_path": endpoint_path, "provider_body": body})
                raise ValueError(f"{config['provider'].title()} stream failed ({response.status_code}): {body}") from e

            for raw_line in response.iter_lines():
                line = raw_line.strip()
                if not line or not line.startswith("data:"):
                    continue
                data = line.removeprefix("data:").strip()
                if data == "[DONE]":
                    break
                try:
                    payload = json.loads(data)
                except json.JSONDecodeError:
                    continue
                delta = (((payload.get("choices") or [{}])[0].get("delta") or {}).get("content")) or ""
                if delta:
                    yield str(delta)

    @staticmethod
    def diagnostics(db: Session) -> dict[str, Any]:
        config = OpenAIProviderService._config(db)
        return {
            "base_url": config["base_url"],
            "default_model": config["default_model"],
            "realtime_model": config["realtime_model"],
            "temperature": config["temperature"],
            "max_output_tokens": config["max_output_tokens"],
            "api_key_set": bool(config["api_key"]),
            "api_key_length": len(config["api_key"]),
            **OpenAIProviderService._tls_diagnostics(),
        }

    @staticmethod
    def test_completion_raw(db: Session, *, prompt: str | None = None, provider: str | None = None) -> dict[str, Any]:
        text = prompt or OpenAIProviderService.TEST_PROMPT
        config = OpenAIProviderService._config_for_provider(db, provider)
        model = OpenAIProviderService._select_text_model(config)
        endpoint_path = "/v1/chat/completions"
        diagnostics = OpenAIProviderService._request_diagnostics(config, endpoint_path=endpoint_path, model=model, style="chat")
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": "You are a concise British clinic voice assistant. Answer in one short sentence."},
                {"role": "user", "content": text},
            ],
            "temperature": config["temperature"],
            "max_tokens": min(config["max_output_tokens"], 120),
        }
        logger.info(f"{config['provider']}_smoke_request", extra={"base_url": config["base_url"], "endpoint_path": endpoint_path, "model": model, "request_style": "chat", "api_key_length": diagnostics["api_key_length"]})
        response = OpenAIProviderService._http_client().post(diagnostics["final_url"], json=payload, headers=OpenAIProviderService._headers(config))
        try:
            body: Any = response.json()
        except Exception:
            body = {"raw_text": response.text}
        if not response.is_success:
            return {
                "ok": False,
                "status_code": response.status_code,
                "prompt": text,
                "diagnostics": diagnostics,
                "openai_payload": body,
                "persisted": False,
            }
        assistant_text = str((((body.get("choices") or [{}])[0].get("message") or {}).get("content")) or "").strip()
        return {
            "ok": True,
            "provider": config["provider"],
            "status_code": response.status_code,
            "prompt": text,
            "assistant_text": assistant_text,
            "usage": body.get("usage") or {},
            "diagnostics": diagnostics,
            "openai_payload": body,
            "persisted": False,
        }

    @staticmethod
    def test_completion(db: Session, *, prompt: str | None = None) -> dict[str, Any]:
        result = OpenAIProviderService.test_completion_raw(db, prompt=prompt)
        if not result["ok"]:
            raise ValueError(f"OpenAI smoke test failed ({result['status_code']}): {result['openai_payload']}")
        return result
