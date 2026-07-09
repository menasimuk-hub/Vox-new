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

RESPONSES_READ_TIMEOUT_SECONDS = float(os.getenv("OPENAI_RESPONSES_TIMEOUT_SECONDS") or 300)
RESPONSES_RETRY_COUNT = max(1, int(os.getenv("OPENAI_RESPONSES_RETRY_COUNT") or 3))
RESPONSES_RETRY_DELAY_SECONDS = float(os.getenv("OPENAI_RESPONSES_RETRY_DELAY_SECONDS") or 2.0)
OPENAI_TRANSIENT_HTTP_STATUSES = frozenset({408, 429, 500, 502, 503, 504, 529})
OPENAI_DEFAULT_BASE_URL = "https://api.openai.com"
DEEPSEEK_DEFAULT_BASE_URL = "https://api.deepseek.com"
GROQ_DEFAULT_BASE_URL = "https://api.groq.com/openai"
GROQ_DEFAULT_MODEL = "llama-3.3-70b-versatile"


@dataclass(frozen=True)
class OpenAIResponse:
    assistant_text: str
    tool_calls: list[AgentToolCall] = field(default_factory=list)
    usage: dict[str, Any] = field(default_factory=dict)
    timings: dict[str, Any] = field(default_factory=dict)
    raw_assistant_message: dict[str, Any] = field(default_factory=dict)
    finish_reason: str = ""


class OpenAIProviderService:
    TEST_PROMPT = "Say hello in one short sentence."
    _client: httpx.Client | None = None
    _client_lock = Lock()

    @staticmethod
    def _parse_tool_call(raw: dict[str, Any]) -> AgentToolCall:
        fn = raw.get("function") or {}
        args_raw = fn.get("arguments")
        args: dict[str, Any] = {}
        if isinstance(args_raw, dict):
            args = args_raw
        elif isinstance(args_raw, str) and args_raw.strip():
            try:
                parsed = json.loads(args_raw)
                args = parsed if isinstance(parsed, dict) else {"value": parsed}
            except json.JSONDecodeError:
                args = {"_parse_error": args_raw}
        return AgentToolCall(
            id=str(raw.get("id") or ""),
            name=str(fn.get("name") or ""),
            arguments=args,
        )

    @staticmethod
    def _parse_chat_completion_body(body: dict[str, Any]) -> OpenAIResponse:
        choice = (body.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        calls = [OpenAIProviderService._parse_tool_call(raw) for raw in msg.get("tool_calls") or []]
        return OpenAIResponse(
            assistant_text=str(msg.get("content") or "").strip(),
            tool_calls=calls,
            usage=body.get("usage") or {},
            raw_assistant_message=dict(msg) if isinstance(msg, dict) else {},
            finish_reason=str(choice.get("finish_reason") or ""),
        )

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
        provider = str(config.get("provider") or "").strip().lower()
        if provider == "deepinfra" and endpoint_path == "/v1/chat/completions":
            endpoint_path = "/chat/completions"
        return f"{config['base_url']}{endpoint_path}"

    @staticmethod
    def _is_realtime_model(model: str) -> bool:
        return "realtime" in str(model or "").lower()

    @staticmethod
    def _chat_uses_max_completion_tokens(model: str) -> bool:
        """OpenAI chat models increasingly reject legacy max_tokens."""
        if str(model or "").strip():
            return True
        return False

    @staticmethod
    def _chat_token_limit_payload(*, provider: str, model: str, tokens: int) -> dict[str, int]:
        cap = max(1, int(tokens))
        if str(provider or "").strip().lower() == "openai" and OpenAIProviderService._chat_uses_max_completion_tokens(model):
            return {"max_completion_tokens": cap}
        return {"max_tokens": cap}

    @staticmethod
    def _reasoning_model(model: str) -> bool:
        m = str(model or "").strip().lower()
        if not m:
            return False
        prefixes = ("o1", "o3", "o4", "gpt-5", "chatgpt-5", "gpt-4.1", "gpt-4.5")
        return any(m == p or m.startswith(f"{p}") for p in prefixes)

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
    def _responses_timeout() -> httpx.Timeout:
        read = max(60.0, RESPONSES_READ_TIMEOUT_SECONDS)
        return httpx.Timeout(connect=30.0, read=read, write=60.0, pool=30.0)

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
    def _groq_config_from_db_or_env(db: Session) -> dict[str, Any]:
        cfg, enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="groq")
        if enabled and cfg:
            config = ProviderSettingsService._validate_groq_config(cfg)
            return {
                "api_key": str(config.get("api_key") or "").strip(),
                "default_model": str(config.get("llm_model") or config.get("default_llm_model") or GROQ_DEFAULT_MODEL).strip(),
                "realtime_model": "",
                "temperature": float(config.get("temperature") or 0.45),
                "max_output_tokens": int(config.get("max_output_tokens") or 120),
                "base_url": OpenAIProviderService._normalize_base_url(config.get("base_url") or GROQ_DEFAULT_BASE_URL),
            }
        api_key = str(os.getenv("GROQ_API_KEY") or "").strip()
        if not api_key:
            raise ValueError("Groq is not configured. Set GROQ_API_KEY or configure it in Integrations.")
        return {
            "api_key": api_key,
            "default_model": str(os.getenv("GROQ_LLM_MODEL") or GROQ_DEFAULT_MODEL).strip(),
            "realtime_model": "",
            "temperature": float(os.getenv("GROQ_TEMPERATURE") or 0.45),
            "max_output_tokens": int(os.getenv("GROQ_MAX_OUTPUT_TOKENS") or 120),
            "base_url": OpenAIProviderService._normalize_base_url(os.getenv("GROQ_BASE_URL") or GROQ_DEFAULT_BASE_URL),
        }

    @staticmethod
    def _config_for_provider(db: Session, provider: str | None = None) -> dict[str, Any]:
        selected = str(provider or "openai").strip().lower()
        if selected == "deepseek":
            config = OpenAIProviderService._deepseek_config_from_db_or_env(db)
            return {**config, "provider": "deepseek"}
        if selected == "groq":
            config = OpenAIProviderService._groq_config_from_db_or_env(db)
            return {**config, "provider": "groq"}
        if selected == "deepinfra":
            config = OpenAIProviderService._deepinfra_config_from_db_or_env(db)
            return {**config, "provider": "deepinfra"}
        config = OpenAIProviderService._config(db)
        return {**config, "provider": "openai"}

    @staticmethod
    def _deepinfra_chat_base_url_from_config(config: dict[str, Any]) -> str:
        """OpenAI-compatible chat base URL — ignore Whisper/inference endpoints from Admin."""
        raw = str(
            config.get("base_url")
            or config.get("moderation_base_url")
            or os.getenv("DEEPINFRA_BASE_URL")
            or ""
        ).strip().rstrip("/")
        low = raw.lower()
        if not raw or "whisper" in low or "/inference/" in low:
            return "https://api.deepinfra.com/v1/openai"
        if low.endswith("/v1/openai") or "/v1/openai" in low:
            head = raw.lower().split("/v1/openai", 1)[0]
            return f"{raw[: len(head)]}/v1/openai" if head else "https://api.deepinfra.com/v1/openai"
        return "https://api.deepinfra.com/v1/openai"

    @staticmethod
    def _deepinfra_config_from_db_or_env(db: Session) -> dict[str, Any]:
        from app.services.provider_settings import ProviderSettingsService

        cfg, _enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="deepinfra")
        config = cfg if isinstance(cfg, dict) else {}
        api_key = str(config.get("api_key") or os.getenv("DEEPINFRA_API_KEY") or "").strip()
        if not api_key:
            raise ValueError("DeepInfra API key is not configured")
        base_url = OpenAIProviderService._deepinfra_chat_base_url_from_config(config)
        model = str(
            config.get("model_name")
            or config.get("moderation_model")
            or os.getenv("DEEPINFRA_LLM_MODEL")
            or "mistralai/Mistral-Small-3.2-24B-Instruct-2506"
        ).strip()
        return {
            "api_key": api_key,
            "default_model": model,
            "realtime_model": "",
            "temperature": float(os.getenv("DEEPINFRA_TEMPERATURE") or 0.35),
            "max_output_tokens": int(os.getenv("DEEPINFRA_MAX_OUTPUT_TOKENS") or 1200),
            "base_url": OpenAIProviderService._normalize_base_url(base_url),
        }

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
        config_cap = max(1, int(config["max_output_tokens"] or 120))
        selected_max_tokens = config_cap if max_tokens is None else max(1, int(max_tokens))
        selected_temperature = config["temperature"] if temperature is None else max(0.0, min(float(temperature), 1.0))
        request_messages = [{"role": m.role, "content": m.content} for m in messages]
        if str(system_prompt or "").strip():
            request_messages.insert(0, {"role": "system", "content": system_prompt})
        payload: dict[str, Any] = {
            "model": text_model,
            "messages": request_messages,
            **OpenAIProviderService._chat_token_limit_payload(
                provider=str(config.get("provider") or "openai"),
                model=text_model,
                tokens=selected_max_tokens,
            ),
        }
        if not (
            str(config.get("provider") or "openai").strip().lower() == "openai"
            and OpenAIProviderService._reasoning_model(text_model)
        ):
            payload["temperature"] = selected_temperature
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
                "output_token_limit": selected_max_tokens,
                "temperature": payload.get("temperature"),
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
        parsed = OpenAIProviderService._parse_chat_completion_body(body)
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
            assistant_text=parsed.assistant_text,
            tool_calls=parsed.tool_calls,
            usage=parsed.usage,
            raw_assistant_message=parsed.raw_assistant_message,
            finish_reason=parsed.finish_reason,
            timings={
                "openai_config_ms": config_ms,
                "openai_http_ms": http_ms,
                "openai_parse_ms": parse_ms,
                "openai_provider_total_ms": total_ms,
                "llm_provider": config["provider"],
            },
        )

    @staticmethod
    def complete_chat_raw(
        db: Session,
        *,
        system_prompt: str,
        messages: list[dict[str, Any]],
        model: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        provider: str = "deepseek",
    ) -> OpenAIResponse:
        total_start = time.perf_counter()
        config_start = time.perf_counter()
        config = OpenAIProviderService._config_for_provider(db, provider)
        config_ms = int((time.perf_counter() - config_start) * 1000)
        text_model = OpenAIProviderService._select_text_model(config, model)
        endpoint_path = "/v1/chat/completions"
        config_cap = max(1, int(config["max_output_tokens"] or 120))
        selected_max_tokens = config_cap if max_tokens is None else max(1, int(max_tokens))
        selected_temperature = config["temperature"] if temperature is None else max(0.0, min(float(temperature), 1.0))
        request_messages: list[dict[str, Any]] = []
        if str(system_prompt or "").strip():
            request_messages.append({"role": "system", "content": system_prompt})
        request_messages.extend(messages)
        payload: dict[str, Any] = {
            "model": text_model,
            "messages": request_messages,
            **OpenAIProviderService._chat_token_limit_payload(
                provider=str(config.get("provider") or "openai"),
                model=text_model,
                tokens=selected_max_tokens,
            ),
        }
        if not (
            str(config.get("provider") or "openai").strip().lower() == "openai"
            and OpenAIProviderService._reasoning_model(text_model)
        ):
            payload["temperature"] = selected_temperature
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
                "output_token_limit": selected_max_tokens,
                "temperature": payload.get("temperature"),
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
            logger.error(
                f"{config['provider']}_request_failed",
                extra={"status_code": response.status_code, "model": text_model, "endpoint_path": endpoint_path, "provider_body": body},
            )
            raise ValueError(f"{config['provider'].title()} request failed ({response.status_code}) at {diagnostics['final_url']}: {body}") from e
        parse_start = time.perf_counter()
        body = response.json()
        parsed = OpenAIProviderService._parse_chat_completion_body(body)
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
            assistant_text=parsed.assistant_text,
            tool_calls=parsed.tool_calls,
            usage=parsed.usage,
            raw_assistant_message=parsed.raw_assistant_message,
            finish_reason=parsed.finish_reason,
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
        config_cap = max(1, int(config["max_output_tokens"] or 120))
        selected_max_tokens = config_cap if max_tokens is None else max(1, int(max_tokens))
        selected_temperature = config["temperature"] if temperature is None else max(0.0, min(float(temperature), 1.0))
        request_messages = [{"role": m.role, "content": m.content} for m in messages]
        if str(system_prompt or "").strip():
            request_messages.insert(0, {"role": "system", "content": system_prompt})
        payload: dict[str, Any] = {
            "model": text_model,
            "messages": request_messages,
            **OpenAIProviderService._chat_token_limit_payload(
                provider=str(config.get("provider") or "openai"),
                model=text_model,
                tokens=selected_max_tokens,
            ),
            "stream": True,
        }
        if not (
            str(config.get("provider") or "openai").strip().lower() == "openai"
            and OpenAIProviderService._reasoning_model(text_model)
        ):
            payload["temperature"] = selected_temperature
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
                "output_token_limit": selected_max_tokens,
                "temperature": payload.get("temperature"),
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
    def _sanitize_provider_error_body(body: Any, *, max_len: int = 400) -> str:
        if isinstance(body, dict):
            err = body.get("error")
            if isinstance(err, dict):
                msg = str(err.get("message") or "").strip()
                code = str(err.get("code") or "").strip()
                if msg and code:
                    return f"{code}: {msg}"[:max_len]
                if msg:
                    return msg[:max_len]
            return json.dumps(body, ensure_ascii=False)[:max_len]
        text = str(body or "").strip()
        if "<html" in text.lower() or "<!doctype" in text.lower():
            import re

            title = re.search(r"<title[^>]*>([^<]+)</title>", text, re.I)
            if title:
                return title.group(1).strip()[:max_len]
            return "Upstream gateway error (HTML response from provider — usually temporary)."
        return text[:max_len] if text else "Unknown provider error"

    @staticmethod
    def _is_transient_openai_status(status_code: int) -> bool:
        return int(status_code) in OPENAI_TRANSIENT_HTTP_STATUSES

    @staticmethod
    def _responses_retry_delay(attempt: int) -> float:
        return RESPONSES_RETRY_DELAY_SECONDS * (2 ** max(0, attempt - 1))

    @staticmethod
    def _parse_structured_json_text(text: str, *, label: str) -> dict[str, Any]:
        if not text:
            raise ValueError(f"OpenAI {label} returned empty structured output")
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(f"OpenAI {label} returned invalid JSON: {text[:400]}") from e
        if not isinstance(parsed, dict):
            raise ValueError(f"OpenAI {label} JSON root must be an object")
        return parsed

    @staticmethod
    def _chat_completions_json(
        config: dict[str, Any],
        *,
        text_model: str,
        system_prompt: str,
        user_prompt: str,
        json_schema: dict[str, Any],
        schema_name: str,
        output_limit: int,
        selected_temperature: float,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Fallback structured JSON via /v1/chat/completions when Responses API is unavailable."""
        endpoint_path = "/v1/chat/completions"
        payload: dict[str, Any] = {
            "model": text_model,
            "messages": [
                {"role": "system", "content": str(system_prompt or "").strip()},
                {"role": "user", "content": str(user_prompt or "").strip()},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "schema": json_schema,
                    "strict": True,
                },
            },
            **OpenAIProviderService._chat_token_limit_payload(
                provider="openai",
                model=text_model,
                tokens=output_limit,
            ),
        }
        if not OpenAIProviderService._reasoning_model(text_model):
            payload["temperature"] = selected_temperature
        response = OpenAIProviderService._http_client().post(
            OpenAIProviderService._endpoint_url(config, endpoint_path),
            json=payload,
            headers=OpenAIProviderService._headers(config),
            timeout=OpenAIProviderService._responses_timeout(),
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            body: Any
            try:
                body = response.json()
            except Exception:
                body = response.text
            detail = OpenAIProviderService._sanitize_provider_error_body(body)
            raise ValueError(
                f"OpenAI Chat fallback failed ({response.status_code}): {detail}"
            ) from e
        raw = response.json()
        choices = raw.get("choices") or []
        message = (choices[0] or {}).get("message") if choices else {}
        text = str((message or {}).get("content") or "").strip()
        parsed = OpenAIProviderService._parse_structured_json_text(text, label="Chat")
        meta = {
            "model": text_model,
            "api_style": "chat_json_schema",
            "endpoint_path": endpoint_path,
            "usage": raw.get("usage") or {},
            "fallback_from": "responses",
        }
        return parsed, meta

    @staticmethod
    def _extract_responses_output_text(body: dict[str, Any]) -> str:
        chunks: list[str] = []
        for item in body.get("output") or []:
            if not isinstance(item, dict):
                continue
            for part in item.get("content") or []:
                if not isinstance(part, dict):
                    continue
                if str(part.get("type") or "") in {"output_text", "text"}:
                    text = str(part.get("text") or "").strip()
                    if text:
                        chunks.append(text)
        if chunks:
            return "\n".join(chunks).strip()
        return str(body.get("output_text") or "").strip()

    @staticmethod
    def responses_json(
        db: Session,
        *,
        system_prompt: str,
        user_prompt: str,
        json_schema: dict[str, Any],
        schema_name: str = "response",
        model: str | None = None,
        max_output_tokens: int = 12000,
        temperature: float | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Structured JSON via OpenAI Responses API (/v1/responses). OpenAI provider only."""
        config = OpenAIProviderService._config(db)
        pack_model = str(model or os.getenv("OPENAI_WA_TEMPLATE_MODEL") or "").strip()
        text_model = OpenAIProviderService._select_text_model(
            config,
            pack_model or config.get("default_model") or "gpt-4o-mini",
        )
        endpoint_path = "/v1/responses"
        selected_temperature = config["temperature"] if temperature is None else max(0.0, min(float(temperature), 1.0))
        output_limit = max(512, int(max_output_tokens))
        payload: dict[str, Any] = {
            "model": text_model,
            "input": [
                {"role": "system", "content": str(system_prompt or "").strip()},
                {"role": "user", "content": str(user_prompt or "").strip()},
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": schema_name,
                    "schema": json_schema,
                    "strict": True,
                }
            },
            "max_output_tokens": output_limit,
        }
        if not OpenAIProviderService._reasoning_model(text_model):
            payload["temperature"] = selected_temperature
        diagnostics = OpenAIProviderService._request_diagnostics(
            config, endpoint_path=endpoint_path, model=text_model, style="responses"
        )
        logger.info(
            "openai_responses_request",
            extra={
                "model": text_model,
                "endpoint_path": endpoint_path,
                "schema_name": schema_name,
                "max_output_tokens": payload["max_output_tokens"],
                "retry_count": RESPONSES_RETRY_COUNT,
            },
        )
        last_error: str | None = None
        last_status: int | None = None
        url = OpenAIProviderService._endpoint_url(config, endpoint_path)
        client = OpenAIProviderService._http_client()
        timeout = OpenAIProviderService._responses_timeout()

        for attempt in range(1, RESPONSES_RETRY_COUNT + 1):
            try:
                response = client.post(
                    url,
                    json=payload,
                    headers=OpenAIProviderService._headers(config),
                    timeout=timeout,
                )
            except httpx.TimeoutException as e:
                last_error = (
                    f"OpenAI timed out after {RESPONSES_READ_TIMEOUT_SECONDS:.0f}s "
                    f"(attempt {attempt}/{RESPONSES_RETRY_COUNT})."
                )
                if attempt < RESPONSES_RETRY_COUNT:
                    time.sleep(OpenAIProviderService._responses_retry_delay(attempt))
                    continue
                raise ValueError(
                    f"{last_error} Generating 10 templates can take several minutes — please try again."
                ) from e
            except (httpx.ConnectError, httpx.NetworkError) as e:
                last_error = f"Network error reaching OpenAI (attempt {attempt}/{RESPONSES_RETRY_COUNT}): {e}"
                if attempt < RESPONSES_RETRY_COUNT:
                    time.sleep(OpenAIProviderService._responses_retry_delay(attempt))
                    continue
                raise ValueError(last_error) from e

            if response.is_success:
                raw = response.json()
                text = OpenAIProviderService._extract_responses_output_text(raw)
                parsed = OpenAIProviderService._parse_structured_json_text(text, label="Responses")
                meta = {
                    "model": text_model,
                    "api_style": "responses",
                    "endpoint_path": endpoint_path,
                    "usage": raw.get("usage") or {},
                    "attempts": attempt,
                }
                return parsed, meta

            last_status = response.status_code
            try:
                body = response.json()
            except Exception:
                body = response.text
            detail = OpenAIProviderService._sanitize_provider_error_body(body)
            last_error = f"OpenAI Responses failed ({response.status_code}): {detail}"
            logger.warning(
                "openai_responses_attempt_failed",
                extra={
                    "status_code": response.status_code,
                    "model": text_model,
                    "attempt": attempt,
                    "detail": detail,
                },
            )
            if (
                OpenAIProviderService._is_transient_openai_status(response.status_code)
                and attempt < RESPONSES_RETRY_COUNT
            ):
                time.sleep(OpenAIProviderService._responses_retry_delay(attempt))
                continue
            break

        if last_status and OpenAIProviderService._is_transient_openai_status(last_status):
            logger.info(
                "openai_responses_chat_fallback",
                extra={"model": text_model, "last_status": last_status},
            )
            try:
                return OpenAIProviderService._chat_completions_json(
                    config,
                    text_model=text_model,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    json_schema=json_schema,
                    schema_name=schema_name,
                    output_limit=output_limit,
                    selected_temperature=selected_temperature,
                )
            except ValueError as fallback_exc:
                raise ValueError(
                    f"{last_error} Chat completions fallback also failed: {fallback_exc}"
                ) from fallback_exc

        if last_status == 502:
            raise ValueError(
                "OpenAI returned 502 Bad Gateway (temporary outage at api.openai.com). "
                "Wait a minute and try again. If it persists, check https://status.openai.com/"
            )
        raise ValueError(last_error or "OpenAI Responses request failed")

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
        token_limit = min(config["max_output_tokens"], 120)
        payload: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": "You are a concise British clinic voice assistant. Answer in one short sentence."},
                {"role": "user", "content": text},
            ],
            **OpenAIProviderService._chat_token_limit_payload(
                provider=str(config.get("provider") or "openai"),
                model=model,
                tokens=token_limit,
            ),
        }
        if not (
            str(config.get("provider") or "openai").strip().lower() == "openai"
            and OpenAIProviderService._reasoning_model(model)
        ):
            payload["temperature"] = config["temperature"]
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
