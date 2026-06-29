from __future__ import annotations

import logging
import re
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.core.http_ssl import httpx_ssl_verify
from app.services.telnyx_api_key import require_telnyx_api_key

logger = logging.getLogger(__name__)

RECORDING_SUFFIX = "This call is recorded for quality — see voxbulk.com for privacy."


def build_agent_greeting(agent_name: str) -> str:
    name = str(agent_name or "").strip() or "VoxBulk"
    return f"Hello, this is {name}. {RECORDING_SUFFIX}"


def normalize_saved_telnyx_greeting(saved_greeting: str | None) -> str:
    """Ignore legacy DB values that are only the recording suffix (pre–Hello, this is X format)."""
    saved = str(saved_greeting or "").strip()
    if saved == RECORDING_SUFFIX:
        return ""
    return saved


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


# Telnyx STT for Arabic calls. We use `azure/fast`, which Telnyx now provides KEYLESS
# (no customer Azure API key required) and which Telnyx documents as the highest-quality
# Arabic transcription on their platform. `deepgram/flux` is English-only (it cannot
# transcribe Arabic at all), so an Arabic agent on flux SPEAKS Arabic but hears the
# candidate as English and never understands them. Azure needs a region-specific BCP-47
# locale (e.g. `ar-EG`, `ar-SA`) — a bare `ar` is not accepted. We default to Egyptian
# Arabic, which Azure recognises across most Levantine/Gulf speakers too.
_ARABIC_STT_MODEL = "azure/fast"
_ARABIC_STT_LOCALE = "ar-EG"


def _transcription_for_language(existing: dict[str, Any], language: str) -> dict[str, Any] | None:
    """Build a Telnyx ``transcription`` body for the call language, or None if no change.

    For Arabic we switch STT to keyless `azure/fast` with an Arabic locale so the
    assistant actually understands the candidate (flux is English-only). We send only
    ``model`` + ``language`` — flux-specific end-of-turn ``settings`` must NOT be sent to
    Azure (they are Deepgram-only and cause Telnyx to reject the update).
    """
    lang = str(language or "").strip().lower()
    if not lang or not lang.startswith("ar"):
        return None
    current = existing.get("transcription") if isinstance(existing.get("transcription"), dict) else {}
    current_model = str(current.get("model") or "").strip().lower()
    current_lang = str(current.get("language") or "").strip().lower()
    if current_model == _ARABIC_STT_MODEL and current_lang == _ARABIC_STT_LOCALE.lower():
        return None
    return {"model": _ARABIC_STT_MODEL, "language": _ARABIC_STT_LOCALE}


def _voice_settings_for_language(existing: dict[str, Any], language: str) -> dict[str, Any] | None:
    """Set ``language_boost`` for Arabic without changing the portal-configured TTS voice."""
    lang = str(language or "").strip().lower()
    if not lang or not lang.startswith("ar"):
        return None
    current = _voice_settings_dict(existing)
    boost = str(current.get("language_boost") or "").strip().lower()
    if boost in {"ar", "arabic"}:
        return None
    merged = dict(current) if current else {}
    merged["language_boost"] = "ar"
    return merged


def ensure_telnyx_assistant_transcription_language(db: Session, assistant_id: str, language: str) -> dict[str, Any]:
    """Make the assistant transcribe (STT) in the given call language. No-op for English/unknown.

    Used before placing an Arabic interview call so Telnyx understands the candidate.
    """
    clean_id = normalize_telnyx_assistant_id(assistant_id)
    existing = fetch_telnyx_assistant(db, clean_id)
    transcription = _transcription_for_language(existing, language)
    if not transcription:
        return existing
    return _update_telnyx_assistant(db, clean_id, {"transcription": transcription})


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


def _normalize_greeting_for_compare(text: str) -> str:
    """Loose compare — Telnyx may normalize punctuation/whitespace after save."""
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


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
    verify_live: bool = True,
    language: str | None = None,
) -> dict[str, Any]:
    """Push admin system prompt (and optional greeting) to the Telnyx assistant.

    When ``language`` indicates a non-English call (e.g. ``ar``), the assistant's
    speech-to-text language is switched to a model that supports it so the candidate
    is understood in that language.
    """
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
    # Apply language-specific STT/voice as a SEPARATE best-effort update AFTER the main
    # one. A bad transcription value (e.g. a model Telnyx rejects with 400) must never
    # block the instructions+greeting update — otherwise the assistant connects but never
    # speaks. We swallow errors here so the greeting/instructions always get saved.
    if language:
        try:
            existing = fetch_telnyx_assistant(db, clean_id)
            lang_body: dict[str, Any] = {}
            transcription = _transcription_for_language(existing, language)
            if transcription:
                lang_body["transcription"] = transcription
            voice_settings = _voice_settings_for_language(existing, language)
            if voice_settings:
                lang_body["voice_settings"] = voice_settings
            if lang_body:
                try:
                    _update_telnyx_assistant(db, clean_id, lang_body)
                except Exception as exc:
                    logger.warning(
                        "telnyx_lang_settings_update_failed assistant_id=%s body=%s error=%s",
                        clean_id,
                        list(lang_body.keys()),
                        exc,
                    )
        except Exception as exc:
            logger.warning("telnyx_transcription_lang_skip assistant_id=%s error=%s", clean_id, exc)
    updated = _update_telnyx_assistant(db, clean_id, body)
    out: dict[str, Any] = {
        **updated,
        "greeting_pushed": bool(pushed_greeting),
        "verify_live": verify_live,
    }
    if not verify_live:
        return out
    try:
        live = resolve_telnyx_assistant_runtime(db, clean_id)
    except Exception as exc:
        logger.warning(
            "telnyx_assistant_live_verify_skipped assistant_id=%s error=%s",
            clean_id,
            exc,
        )
        out["verify_warning"] = str(exc)
        return out
    live_instructions = str(live.get("instructions") or "").strip()
    live_greeting = str(live.get("greeting") or "").strip()
    out["verified_instructions_chars"] = len(live_instructions)
    out["verified_greeting"] = live_greeting
    out["verified_greeting_chars"] = len(live_greeting)
    if live_instructions != clean_instructions:
        raise ValueError(
            "Telnyx did not save instructions — live text differs after sync. "
            "Check assistant ID and API key in Integrations."
        )
    if pushed_greeting and _normalize_greeting_for_compare(live_greeting) != _normalize_greeting_for_compare(pushed_greeting):
        raise ValueError(
            f"Telnyx did not save greeting ({len(pushed_greeting)} chars pushed, {len(live_greeting)} live). "
            "Save your greeting in admin and try again."
        )
    return out


def prepare_telnyx_webrtc_call(
    db: Session,
    assistant_id: str,
    instructions: str,
    *,
    greeting: str | None = None,
    language: str | None = None,
) -> dict[str, Any]:
    """Sync prompt + greeting to Telnyx and enable browser WebRTC before the client connects."""
    clean_id = normalize_telnyx_assistant_id(assistant_id)
    clean_instructions = str(instructions or "").strip()
    if not clean_instructions:
        raise ValueError("Save a system prompt in admin → Front page call leads.")
    try:
        sync_telnyx_assistant_instructions(db, clean_id, clean_instructions, greeting=greeting, language=language)
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
