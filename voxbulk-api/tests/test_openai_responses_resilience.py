"""OpenAI Responses API retries and error sanitization."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import httpx
import pytest

from app.services.providers.openai_service import OpenAIProviderService

HTML_502 = """<!DOCTYPE html><html><head><title>api.openai.com | 502: Bad gateway</title></head><body></body></html>"""


def test_sanitize_html_502():
    msg = OpenAIProviderService._sanitize_provider_error_body(HTML_502)
    assert "502" in msg
    assert "<html" not in msg.lower()


def test_sanitize_json_error():
    body = {"error": {"message": "Rate limit exceeded", "code": "rate_limit_exceeded"}}
    msg = OpenAIProviderService._sanitize_provider_error_body(body)
    assert "rate_limit" in msg


def test_responses_retries_then_succeeds(monkeypatch):
    calls = {"n": 0}
    ok_payload = {
        "output": [
            {
                "content": [
                    {"type": "output_text", "text": json.dumps({"templates": [], "ok": True})}
                ]
            }
        ]
    }

    def fake_post(url, **kwargs):
        calls["n"] += 1
        if calls["n"] < 2:
            return httpx.Response(502, text=HTML_502, request=httpx.Request("POST", url))
        return httpx.Response(200, json=ok_payload, request=httpx.Request("POST", url))

    client = MagicMock()
    client.post.side_effect = fake_post
    monkeypatch.setattr(OpenAIProviderService, "_http_client", lambda: client)
    monkeypatch.setattr("app.services.providers.openai_service.RESPONSES_RETRY_COUNT", 3)
    monkeypatch.setattr("app.services.providers.openai_service.RESPONSES_RETRY_DELAY_SECONDS", 0.01)
    monkeypatch.setattr(
        OpenAIProviderService,
        "_config",
        lambda db: {
            "api_key": "sk-test",
            "default_model": "gpt-4o-mini",
            "temperature": 0.5,
            "base_url": "https://api.openai.com",
        },
    )

    parsed, meta = OpenAIProviderService.responses_json(
        None,
        system_prompt="sys",
        user_prompt="user",
        json_schema={"type": "object", "properties": {}, "additionalProperties": False},
        schema_name="test_schema",
        max_output_tokens=1000,
    )
    assert parsed.get("ok") is True
    assert meta["api_style"] == "responses"
    assert meta.get("attempts") == 2
    assert calls["n"] == 2


def test_responses_502_falls_back_to_chat(monkeypatch):
    chat_payload = {
        "choices": [{"message": {"content": json.dumps({"templates": [{"x": 1}]})}}],
        "usage": {},
    }

    def fake_post(url, **kwargs):
        if "/responses" in str(url):
            return httpx.Response(502, text=HTML_502, request=httpx.Request("POST", url))
        return httpx.Response(200, json=chat_payload, request=httpx.Request("POST", url))

    client = MagicMock()
    client.post.side_effect = fake_post
    monkeypatch.setattr(OpenAIProviderService, "_http_client", lambda: client)
    monkeypatch.setattr("app.services.providers.openai_service.RESPONSES_RETRY_COUNT", 1)
    monkeypatch.setattr("app.services.providers.openai_service.RESPONSES_RETRY_DELAY_SECONDS", 0.01)
    monkeypatch.setattr(
        OpenAIProviderService,
        "_config",
        lambda db: {
            "api_key": "sk-test",
            "default_model": "gpt-4o-mini",
            "temperature": 0.5,
            "base_url": "https://api.openai.com",
        },
    )

    parsed, meta = OpenAIProviderService.responses_json(
        None,
        system_prompt="sys",
        user_prompt="user",
        json_schema={
            "type": "object",
            "properties": {"templates": {"type": "array"}},
            "required": ["templates"],
            "additionalProperties": False,
        },
        schema_name="wa_pack",
    )
    assert "templates" in parsed
    assert meta["api_style"] == "chat_json_schema"
    assert meta.get("fallback_from") == "responses"
