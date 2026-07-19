from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.core.http_ssl import httpx_ssl_verify
from app.services.telnyx_api_key import require_telnyx_api_key

logger = logging.getLogger(__name__)

DEFAULT_TELNYX_ASSISTANT_MODEL = "openai/gpt-4o"

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


def parse_telnyx_assistant_voice(
    voice: str,
    *,
    voice_settings: dict[str, Any] | None = None,
) -> tuple[str, str, dict[str, Any]]:
    """Map Telnyx voice_settings.voice → (tts_provider, elevenlabs_voice_id, extras).

    Telnyx portal uses composite IDs such as ``ElevenLabs.eleven_flash_v2_5.{voice_id}``.
    Direct ElevenLabs integrations may store only the raw voice id with ``api_key_ref`` set.
    """
    raw = str(voice or "").strip()
    settings = voice_settings if isinstance(voice_settings, dict) else {}
    extras: dict[str, Any] = {}

    if not raw:
        return "telnyx", "", extras

    lower = raw.lower()
    if lower.startswith("telnyx."):
        return "telnyx", "", extras

    if lower.startswith("elevenlabs."):
        parts = raw.split(".")
        if len(parts) >= 3:
            extras["model_id"] = parts[1]
            return "elevenlabs", parts[-1], extras
        if len(parts) == 2 and parts[1].strip():
            return "elevenlabs", parts[1].strip(), extras

    if settings.get("api_key_ref") or ("." not in raw and len(raw) >= 10):
        return "elevenlabs", raw, extras

    return "telnyx", "", extras


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

    tts_provider, elevenlabs_voice_id, voice_extras = parse_telnyx_assistant_voice(
        voice, voice_settings=voice_settings
    )
    elevenlabs_voice_settings: dict[str, Any] = dict(voice_extras)
    if tts_provider == "elevenlabs":
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


def _telnyx_response_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
        if isinstance(payload, dict):
            errors = payload.get("errors")
            if errors:
                return str(errors)
            return str(payload)
    except Exception:
        pass
    return response.text or f"HTTP {response.status_code}"


def template_assistant_create_defaults(db: Session, template_assistant_id: str) -> dict[str, Any]:
    """Clone model + voice from an existing working Telnyx assistant (e.g. Leo)."""
    assistant = fetch_telnyx_assistant(db, template_assistant_id)
    voice_settings = _voice_settings_dict(assistant)
    out_voice: dict[str, Any] | None = None
    if voice_settings.get("voice"):
        out_voice = {"voice": voice_settings.get("voice")}
        for key in ("voice_speed", "speed", "api_key_ref"):
            if voice_settings.get(key) is not None:
                out_voice[key] = voice_settings.get(key)
    model = str(assistant.get("model") or DEFAULT_TELNYX_ASSISTANT_MODEL).strip()
    return {"model": model, "voice_settings": out_voice}


def create_telnyx_assistant(
    db: Session,
    *,
    name: str,
    instructions: str,
    model: str | None = None,
    greeting: str | None = None,
    voice_settings: dict[str, Any] | None = None,
    telephony_settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a Telnyx AI assistant. Returns assistant payload including id."""
    del telephony_settings  # applied post-create via enable_telnyx_assistant_web_calls
    clean_name = str(name or "").strip()
    clean_instructions = str(instructions or "").strip()
    if not clean_name:
        raise ValueError("Assistant name is required")
    if not clean_instructions:
        raise ValueError("Assistant instructions are required")

    api_key, _source = require_telnyx_api_key(db)
    url = "https://api.telnyx.com/v2/ai/assistants"
    body: dict[str, Any] = {
        "name": clean_name,
        "model": str(model or DEFAULT_TELNYX_ASSISTANT_MODEL).strip(),
        "instructions": clean_instructions,
    }
    if greeting:
        body["greeting"] = str(greeting).strip()
    if voice_settings:
        body["voice_settings"] = dict(voice_settings)

    with httpx.Client(timeout=30.0, verify=httpx_ssl_verify()) as client:
        response = client.post(url, json=body, headers=_telnyx_headers(api_key))
    if response.status_code >= 400:
        raise ValueError(
            f"Telnyx assistant create failed ({response.status_code}): {_telnyx_response_detail(response)}"
        )
    payload = response.json()
    data = payload.get("data") if isinstance(payload, dict) else None
    created = data if isinstance(data, dict) else (payload if isinstance(payload, dict) else {})
    assistant_id = str(created.get("id") or "").strip()
    if assistant_id:
        enable_telnyx_assistant_web_calls(db, assistant_id)
    return created


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
# locale (e.g. `ar-EG`, `ar-SA`) — a bare `ar` is not accepted. We default to Saudi
# Arabic (Gulf-oriented) for STT on interview/survey calls targeting UAE/KSA speakers.
#
# Telnyx also requires a supported Azure ``region`` for `azure/fast`. Omitting it (or
# leaving region=null) makes `ai_assistant_start` fail with HTTP 422 and the candidate
# hears silence — no agent voice. Keep this list aligned with Telnyx's Azure STT docs.
_ARABIC_STT_MODEL = "azure/fast"
_ARABIC_STT_LOCALE = "ar-SA"
_ARABIC_STT_REGION = "westeurope"
# English interview assistants default to Deepgram Flux (English-only). Used when clearing
# sticky Arabic Azure STT left behind by a prior Arabic call/test.
_ENGLISH_STT_MODEL = "deepgram/flux"
_ENGLISH_STT_LOCALE = "en"
_AZURE_STT_REGIONS = frozenset(
    {
        "australiaeast",
        "centralindia",
        "eastus",
        "northcentralus",
        "westeurope",
        "westus2",
        "latency",
    }
)


def _transcription_for_language(existing: dict[str, Any], language: str) -> dict[str, Any] | None:
    """Build a Telnyx ``transcription`` body for the call language, or None if no change.

    For Arabic we switch STT to keyless `azure/fast` with an Arabic locale so the
    assistant actually understands the candidate (flux is English-only). We send
    ``model`` + ``language`` + ``region`` — flux-specific end-of-turn ``settings`` must
    NOT be sent to Azure (they are Deepgram-only and cause Telnyx to reject the update).
    Region is mandatory: without it Telnyx rejects starting the assistant on the call.

    For English we clear sticky Arabic Azure STT (``ar-SA``) back to Deepgram Flux so EN
    agents do not keep hearing Arabic after a prior Arabic sync/test.
    """
    lang = str(language or "").strip().lower()
    if not lang:
        return None
    current = existing.get("transcription") if isinstance(existing.get("transcription"), dict) else {}
    current_model = str(current.get("model") or "").strip().lower()
    current_lang = str(current.get("language") or "").strip().lower()
    current_region = str(current.get("region") or "").strip().lower()

    if lang.startswith("ar"):
        region = current_region if current_region in _AZURE_STT_REGIONS else _ARABIC_STT_REGION
        if (
            current_model == _ARABIC_STT_MODEL
            and current_lang == _ARABIC_STT_LOCALE.lower()
            and current_region == region
        ):
            return None
        return {"model": _ARABIC_STT_MODEL, "language": _ARABIC_STT_LOCALE, "region": region}

    # English (or other non-Arabic): undo sticky Arabic Azure STT.
    sticky_ar = current_lang.startswith("ar") or (
        current_model.startswith("azure/") and current_lang.startswith("ar")
    )
    if not sticky_ar:
        return None
    if current_model == _ENGLISH_STT_MODEL and current_lang in {"en", "en-gb", "en-us", "en_gb", "en_us"}:
        return None
    return {"model": _ENGLISH_STT_MODEL, "language": _ENGLISH_STT_LOCALE}


def _voice_settings_for_language(existing: dict[str, Any], language: str) -> dict[str, Any] | None:
    """Set or clear ``language_boost`` for Arabic on Telnyx-native TTS only.

    ElevenLabs voices on Telnyx reject a merged ``voice_settings`` PATCH (400) — the
    Sultan voice is already Arabic-capable via ElevenLabs multilingual models.
    """
    lang = str(language or "").strip().lower()
    if not lang:
        return None
    current = _voice_settings_dict(existing)
    voice = str(current.get("voice") or "").strip()
    tts_provider, _vid, _extras = parse_telnyx_assistant_voice(voice, voice_settings=current)
    if tts_provider == "elevenlabs":
        return None

    boost = str(current.get("language_boost") or "").strip().lower()
    if lang.startswith("ar"):
        if boost in {"ar", "arabic"}:
            return None
        patch: dict[str, Any] = {"language_boost": "ar"}
        if voice:
            patch["voice"] = voice
        if current.get("voice_speed") is not None:
            patch["voice_speed"] = current["voice_speed"]
        return patch

    # English: clear sticky Arabic boost on Telnyx-native voices.
    if boost not in {"ar", "arabic"}:
        return None
    patch = {"language_boost": "English"}
    if voice:
        patch["voice"] = voice
    if current.get("voice_speed") is not None:
        patch["voice_speed"] = current["voice_speed"]
    return patch


def ensure_telnyx_assistant_transcription_language(db: Session, assistant_id: str, language: str) -> dict[str, Any]:
    """Align assistant STT (and Telnyx-native language_boost) with the call language.

    Arabic → azure/fast + ar-SA + region. English → clear sticky Arabic STT/boost.
    """
    clean_id = normalize_telnyx_assistant_id(assistant_id)
    existing = fetch_telnyx_assistant(db, clean_id)
    body: dict[str, Any] = {}
    transcription = _transcription_for_language(existing, language)
    if transcription:
        body["transcription"] = transcription
    voice_settings = _voice_settings_for_language(existing, language)
    if voice_settings:
        body["voice_settings"] = voice_settings
    if not body:
        return existing
    return _update_telnyx_assistant(db, clean_id, body)


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


def apply_interview_assistant_pacing(
    db: Session,
    assistant_id: str,
    *,
    voice_speed: float | None = None,
) -> dict[str, Any]:
    """Tune turn-taking and TTS so the agent sounds natural on the phone.

    ElevenLabs Flash at 1.0 often feels slow/bot-like on PSTN — prefer ~1.12.
    NaturalHD at 1.0 often sounded slow/"drunk" — prefer ~1.15–1.2.
    Do not use 0.8 (robotic slow). Clamp stays 0.85–1.25.
    """
    clean_id = normalize_telnyx_assistant_id(assistant_id)
    existing = fetch_telnyx_assistant(db, clean_id)
    current = _voice_settings_dict(existing)
    voice = str(current.get("voice") or "").strip()
    tts_provider, _vid, _extras = parse_telnyx_assistant_voice(voice, voice_settings=current)
    # Provider-aware defaults when caller does not pass an explicit speed.
    if voice_speed is None:
        target = 1.2 if (tts_provider == "telnyx" and "naturalhd" in voice.lower()) else 1.12
    else:
        target = float(voice_speed)
    if tts_provider == "telnyx" and "naturalhd" in voice.lower():
        target = max(target, 1.15)
    clamped = max(0.85, min(1.25, target))

    # Minimal PATCH — do not resend the full voice_settings blob (Telnyx 400s on extras).
    # Always set voice_speed explicitly: Telnyx Natural uses it, and some ElevenLabs
    # assistants keep a stale voice_speed that still slows playback if left at 0.8.
    if tts_provider == "elevenlabs":
        voice_patch: dict[str, Any] = {
            "speed": clamped,
            "voice_speed": clamped,
            # Slightly more expressive on phone (less flat “bot” delivery).
            "stability": 0.48,
            "similarity_boost": 0.78,
            "style": 0.28,
            "use_speaker_boost": True,
        }
        if voice:
            voice_patch["voice"] = voice
        if current.get("api_key_ref"):
            voice_patch["api_key_ref"] = current["api_key_ref"]
    else:
        voice_patch = {"voice_speed": clamped}
        if voice:
            voice_patch["voice"] = voice

    # Allow barge-in; keep endpointing snappy so side questions are heard.
    interruption_settings = {
        "enable": True,
        "disable_greeting_interruption": False,
        "interrupt_prediction_threshold": 0.5,
        "start_speaking_plan": {
            "wait_seconds": 0.4,
            "transcription_endpointing_plan": {
                "on_punctuation_seconds": 0.35,
                "on_no_punctuation_seconds": 0.9,
                "on_number_seconds": 0.65,
            },
        },
    }
    out: dict[str, Any] = {"assistant_id": clean_id, "tts_provider": tts_provider}
    try:
        _update_telnyx_assistant(db, clean_id, {"voice_settings": voice_patch})
        out["voice_settings"] = voice_patch
    except Exception as exc:
        logger.warning("interview_pacing_voice_failed assistant_id=%s err=%s", clean_id, exc)
        out["voice_error"] = str(exc)
        # Retry without ElevenLabs extras if Telnyx rejects the richer patch.
        if tts_provider == "elevenlabs":
            try:
                minimal = {"speed": clamped, "voice_speed": clamped}
                if voice:
                    minimal["voice"] = voice
                if current.get("api_key_ref"):
                    minimal["api_key_ref"] = current["api_key_ref"]
                _update_telnyx_assistant(db, clean_id, {"voice_settings": minimal})
                out["voice_settings"] = minimal
                out.pop("voice_error", None)
            except Exception as exc2:
                out["voice_error"] = str(exc2)
    try:
        _update_telnyx_assistant(db, clean_id, {"interruption_settings": interruption_settings})
        out["interruption_settings"] = interruption_settings
    except Exception as exc:
        logger.warning("interview_pacing_interrupt_failed assistant_id=%s err=%s", clean_id, exc)
        out["interruption_error"] = str(exc)
    try:
        tools_out = ensure_interview_assistant_hangup_tools(db, clean_id, existing=existing)
        out["tools"] = tools_out
    except Exception as exc:
        logger.warning("interview_assistant_tools_sync_failed assistant_id=%s err=%s", clean_id, exc)
        out["tools_error"] = str(exc)
    return out


def ensure_interview_assistant_hangup_tools(
    db: Session,
    assistant_id: str,
    *,
    existing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Ensure built-in Hangup tool is present. Do not add custom webhook tools (Telnyx 400)."""
    clean_id = normalize_telnyx_assistant_id(assistant_id)
    live = existing if isinstance(existing, dict) else fetch_telnyx_assistant(db, clean_id)
    current_tools = live.get("tools") if isinstance(live.get("tools"), list) else []
    blob = json.dumps(current_tools).lower()
    if "hangup" in blob:
        return {
            "ok": True,
            "changed": False,
            "tool_count": len(current_tools),
            "has_hangup": True,
            "webhook_tools_synced": False,
        }

    # Shape verified against live Leo assistant tools in Telnyx.
    hangup_tool = {
        "type": "hangup",
        "hangup": {
            "description": (
                "To be used whenever the conversation has ended and it would be "
                "appropriate to hangup the call."
            )
        },
    }
    desired = list(current_tools) + [hangup_tool]
    try:
        _update_telnyx_assistant(db, clean_id, {"tools": desired})
        return {
            "ok": True,
            "changed": True,
            "tool_count": len(desired),
            "has_hangup": True,
            "webhook_tools_synced": False,
        }
    except Exception as exc:
        logger.warning("ensure_interview_hangup_tool_failed assistant_id=%s err=%s", clean_id, exc)
        return {
            "ok": False,
            "changed": False,
            "tool_count": len(current_tools),
            "has_hangup": False,
            "error": str(exc)[:240],
            "webhook_tools_synced": False,
        }


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
    apply_human_pacing: bool = False,
) -> dict[str, Any]:
    """Push admin system prompt (and optional greeting) to the Telnyx assistant.

    When ``language`` indicates a non-English call (e.g. ``ar``), the assistant's
    speech-to-text language is switched to a model that supports it so the candidate
    is understood in that language.

    When ``apply_human_pacing`` is True, also set normal TTS speed and interview turn-taking.
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
                for patch_key, patch_val in lang_body.items():
                    try:
                        _update_telnyx_assistant(db, clean_id, {patch_key: patch_val})
                    except Exception as exc:
                        logger.warning(
                            "telnyx_lang_settings_update_failed assistant_id=%s body=%s error=%s",
                            clean_id,
                            [patch_key],
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
    if apply_human_pacing:
        try:
            pacing = apply_interview_assistant_pacing(db, clean_id)
            out["human_pacing"] = {
                "voice_ok": not bool(pacing.get("voice_error")),
                "interrupt_ok": not bool(pacing.get("interruption_error")),
                "voice_speed": (pacing.get("voice_settings") or {}).get("voice_speed"),
                "wait_seconds": ((pacing.get("interruption_settings") or {}).get("start_speaking_plan") or {}).get(
                    "wait_seconds"
                ),
            }
        except Exception as exc:
            logger.warning("interview_human_pacing_skip assistant_id=%s err=%s", clean_id, exc)
            out["human_pacing_error"] = str(exc)
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
