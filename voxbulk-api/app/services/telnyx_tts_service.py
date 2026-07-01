from __future__ import annotations

import base64
import time
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.core.http_ssl import httpx_ssl_verify
from app.services.telnyx_api_key import require_telnyx_api_key, telnyx_key_fingerprint

TELNYX_API_BASE = "https://api.telnyx.com/v2"
STOCK_PROBE_VOICE = "Telnyx.NaturalHD.astra"
_PROBE_TEXT = "Hello, this is a Telnyx TTS probe from VoxBulk."


def _clamp_voice_speed(voice_speed: float | None) -> float | None:
    if voice_speed is None:
        return None
    try:
        return max(0.5, min(2.0, float(voice_speed)))
    except (TypeError, ValueError):
        return None


def _telnyx_tuning_params(voice_speed: float | None) -> dict[str, Any]:
    params: dict[str, Any] = {"response_format": "mp3", "sampling_rate": 24000}
    clamped = _clamp_voice_speed(voice_speed)
    if clamped is not None:
        params["voice_speed"] = clamped
    return params


def parse_telnyx_tts_error(response: httpx.Response) -> str:
    """Extract a human-readable message from a Telnyx TTS error response."""
    try:
        body = response.json()
        if isinstance(body, dict):
            errors = body.get("errors")
            if isinstance(errors, list) and errors:
                parts: list[str] = []
                for err in errors:
                    if isinstance(err, dict):
                        detail = str(err.get("detail") or err.get("title") or "").strip()
                        if detail:
                            parts.append(detail)
                if parts:
                    return "; ".join(parts)
            for key in ("detail", "message", "error"):
                val = body.get(key)
                if val:
                    return str(val)
    except Exception:
        pass
    text = (response.text or "").strip()
    if text and len(text) <= 500:
        return text
    return f"HTTP {response.status_code}"


def _extract_audio(response: httpx.Response, *, output_type: str) -> bytes:
    content_type = (response.headers.get("content-type") or "").lower()
    if output_type == "base64_output" or "application/json" in content_type:
        try:
            body = response.json()
        except Exception:
            body = {}
        audio_b64 = ""
        if isinstance(body, dict):
            audio_b64 = str(body.get("base64_audio") or "").strip()
            data = body.get("data")
            if not audio_b64 and isinstance(data, dict):
                audio_b64 = str(data.get("base64_audio") or "").strip()
        if not audio_b64:
            raise ValueError("Telnyx TTS returned no base64 audio")
        return base64.b64decode(audio_b64)
    if response.content:
        return bytes(response.content)
    raise ValueError("Telnyx TTS returned no audio")


def _audio_mime(response: httpx.Response) -> str:
    content_type = (response.headers.get("content-type") or "").lower()
    if "wav" in content_type:
        return "audio/wav"
    return "audio/mpeg"


def _endpoint_order(voice: str) -> list[tuple[str, str]]:
    """Return (url, payload_style) pairs in try order."""
    is_ultra = ".ultra." in str(voice or "").lower()
    if is_ultra:
        return [
            (f"{TELNYX_API_BASE}/text-to-speech/speech", "native"),
            (f"{TELNYX_API_BASE}/text-to-speech", "native"),
            (f"{TELNYX_API_BASE}/audio/speech", "openai"),
        ]
    return [
        (f"{TELNYX_API_BASE}/text-to-speech", "native"),
        (f"{TELNYX_API_BASE}/text-to-speech/speech", "native"),
        (f"{TELNYX_API_BASE}/audio/speech", "openai"),
    ]


def _native_payloads(
    text: str,
    voice: str,
    voice_speed: float | None,
    *,
    output_type: str,
) -> list[dict[str, Any]]:
    minimal: dict[str, Any] = {
        "text": text,
        "voice": voice,
        "output_type": output_type,
    }
    tuned = dict(minimal)
    tuned["telnyx"] = _telnyx_tuning_params(voice_speed)
    return [minimal, tuned]


def _openai_payload(text: str, voice: str) -> dict[str, Any]:
    return {
        "model": "tts-1-hd",
        "voice": voice,
        "input": text,
    }


def _request_headers(*, output_type: str) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if output_type == "base64_output":
        headers["Accept"] = "application/json"
    else:
        headers["Accept"] = "audio/mpeg, application/json;q=0.9, */*;q=0.8"
    return headers


def _post_once(
    client: httpx.Client,
    *,
    url: str,
    payload: dict[str, Any],
    api_key: str,
    output_type: str,
) -> tuple[bytes, str]:
    headers = _request_headers(output_type=output_type)
    headers["Authorization"] = f"Bearer {api_key}"
    response = client.post(url, json=payload, headers=headers)
    if response.status_code >= 400:
        detail = parse_telnyx_tts_error(response)
        raise httpx.HTTPStatusError(
            f"{detail} (HTTP {response.status_code} for {url})",
            request=response.request,
            response=response,
        )
    audio = _extract_audio(response, output_type=output_type)
    return audio, _audio_mime(response)


def _attempt_synthesis(
    client: httpx.Client,
    *,
    url: str,
    style: str,
    text: str,
    voice: str,
    voice_speed: float | None,
    api_key: str,
) -> tuple[bytes, str, str]:
    """Try base64 then binary output. Returns (audio, mime, output_type_used)."""
    last_exc: Exception | None = None
    if style == "openai":
        payload = _openai_payload(text, voice)
        for output_type in ("binary_output", "base64_output"):
            try:
                audio, mime = _post_once(
                    client,
                    url=url,
                    payload=payload,
                    api_key=api_key,
                    output_type=output_type,
                )
                return audio, mime, output_type
            except httpx.HTTPStatusError as exc:
                last_exc = exc
                if exc.response is not None and exc.response.status_code == 404:
                    raise
                continue
        if last_exc is not None:
            raise last_exc
        raise ValueError("Telnyx TTS OpenAI-compat request failed")

    for output_type in ("base64_output", "binary_output"):
        for payload in _native_payloads(text, voice, voice_speed, output_type=output_type):
            try:
                audio, mime = _post_once(
                    client,
                    url=url,
                    payload=payload,
                    api_key=api_key,
                    output_type=output_type,
                )
                return audio, mime, output_type
            except httpx.HTTPStatusError as exc:
                last_exc = exc
                if exc.response is not None and exc.response.status_code == 404:
                    raise
                continue
            except ValueError as exc:
                last_exc = exc
                continue
    if last_exc is not None:
        raise last_exc
    raise ValueError("Telnyx TTS native request failed")


def synthesize_telnyx_speech(
    db: Session,
    *,
    text: str,
    voice: str,
    voice_speed: float | None = None,
) -> dict[str, Any]:
    clean_text = str(text or "").strip()
    clean_voice = str(voice or "").strip()
    if not clean_text:
        raise ValueError("Text is required for Telnyx TTS")
    if not clean_voice:
        raise ValueError("Telnyx voice identifier is required")

    api_key, _source = require_telnyx_api_key(db)
    started = time.perf_counter()
    errors: list[str] = []

    with httpx.Client(timeout=45.0, verify=httpx_ssl_verify()) as client:
        for url, style in _endpoint_order(clean_voice):
            try:
                audio, mime, _output_type = _attempt_synthesis(
                    client,
                    url=url,
                    style=style,
                    text=clean_text,
                    voice=clean_voice,
                    voice_speed=voice_speed,
                    api_key=api_key,
                )
                return {
                    "ok": True,
                    "audio_data": audio,
                    "audio_mime": mime,
                    "voice_id": clean_voice,
                    "timings": {"telnyx_tts_ms": int((time.perf_counter() - started) * 1000)},
                }
            except httpx.HTTPStatusError as exc:
                msg = str(exc)
                if exc.response is not None and exc.response.status_code == 404:
                    errors.append(f"{url}: not found")
                    continue
                raise ValueError(f"Could not generate voice sample: {msg}") from exc
            except ValueError as exc:
                errors.append(f"{url}: {exc}")
                continue

    hint = (
        "Telnyx Text-to-Speech REST API is not reachable with this API key. "
        "Live interview calls still use the assistant voice on Telnyx; preview needs REST TTS. "
        "Check Telnyx Portal -> API Keys (same account as AI Assistants) and enable Text-to-Speech, "
        "or contact Telnyx support if all endpoints return 404."
    )
    if errors:
        hint = f"{hint} Attempts: {'; '.join(errors)}"
    raise ValueError(hint)


def probe_telnyx_tts_access(
    db: Session,
    *,
    ultra_voice: str | None = None,
) -> dict[str, Any]:
    """Read-only smoke test for Telnyx TTS REST endpoints (for diagnose script)."""
    from app.services.telnyx_api_key import resolve_telnyx_api_key

    api_key, source = resolve_telnyx_api_key(db)
    fp = telnyx_key_fingerprint(api_key)
    result: dict[str, Any] = {
        "key_source": source,
        "key_fingerprint": fp,
        "voices_list": None,
        "endpoint_tests": [],
        "verdict": "unknown",
    }

    if not fp.get("looks_valid"):
        result["verdict"] = "invalid_api_key"
        return result

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
    }

    with httpx.Client(timeout=30.0, verify=httpx_ssl_verify()) as client:
        voices_url = f"{TELNYX_API_BASE}/text-to-speech/voices?provider=telnyx"
        try:
            voices_resp = client.get(voices_url, headers=headers)
            if voices_resp.status_code == 200:
                try:
                    body = voices_resp.json()
                except Exception:
                    body = {}
                voices = body.get("voices") if isinstance(body, dict) else None
                count = len(voices) if isinstance(voices, list) else 0
                result["voices_list"] = {"ok": True, "count": count, "url": voices_url}
            else:
                result["voices_list"] = {
                    "ok": False,
                    "status": voices_resp.status_code,
                    "detail": parse_telnyx_tts_error(voices_resp),
                    "url": voices_url,
                }
        except Exception as exc:  # noqa: BLE001
            result["voices_list"] = {"ok": False, "error": str(exc), "url": voices_url}

        for label, voice in (
            ("stock", STOCK_PROBE_VOICE),
            ("ultra", str(ultra_voice or "").strip() or None),
        ):
            if not voice:
                continue
            for url, style in _endpoint_order(voice):
                entry: dict[str, Any] = {"label": label, "voice": voice, "url": url, "style": style}
                try:
                    audio, mime, output_type = _attempt_synthesis(
                        client,
                        url=url,
                        style=style,
                        text=_PROBE_TEXT,
                        voice=voice,
                        voice_speed=None,
                        api_key=api_key,
                    )
                    entry.update({"ok": True, "bytes": len(audio), "mime": mime, "output_type": output_type})
                    result["endpoint_tests"].append(entry)
                    break
                except httpx.HTTPStatusError as exc:
                    status = exc.response.status_code if exc.response is not None else None
                    entry.update({"ok": False, "status": status, "error": str(exc)})
                    if status == 404:
                        result["endpoint_tests"].append(entry)
                        continue
                    result["endpoint_tests"].append(entry)
                    break
                except Exception as exc:  # noqa: BLE001
                    entry.update({"ok": False, "error": str(exc)})
                    result["endpoint_tests"].append(entry)
                    break

    any_ok = any(t.get("ok") for t in result["endpoint_tests"])
    stock_ok = any(t.get("ok") and t.get("label") == "stock" for t in result["endpoint_tests"])
    ultra_test = next((t for t in result["endpoint_tests"] if t.get("label") == "ultra"), None)
    ultra_ran = ultra_test is not None
    ultra_ok = bool(ultra_test and ultra_test.get("ok"))
    all_404 = bool(result["endpoint_tests"]) and all(
        t.get("status") == 404 or (not t.get("ok") and "not found" in str(t.get("error", "")).lower())
        for t in result["endpoint_tests"]
        if not t.get("ok")
    )
    if ultra_ran and stock_ok and not ultra_ok:
        result["verdict"] = "tts_stock_only"
    elif any_ok:
        result["verdict"] = "tts_api_reachable"
    elif all_404:
        result["verdict"] = "tts_api_404"
    elif result["endpoint_tests"]:
        result["verdict"] = "tts_api_error"
    else:
        result["verdict"] = "no_tests_run"
    return result
