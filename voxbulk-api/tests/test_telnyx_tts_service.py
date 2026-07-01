from __future__ import annotations

import base64
import json

import httpx
import pytest


class _MockResponse:
    def __init__(
        self,
        status_code: int,
        *,
        json_body: dict | None = None,
        content: bytes = b"",
        headers: dict[str, str] | None = None,
        text: str = "",
    ):
        self.status_code = status_code
        self._json_body = json_body
        self.content = content
        self.headers = headers or {}
        self.text = text or (content.decode("utf-8", errors="replace") if content else "")
        self.request = httpx.Request("POST", "https://api.telnyx.com/v2/text-to-speech")

    def json(self):
        return self._json_body or {}


class _MockClient:
    def __init__(self, handler):
        self._handler = handler

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def post(self, url: str, *args, **kwargs):
        return self._handler("POST", url, kwargs)

    def get(self, url: str, *args, **kwargs):
        return self._handler("GET", url, kwargs)


def _patch_client(monkeypatch, handler):
    def factory(*args, **kwargs):
        return _MockClient(handler)

    monkeypatch.setattr(httpx, "Client", factory)


_FAKE_API_KEY = "KEY0123456789ABCDEF0123456789ABCDEF0123456789ABCDEF01"


def _patch_api_key(monkeypatch):
    monkeypatch.setattr(
        "app.services.telnyx_tts_service.require_telnyx_api_key",
        lambda db, config=None: (_FAKE_API_KEY, "test"),
    )
    monkeypatch.setattr(
        "app.services.telnyx_api_key.resolve_telnyx_api_key",
        lambda db, config=None: (_FAKE_API_KEY, "test"),
    )


def test_synthesize_primary_base64_success(monkeypatch):
    from app.services.telnyx_tts_service import synthesize_telnyx_speech

    audio = b"fake-mp3-bytes"
    b64 = base64.b64encode(audio).decode("ascii")

    def handler(method, url, kwargs):
        assert method == "POST"
        payload = kwargs.get("json") or {}
        assert payload.get("voice") == "Telnyx.NaturalHD.astra"
        assert payload.get("text") == "Hello"
        if url.endswith("/text-to-speech/speech"):
            return _MockResponse(404, json_body={"errors": [{"detail": "not found"}]})
        if url.endswith("/audio/speech"):
            return _MockResponse(404, json_body={"errors": [{"detail": "not found"}]})
        return _MockResponse(200, json_body={"base64_audio": b64}, headers={"content-type": "application/json"})

    _patch_api_key(monkeypatch)
    _patch_client(monkeypatch, handler)

    result = synthesize_telnyx_speech(None, text="Hello", voice="Telnyx.NaturalHD.astra")  # type: ignore[arg-type]
    assert result["ok"] is True
    assert result["audio_data"] == audio


def test_synthesize_binary_output_success(monkeypatch):
    from app.services.telnyx_tts_service import synthesize_telnyx_speech

    audio = b"binary-mp3"

    calls: list[str] = []

    def handler(method, url, kwargs):
        calls.append(url)
        payload = kwargs.get("json") or {}
        if payload.get("output_type") == "base64_output" and url.endswith("/text-to-speech"):
            return _MockResponse(422, json_body={"errors": [{"detail": "prefer binary"}]})
        if url.endswith("/text-to-speech"):
            return _MockResponse(200, content=audio, headers={"content-type": "audio/mpeg"})
        return _MockResponse(404, json_body={"errors": [{"detail": "not found"}]})

    _patch_api_key(monkeypatch)
    _patch_client(monkeypatch, handler)

    result = synthesize_telnyx_speech(None, text="Hello", voice="Telnyx.NaturalHD.astra")  # type: ignore[arg-type]
    assert result["ok"] is True
    assert result["audio_data"] == audio
    assert any(url.endswith("/text-to-speech") for url in calls)


def test_synthesize_fallback_on_404(monkeypatch):
    from app.services.telnyx_tts_service import synthesize_telnyx_speech

    audio = b"ultra-mp3"
    b64 = base64.b64encode(audio).decode("ascii")
    calls: list[str] = []

    def handler(method, url, kwargs):
        calls.append(url)
        if "/text-to-speech/speech" in url and not url.endswith("/audio/speech"):
            return _MockResponse(200, json_body={"base64_audio": b64}, headers={"content-type": "application/json"})
        if url.endswith("/text-to-speech"):
            return _MockResponse(404, json_body={"errors": [{"detail": "route missing"}]})
        return _MockResponse(404, json_body={"errors": [{"detail": "not found"}]})

    _patch_api_key(monkeypatch)
    _patch_client(monkeypatch, handler)

    voice = "Telnyx.Ultra.00967b2f-88a6-4a31-8153-110a92134b9f"
    result = synthesize_telnyx_speech(None, text="Hello", voice=voice)  # type: ignore[arg-type]
    assert result["ok"] is True
    assert result["audio_data"] == audio
    assert calls[0].endswith("/text-to-speech/speech")


def test_synthesize_all_endpoints_fail(monkeypatch):
    from app.services.telnyx_tts_service import synthesize_telnyx_speech

    def handler(method, url, kwargs):
        return _MockResponse(404, json_body={"errors": [{"detail": f"missing {url}"}]})

    _patch_api_key(monkeypatch)
    _patch_client(monkeypatch, handler)

    with pytest.raises(ValueError, match="Text-to-Speech REST API is not reachable"):
        synthesize_telnyx_speech(None, text="Hello", voice="Telnyx.Ultra.test-voice")  # type: ignore[arg-type]


def test_parse_telnyx_tts_error_extracts_detail():
    from app.services.telnyx_tts_service import parse_telnyx_tts_error

    resp = _MockResponse(
        400,
        json_body={"errors": [{"title": "Bad Request", "detail": "Invalid voice format"}]},
    )
    assert parse_telnyx_tts_error(resp) == "Invalid voice format"


def test_probe_reports_reachable(monkeypatch):
    from app.services.telnyx_tts_service import probe_telnyx_tts_access

    audio = b"probe"
    b64 = base64.b64encode(audio).decode("ascii")

    def handler(method, url, kwargs):
        if method == "GET" and "/text-to-speech/voices" in url:
            return _MockResponse(200, json_body={"voices": [{"voice_id": "astra"}, {"voice_id": "alloy"}]})
        if method == "POST" and url.endswith("/text-to-speech"):
            return _MockResponse(200, json_body={"base64_audio": b64}, headers={"content-type": "application/json"})
        return _MockResponse(404, json_body={"errors": [{"detail": "not found"}]})

    _patch_api_key(monkeypatch)
    _patch_client(monkeypatch, handler)

    probe = probe_telnyx_tts_access(None, ultra_voice=None)  # type: ignore[arg-type]
    assert probe["verdict"] == "tts_api_reachable"
    assert probe["voices_list"]["ok"] is True
    assert probe["voices_list"]["count"] == 2


def test_probe_stock_only_when_ultra_fails(monkeypatch):
    from app.services.telnyx_tts_service import probe_telnyx_tts_access

    audio = b"probe"
    b64 = base64.b64encode(audio).decode("ascii")

    def handler(method, url, kwargs):
        if method == "GET" and "/text-to-speech/voices" in url:
            return _MockResponse(200, json_body={"voices": [{"voice_id": "astra"}]})
        if method == "POST":
            payload = kwargs.get("json") or {}
            voice = str(payload.get("voice") or "")
            if "Ultra.uuid" in voice or voice.endswith(".uuid"):
                return _MockResponse(500, json_body={"errors": [{"detail": "Internal Server Error"}]})
            if url.endswith("/text-to-speech"):
                return _MockResponse(200, json_body={"base64_audio": b64}, headers={"content-type": "application/json"})
        return _MockResponse(404, json_body={"errors": [{"detail": "not found"}]})

    _patch_api_key(monkeypatch)
    _patch_client(monkeypatch, handler)

    probe = probe_telnyx_tts_access(None, ultra_voice="Telnyx.Ultra.uuid")  # type: ignore[arg-type]
    assert probe["verdict"] == "tts_stock_only"

