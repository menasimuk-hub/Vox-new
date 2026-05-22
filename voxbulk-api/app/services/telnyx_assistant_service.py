from __future__ import annotations

import re
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.core.http_ssl import httpx_ssl_verify
from app.services.telnyx_api_key import require_telnyx_api_key

RECORDING_SUFFIX = "This call is recorded for quality — see voxbulk.com for privacy."


def build_agent_greeting(agent_name: str) -> str:
    name = str(agent_name or "").strip() or "VoxBulk"
    return f"Hello, this is {name}. {RECORDING_SUFFIX}"


def _telnyx_headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def normalize_telnyx_assistant_id(assistant_id: str) -> str:
    clean = str(assistant_id or "").strip()
    if not clean:
        raise ValueError("Telnyx assistant ID is required")
    if clean.startswith("assistant-"):
        return clean
    return f"assistant-{clean}"


def fetch_telnyx_assistant(db: Session, assistant_id: str) -> dict[str, Any]:
    """Load a Telnyx AI assistant (instructions, greeting, voice, etc.)."""
    clean_id = normalize_telnyx_assistant_id(assistant_id)
    api_key, _source = require_telnyx_api_key(db)
    url = f"https://api.telnyx.com/v2/ai/assistants/{clean_id}"
    with httpx.Client(timeout=20.0, verify=httpx_ssl_verify()) as client:
        response = client.get(url, headers=_telnyx_headers(api_key))
    response.raise_for_status()
    payload = response.json()
    data = payload.get("data") if isinstance(payload, dict) else None
    if isinstance(data, dict):
        return data
    if isinstance(payload, dict):
        return payload
    return {}


def _voice_settings_dict(assistant: dict[str, Any]) -> dict[str, Any]:
    raw = assistant.get("voice_settings")
    return raw if isinstance(raw, dict) else {}


def resolve_telnyx_assistant_runtime(db: Session, assistant_id: str) -> dict[str, Any]:
    """Map Telnyx portal assistant → instructions, greeting, and TTS voice for browser calls."""
    assistant = fetch_telnyx_assistant(db, assistant_id)
    voice_settings = _voice_settings_dict(assistant)
    voice = str(voice_settings.get("voice") or "").strip()
    instructions = str(assistant.get("instructions") or assistant.get("instruction") or "").strip()
    greeting = str(assistant.get("greeting") or "").strip() or None

    voice_speed = voice_settings.get("voice_speed")
    if voice_speed is None:
        voice_speed = voice_settings.get("speed")

    tts_provider = "telnyx"
    elevenlabs_voice_id = ""
    elevenlabs_voice_settings: dict[str, Any] = {}
    if voice.lower().startswith("telnyx."):
        tts_provider = "telnyx"
    elif voice_settings.get("api_key_ref") or (voice and "." not in voice and len(voice) >= 10):
        tts_provider = "elevenlabs"
        elevenlabs_voice_id = voice
        for key in ("stability", "similarity_boost", "style", "speed", "temperature", "use_speaker_boost"):
            if voice_settings.get(key) is not None:
                elevenlabs_voice_settings[key] = voice_settings.get(key)

    return {
        "assistant_id": assistant_id,
        "assistant_name": str(assistant.get("name") or "").strip(),
        "instructions": instructions,
        "greeting": greeting,
        "voice": voice,
        "voice_speed": voice_speed,
        "tts_provider": tts_provider,
        "elevenlabs_voice_id": elevenlabs_voice_id,
        "elevenlabs_voice_settings": elevenlabs_voice_settings,
        "model": str(assistant.get("model") or "").strip(),
    }


def telnyx_assistant_instructions(db: Session, assistant_id: str) -> str:
    return str(resolve_telnyx_assistant_runtime(db, assistant_id).get("instructions") or "").strip()


def telnyx_assistant_greeting(db: Session, assistant_id: str) -> str | None:
    greeting = str(resolve_telnyx_assistant_runtime(db, assistant_id).get("greeting") or "").strip()
    return greeting or None


def _update_telnyx_assistant(db: Session, assistant_id: str, body: dict[str, Any]) -> dict[str, Any]:
    clean_id = normalize_telnyx_assistant_id(assistant_id)
    api_key, _source = require_telnyx_api_key(db)
    url = f"https://api.telnyx.com/v2/ai/assistants/{clean_id}"
    payload = dict(body)
    if "promote_to_main" not in payload:
        payload["promote_to_main"] = True
    with httpx.Client(timeout=30.0, verify=httpx_ssl_verify()) as client:
        response = client.post(url, json=payload, headers=_telnyx_headers(api_key))
    response.raise_for_status()
    payload = response.json()
    data = payload.get("data") if isinstance(payload, dict) else None
    return data if isinstance(data, dict) else (payload if isinstance(payload, dict) else {})


def _telephony_with_web_and_dual_recording(existing: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    telephony = dict(existing.get("telephony_settings") or {}) if isinstance(existing.get("telephony_settings"), dict) else {}
    changed = False
    if not telephony.get("supports_unauthenticated_web_calls"):
        telephony["supports_unauthenticated_web_calls"] = True
        changed = True
    recording = dict(telephony.get("recording_settings") or {})
    if str(recording.get("channels") or "").strip().lower() != "dual":
        recording["channels"] = "dual"
        changed = True
    if not str(recording.get("file_format") or "").strip():
        recording["file_format"] = "wav"
        changed = True
    telephony["recording_settings"] = recording
    return telephony, changed


def enable_telnyx_assistant_web_calls(db: Session, assistant_id: str) -> dict[str, Any]:
    """Turn on browser/WebRTC and dual-channel call recording for this assistant."""
    clean_id = normalize_telnyx_assistant_id(assistant_id)
    existing = fetch_telnyx_assistant(db, clean_id)
    telephony, changed = _telephony_with_web_and_dual_recording(existing)
    if not changed:
        return existing
    return _update_telnyx_assistant(db, clean_id, {"telephony_settings": telephony})


def ensure_telnyx_webrtc_call_ready(db: Session, assistant_id: str) -> dict[str, Any]:
    """Fast pre-call setup: web calls + dual recording only (no instruction sync)."""
    clean_id = normalize_telnyx_assistant_id(assistant_id)
    existing = fetch_telnyx_assistant(db, clean_id)
    telephony, changed = _telephony_with_web_and_dual_recording(existing)
    if changed:
        _update_telnyx_assistant(db, clean_id, {"telephony_settings": telephony})
    return {
        "assistant_id": clean_id,
        "web_calls_enabled": bool(telephony.get("supports_unauthenticated_web_calls")),
        "recording_channels": str((telephony.get("recording_settings") or {}).get("channels") or "dual"),
    }


def extract_agent_name_from_prompt(instructions: str) -> str:
    """Extract agent name from system prompt. Returns 'VoxBulk' if not found."""
    text = str(instructions or "")
    patterns = [
        r"your name is\s+([A-Za-z][A-Za-z'-]{0,30})",
        r"you are\s+([A-Za-z][A-Za-z'-]{0,30})",
        r"I am\s+([A-Za-z][A-Za-z'-]{0,30})",
        r"my name is\s+([A-Za-z][A-Za-z'-]{0,30})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            return match.group(1).strip()
    return "VoxBulk"


def personalize_greeting(greeting: str, *, first_name: str | None = None) -> str:
    """Apply {{first_name}} and common Hi there placeholders."""
    first = str(first_name or "").strip().split()[0] if str(first_name or "").strip() else "there"
    text = str(greeting or "").strip()
    if not text:
        return ""
    return (
        text.replace("{{first_name}}", first)
        .replace("Hi there,", f"Hi {first},")
        .replace("Hi there", f"Hi {first}")
        .replace("Hi,", f"Hi {first},")
    )


def sync_telnyx_assistant_instructions(
    db: Session,
    assistant_id: str,
    instructions: str,
    *,
    greeting: str | None = None,
    sync_greeting: bool = True,
    enable_web_calls: bool = True,
) -> dict[str, Any]:
    """Push admin system prompt (and optional greeting) to the Telnyx assistant."""
    clean_id = normalize_telnyx_assistant_id(assistant_id)
    clean_instructions = str(instructions or "").strip()
    if not clean_instructions:
        raise ValueError("System prompt is required to sync to Telnyx")
    if enable_web_calls:
        enable_telnyx_assistant_web_calls(db, clean_id)
    body: dict[str, Any] = {"instructions": clean_instructions, "promote_to_main": True, "include_transcript": True}
    pushed_greeting = ""
    if sync_greeting:
        pushed_greeting = str(greeting or "").strip()
        if pushed_greeting:
            body["greeting"] = pushed_greeting
    updated = _update_telnyx_assistant(db, clean_id, body)
    live = resolve_telnyx_assistant_runtime(db, clean_id)
    live_instructions = str(live.get("instructions") or "").strip()
    live_greeting = str(live.get("greeting") or "").strip()
    if live_instructions != clean_instructions:
        raise ValueError(
            "Telnyx did not save instructions — live text differs after sync. "
            "Check assistant ID and API key in Integrations."
        )
    if pushed_greeting and live_greeting != pushed_greeting:
        raise ValueError(
            f"Telnyx did not save greeting ({len(pushed_greeting)} chars pushed, {len(live_greeting)} live). "
            "Save your greeting in admin and try again."
        )
    return {
        **updated,
        "verified_instructions_chars": len(live_instructions),
        "verified_greeting": live_greeting,
        "verified_greeting_chars": len(live_greeting),
        "greeting_pushed": bool(pushed_greeting),
    }


def prepare_telnyx_webrtc_call(
    db: Session,
    assistant_id: str,
    instructions: str,
    *,
    greeting: str | None = None,
) -> dict[str, Any]:
    """Sync prompt + greeting to Telnyx and enable browser WebRTC before the client connects."""
    clean_id = normalize_telnyx_assistant_id(assistant_id)
    clean_instructions = str(instructions or "").strip()
    if not clean_instructions:
        raise ValueError("Save a system prompt in admin → Front page call leads.")
    try:
        sync_telnyx_assistant_instructions(db, clean_id, clean_instructions, greeting=greeting)
    except httpx.HTTPStatusError as exc:
        detail = ""
        try:
            detail = str(exc.response.json())
        except Exception:
            detail = exc.response.text if exc.response is not None else str(exc)
        raise ValueError(f"Telnyx could not update the assistant: {detail}") from exc
    ready = ensure_telnyx_webrtc_call_ready(db, clean_id)
    return {**ready, "prompt_synced": True}


def background_sync_telnyx_assistant_instructions(assistant_id: str, instructions: str) -> None:
    """Best-effort prompt sync after the browser call has already started."""
    from app.core.database import get_sessionmaker

    clean_instructions = str(instructions or "").strip()
    if not clean_instructions:
        return
    sessionmaker = get_sessionmaker()
    with sessionmaker() as db:
        try:
            sync_telnyx_assistant_instructions(db, assistant_id, clean_instructions)
        except Exception:
            pass


def telnyx_assistant_web_calls_enabled(assistant: dict[str, Any]) -> bool:
    telephony = assistant.get("telephony_settings")
    if not isinstance(telephony, dict):
        return False
    return bool(telephony.get("supports_unauthenticated_web_calls"))
