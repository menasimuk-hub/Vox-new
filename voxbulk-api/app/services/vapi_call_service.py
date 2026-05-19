from __future__ import annotations

import os
import re
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.services.provider_settings import ProviderSettingsService

_KEY_SWAP_HINT = (
    "In Vapi dashboard → API Keys: Public Key goes in Integrations → Public key; "
    "Private API Key goes in Server API key (or VAPI_API_KEY in .env). Do not swap them."
)


def _vapi_config(db: Session) -> dict[str, Any]:
    cfg, _enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="vapi")
    return cfg or {}


def _probe_public_key(key: str, base_url: str, assistant_id: str) -> bool:
    if not key or not assistant_id:
        return False
    try:
        response = httpx.post(
            f"{base_url}/call/web",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"assistantId": assistant_id},
            timeout=12.0,
        )
    except Exception:
        return False
    return response.status_code != 401


def _probe_private_key(
    key: str,
    base_url: str,
    *,
    call_id: str | None = None,
    assistant_id: str | None = None,
) -> tuple[bool, str | None]:
    if not key:
        return False, None
    url = f"{base_url}/call/{call_id}" if call_id else f"{base_url}/assistant/{assistant_id}" if assistant_id else ""
    if not url:
        return False, None
    try:
        response = httpx.get(url, headers={"Authorization": f"Bearer {key}"}, timeout=12.0)
    except Exception as e:
        return False, str(e)
    if response.status_code == 401:
        return False, response.text[:300] if response.text else "401 Unauthorized"
    return response.is_success, None if response.is_success else response.text[:300]


def resolve_vapi_private_api_key(db: Session, *, provider_call_id: str | None = None) -> tuple[str, str]:
    """Return (private_api_key, base_url) that works for GET /call and GET /assistant."""
    config = _vapi_config(db)
    base_url = str(config.get("base_url") or "https://api.vapi.ai").strip().rstrip("/")
    public_key = str(config.get("public_key") or "").strip()
    assistant_id = str(config.get("assistant_id") or "").strip()
    db_key = str(config.get("api_key") or "").strip()
    env_key = str(get_settings().vapi_api_key or os.getenv("VAPI_API_KEY") or "").strip()

    candidates: list[tuple[str, str]] = []
    if db_key:
        candidates.append(("Integrations → Server API key", db_key))
    if env_key and env_key not in {k for _, k in candidates}:
        candidates.append(("VAPI_API_KEY in .env", env_key))

    if not candidates:
        raise ValueError(
            "Vapi Private API Key is required for transcripts and recordings. "
            "Add it under Integrations → Vapi → Server API key, then Save. "
            + _KEY_SWAP_HINT
        )

    call_id = str(provider_call_id or "").strip() or None
    last_detail = ""
    for label, key in candidates:
        ok, detail = _probe_private_key(
            key,
            base_url,
            call_id=call_id,
            assistant_id=assistant_id if not call_id else None,
        )
        if ok:
            return key, base_url
        last_detail = detail or last_detail

    if db_key:
        if public_key and db_key == public_key:
            raise ValueError(
                "Public key and Server API key are identical. "
                "Paste the Private API Key (not the Public Key) in Server API key. "
                + _KEY_SWAP_HINT
            )
        if _probe_public_key(db_key, base_url, assistant_id):
            raise ValueError(
                "Server API key field contains your Public Key. "
                "Copy the Private API Key from Vapi into Integrations → Vapi → Server API key, then Save. "
                + _KEY_SWAP_HINT
            )

    raise ValueError(
        "Vapi rejected the Private API Key (401). "
        f"Check Integrations → Vapi → Server API key or VAPI_API_KEY in .env. {last_detail or ''} "
        + _KEY_SWAP_HINT
    )


def fetch_vapi_call(db: Session, *, provider_call_id: str) -> tuple[dict[str, Any] | None, str | None]:
    call_id = str(provider_call_id or "").strip()
    if not call_id:
        return None, "Missing Vapi call id"
    try:
        api_key, base_url = resolve_vapi_private_api_key(db, provider_call_id=call_id)
    except ValueError as e:
        return None, str(e)
    try:
        response = httpx.get(
            f"{base_url}/call/{call_id}",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=25.0,
        )
    except Exception as e:
        return None, f"Vapi request failed: {e}"
    if not response.is_success:
        detail = response.text[:300] if response.text else ""
        if response.status_code == 401:
            return None, f"Vapi returned 401 — {detail}. " + _KEY_SWAP_HINT
        return None, f"Vapi returned {response.status_code}" + (f" — {detail}" if detail else "")
    body = response.json()
    return (body if isinstance(body, dict) else None), None


def _message_text(msg: dict[str, Any]) -> str:
    raw = msg.get("message")
    if isinstance(raw, str):
        return raw.strip()
    if isinstance(raw, dict):
        return str(raw.get("content") or raw.get("transcript") or "").strip()
    return str(msg.get("content") or msg.get("transcript") or "").strip()


def _speaker_label(role: str) -> str | None:
    clean = str(role or "").strip().lower()
    if clean in {"user", "customer"}:
        return "User"
    if clean in {"assistant", "bot", "ai"}:
        return "Agent"
    if clean == "system":
        return None
    return None


def _message_sort_key(msg: dict[str, Any]) -> tuple[int, float, int]:
    seconds = msg.get("secondsFromStart")
    if isinstance(seconds, (int, float)):
        return (0, float(seconds), 0)
    time_val = msg.get("time")
    if isinstance(time_val, (int, float)):
        return (1, float(time_val), 0)
    end_time = msg.get("endTime")
    if isinstance(end_time, (int, float)):
        return (2, float(end_time), 0)
    return (3, 0.0, id(msg))


def _collect_messages(call: dict[str, Any]) -> list[dict[str, Any]]:
    artifact = call.get("artifact") if isinstance(call.get("artifact"), dict) else {}
    messages = artifact.get("messages") or call.get("messages") or []
    return [msg for msg in messages if isinstance(msg, dict)]


def transcript_entries_from_call(call: dict[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for msg in sorted(_collect_messages(call), key=_message_sort_key):
        if msg.get("toolCalls") or msg.get("toolCallId"):
            continue
        speaker = _speaker_label(str(msg.get("role") or ""))
        text = _message_text(msg)
        if not speaker or not text:
            continue
        seconds = msg.get("secondsFromStart")
        entries.append(
            {
                "speaker": speaker,
                "text": text,
                "seconds_from_start": float(seconds) if isinstance(seconds, (int, float)) else None,
                "time": msg.get("time"),
            }
        )
    return entries


def transcript_from_vapi_call(call: dict[str, Any]) -> str:
    entries = transcript_entries_from_call(call)
    if entries:
        return "\n".join(f"{entry['speaker']}: {entry['text']}" for entry in entries)

    artifact = call.get("artifact") if isinstance(call.get("artifact"), dict) else {}
    openai_lines: list[str] = []
    for msg in artifact.get("messagesOpenAIFormatted") or []:
        if not isinstance(msg, dict):
            continue
        label = _speaker_label(str(msg.get("role") or ""))
        text = str(msg.get("content") or "").strip()
        if label and text:
            openai_lines.append(f"{label}: {text}")
    if openai_lines:
        return "\n".join(openai_lines)

    direct = str(artifact.get("transcript") or "").strip()
    if direct:
        return _normalize_transcript_blob(direct)
    return ""


def _normalize_transcript_blob(text: str) -> str:
    cleaned = text.strip()
    if not cleaned:
        return ""
    if re.search(r"(?m)^(Agent|User):", cleaned):
        return cleaned
    out: list[str] = []
    for raw_line in cleaned.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = re.match(r"^(User|Agent|Assistant|AI|Bot|Customer)\s*:\s*(.*)$", line, flags=re.I)
        if match:
            speaker = match.group(1).lower()
            body = match.group(2).strip()
            label = "Agent" if speaker in {"assistant", "ai", "bot", "agent"} else "User"
            out.append(f"{label}: {body}")
        else:
            out.append(line)
    return "\n".join(out)


def recording_url_from_vapi_call(call: dict[str, Any]) -> str | None:
    artifact = call.get("artifact")
    if isinstance(artifact, dict):
        recording = artifact.get("recording")
        if isinstance(recording, dict):
            for key in ("stereoUrl", "videoUrl", "url"):
                url = str(recording.get(key) or "").strip()
                if url.startswith("http"):
                    return url
            mono = recording.get("mono")
            if isinstance(mono, dict):
                for key in ("combinedUrl", "assistantUrl", "customerUrl"):
                    url = str(mono.get(key) or "").strip()
                    if url.startswith("http"):
                        return url
        for key in ("stereoRecordingUrl", "recordingUrl", "videoRecordingUrl"):
            url = str(artifact.get(key) or "").strip()
            if url.startswith("http"):
                return url
    return None


def get_vapi_media_for_lead(db: Session, row) -> dict[str, Any]:
    result: dict[str, Any] = {
        "source": "vapi",
        "available": False,
        "call_id": str(row.provider_call_id or "").strip() or None,
        "transcript": None,
        "recording_url": None,
        "messages": [],
        "error": None,
    }
    if str(row.voice_provider or "").strip().lower() != "vapi":
        result["error"] = "Not a Vapi call"
        return result
    if not result["call_id"]:
        result["error"] = "No Vapi call id stored for this lead"
        return result

    call, err = fetch_vapi_call(db, provider_call_id=result["call_id"])
    if err or not call:
        result["error"] = err or "Could not load call from Vapi"
        return result

    result["available"] = True
    entries = transcript_entries_from_call(call)
    result["messages"] = entries
    transcript = transcript_from_vapi_call(call)
    if transcript:
        result["transcript"] = transcript
    recording_url = recording_url_from_vapi_call(call)
    if recording_url:
        result["recording_url"] = recording_url
    if not result["transcript"] and not result["recording_url"]:
        result["error"] = "Vapi call loaded but transcript/recording are not ready yet — try again in a minute"
    return result


def sync_vapi_lead_artifacts(db: Session, row) -> dict[str, Any]:
    media = get_vapi_media_for_lead(db, row)
    result = {
        "synced": media.get("available", False),
        "transcript_updated": False,
        "recording_available": bool(media.get("recording_url")) or bool(row.recording_path),
        "recording_url": media.get("recording_url"),
        "error": media.get("error"),
    }
    transcript = str(media.get("transcript") or "").strip()
    if transcript:
        row.transcript_text = transcript
        row.agent_response_text = None
        result["transcript_updated"] = True
        db.commit()
        db.refresh(row)
    return result
