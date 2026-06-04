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
OPENAI_DEFAULT_BASE_URL = "https://api.openai.com"
DEEPSEEK_DEFAULT_BASE_URL = "https://api.deepseek.com"
GROQ_DEFAULT_BASE_URL = "https://api.groq.com/openai"
GROQ_DEFAULT_MODEL = "llama-3.3-70b-versatile"


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
            },
        )
        try:
            response = OpenAIProviderService._http_client().post(
                OpenAIProviderService._endpoint_url(config, endpoint_path),
                json=payload,
                headers=OpenAIProviderService._headers(config),
                timeout=OpenAIProviderService._responses_timeout(),
            )
        except httpx.TimeoutException as e:
            raise ValueError(
                f"OpenAI Responses request timed out after {RESPONSES_READ_TIMEOUT_SECONDS:.0f}s. "
                "Generating 10 templates can take several minutes — please try again."
            ) from e
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            body: Any
            try:
                body = response.json()
            except Exception:
                body = response.text
            logger.error(
                "openai_responses_failed",
                extra={"status_code": response.status_code, "model": text_model, "provider_body": body},
            )
            raise ValueError(
                f"OpenAI Responses request failed ({response.status_code}) at {diagnostics['final_url']}: {body}"
            ) from e
        raw = response.json()
        text = OpenAIProviderService._extract_responses_output_text(raw)
        if not text:
            raise ValueError("OpenAI Responses returned empty structured output")
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(f"OpenAI Responses returned invalid JSON: {text[:400]}") from e
        if not isinstance(parsed, dict):
            raise ValueError("OpenAI Responses JSON root must be an object")
        meta = {
            "model": text_model,
            "api_style": "responses",
            "endpoint_path": endpoint_path,
            "usage": raw.get("usage") or {},
        }
        return parsed, meta

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
