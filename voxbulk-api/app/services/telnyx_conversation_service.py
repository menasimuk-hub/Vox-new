from __future__ import annotations

import array
import io
import json
import re
import wave
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.core.http_ssl import httpx_ssl_verify
from app.services.telnyx_api_key import require_telnyx_api_key

TELNYX_API_BASE = "https://api.telnyx.com/v2"
_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.I,
)


def _telnyx_headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}


def _telnyx_request(
    db: Session,
    method: str,
    path: str,
    *,
    params: dict[str, Any] | list[tuple[str, str]] | None = None,
    timeout: float = 25.0,
) -> tuple[dict[str, Any] | list[Any] | None, str | None]:
    try:
        api_key, _source = require_telnyx_api_key(db)
    except ValueError as exc:
        return None, str(exc)
    url = f"{TELNYX_API_BASE}{path}"
    try:
        response = httpx.request(
            method,
            url,
            headers=_telnyx_headers(api_key),
            params=params,
            timeout=timeout,
            verify=httpx_ssl_verify(),
        )
    except Exception as exc:
        return None, f"Telnyx request failed: {exc}"
    if response.status_code == 401:
        detail = (response.text or "")[:300]
        return None, f"Telnyx returned 401 — {detail}. Check Integrations → Telnyx API key."
    if response.status_code == 404:
        return None, "Telnyx resource not found"
    if not response.is_success:
        detail = (response.text or "")[:300]
        return None, f"Telnyx returned {response.status_code}" + (f" — {detail}" if detail else "")
    try:
        body = response.json()
    except Exception:
        return None, "Telnyx returned invalid JSON"
    return body, None


def _parse_iso(value: str | None) -> datetime | None:
    clean = str(value or "").strip()
    if not clean:
        return None
    try:
        if clean.endswith("Z"):
            clean = clean[:-1] + "+00:00"
        return datetime.fromisoformat(clean.replace("Z", "+00:00"))
    except ValueError:
        return None


def _to_utc_naive(value: datetime | str | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, str):
        parsed = _parse_iso(value)
        if parsed is None:
            return None
        value = parsed
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _dt_sort_key(value: str | None) -> float:
    normalized = _to_utc_naive(_parse_iso(value))
    return normalized.timestamp() if normalized else 0.0


def _looks_like_conversation_id(value: str | None) -> bool:
    return bool(_UUID_RE.match(str(value or "").strip()))


def _conversation_list(db: Session, *, params: dict[str, Any]) -> list[dict[str, Any]]:
    body, err = _telnyx_request(db, "GET", "/ai/conversations", params=params)
    if err or not isinstance(body, dict):
        return []
    rows = body.get("data")
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _conversation_belongs_to_lead(row, conversation: dict[str, Any]) -> bool:
    lead_id = str(getattr(row, "id", "") or "").strip()
    if not lead_id or not conversation:
        return False
    try:
        blob = json.dumps(conversation, default=str).lower()
    except TypeError:
        return False
    needle = lead_id.lower()
    return needle in blob or f"x-lead-call-id" in blob and needle in blob


def _pick_conversation_for_lead(row, conversations: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not conversations:
        return None
    matched = [conv for conv in conversations if _conversation_belongs_to_lead(row, conv)]
    if matched:
        conversations = matched
    target = _to_utc_naive(row.completed_at or row.started_at or row.created_at)
    if not target:
        return conversations[0]

    def score(conv: dict[str, Any]) -> float:
        ref = _to_utc_naive(str(conv.get("last_message_at") or "")) or _to_utc_naive(
            str(conv.get("created_at") or "")
        )
        if ref is None:
            return float("inf")
        return abs((ref - target).total_seconds())

    return min(conversations, key=score)


def fetch_conversation_by_id(db: Session, conversation_id: str) -> dict[str, Any] | None:
    conv_id = str(conversation_id or "").strip()
    if not conv_id:
        return None
    body, err = _telnyx_request(db, "GET", f"/ai/conversations/{conv_id}")
    if err or not isinstance(body, dict):
        return None
    data = body.get("data")
    return data if isinstance(data, dict) else None


def find_conversation_for_lead(db: Session, row) -> tuple[dict[str, Any] | None, str | None]:
    stored = str(row.provider_call_id or "").strip()
    if _looks_like_conversation_id(stored):
        full = fetch_conversation_by_id(db, stored)
        if full:
            return full, None
        matches = _conversation_list(db, params={"id": f"eq.{stored}", "limit": 1})
        if matches:
            return matches[0], None
        probe, err = _telnyx_request(db, "GET", f"/ai/conversations/{stored}/messages", params={"page[size]": 1})
        if not err and isinstance(probe, dict):
            return {"id": stored, "metadata": {}}, None

    assistant_id = str(row.provider_agent_id or "").strip()
    if not assistant_id:
        return None, "Missing Telnyx assistant ID on this lead"

    started = row.started_at or row.created_at
    if not started:
        return None, "Missing call start time for Telnyx lookup"

    window_start = started - timedelta(minutes=5)
    params: dict[str, Any] = {
        "metadata->assistant_id": f"eq.{assistant_id}",
        "created_at": f"gte.{window_start.strftime('%Y-%m-%dT%H:%M:%SZ')}",
        "order": "created_at.desc",
        "limit": 25,
    }
    conversations = _conversation_list(db, params=params)
    if not conversations:
        params.pop("metadata->assistant_id", None)
        params["created_at"] = f"gte.{window_start.strftime('%Y-%m-%dT%H:%M:%SZ')}"
        conversations = _conversation_list(db, params=params)
    if not conversations:
        return None, "Telnyx conversation not found yet — try again in a minute"
    return _pick_conversation_for_lead(row, conversations), None


def fetch_conversation_messages(db: Session, conversation_id: str) -> tuple[list[dict[str, Any]], str | None]:
    conv_id = str(conversation_id or "").strip()
    if not conv_id:
        return [], "Missing conversation id"
    messages: list[dict[str, Any]] = []
    page = 1
    while page <= 20:
        body, err = _telnyx_request(
            db,
            "GET",
            f"/ai/conversations/{conv_id}/messages",
            params={"page[number]": page, "page[size]": 100},
        )
        if err or not isinstance(body, dict):
            return messages, err
        batch = body.get("data")
        if isinstance(batch, list):
            messages.extend(item for item in batch if isinstance(item, dict))
        meta = body.get("meta") if isinstance(body.get("meta"), dict) else {}
        total_pages = int(meta.get("total_pages") or 1)
        if page >= total_pages:
            break
        page += 1
    return messages, None


def _speaker_label(role: str) -> str | None:
    clean = str(role or "").strip().lower()
    if clean == "user":
        return "User"
    if clean == "assistant":
        return "Agent"
    return None


def transcript_entries_from_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(
        messages,
        key=lambda msg: (
            _dt_sort_key(str(msg.get("sent_at") or msg.get("created_at") or "")),
            id(msg),
        ),
    )
    first_at: datetime | None = None
    entries: list[dict[str, Any]] = []
    for msg in ordered:
        if str(msg.get("role") or "").strip().lower() == "tool":
            continue
        speaker = _speaker_label(str(msg.get("role") or ""))
        text = str(msg.get("text") or "").strip()
        if not speaker or not text:
            continue
        sent_at = str(msg.get("sent_at") or msg.get("created_at") or "").strip() or None
        sent_dt = _to_utc_naive(sent_at)
        if sent_dt and first_at is None:
            first_at = sent_dt
        seconds_from_start = None
        if sent_dt and first_at:
            seconds_from_start = max(0.0, (sent_dt - first_at).total_seconds())
        entries.append(
            {
                "speaker": speaker,
                "text": text,
                "sent_at": sent_at,
                "seconds_from_start": seconds_from_start,
            }
        )
    return entries


def transcript_from_entries(entries: list[dict[str, Any]]) -> str:
    if not entries:
        return ""
    return "\n".join(f"{entry['speaker']}: {entry['text']}" for entry in entries)


def _iso_z(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _list_recordings(
    db: Session,
    *,
    call_control_id: str | None = None,
    call_session_id: str | None = None,
    created_gte: datetime | None = None,
    created_lte: datetime | None = None,
) -> list[dict[str, Any]]:
    params: list[tuple[str, str]] = [("page[size]", "50")]
    if call_control_id:
        params.append(("filter[call_control_id]", call_control_id))
    if call_session_id:
        params.append(("filter[call_session_id]", call_session_id))
    if created_gte:
        params.append(("filter[created_at][gte]", _iso_z(created_gte)))
    if created_lte:
        params.append(("filter[created_at][lte]", _iso_z(created_lte)))
    if len(params) == 1 and not (created_gte or created_lte):
        return []
    body, err = _telnyx_request(db, "GET", "/recordings", params=params)
    if err or not isinstance(body, dict):
        return []
    rows = body.get("data")
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _metadata_ids(metadata: dict[str, Any]) -> dict[str, str]:
    keys = (
        "call_control_id",
        "call_session_id",
        "call_leg_id",
        "recording_id",
        "telnyx_call_control_id",
        "telnyx_call_session_id",
    )
    out: dict[str, str] = {}
    for key in keys:
        value = str(metadata.get(key) or "").strip()
        if value:
            out[key] = value
    return out


def _extract_call_ids_from_conversation(conversation: dict[str, Any]) -> dict[str, str]:
    """Walk conversation JSON — WebRTC calls sometimes nest call_control_id outside metadata."""
    found: dict[str, str] = {}
    id_keys = {
        "call_control_id",
        "call_session_id",
        "call_leg_id",
        "telnyx_call_control_id",
        "telnyx_call_session_id",
    }

    def walk(value: Any, depth: int = 0) -> None:
        if depth > 8:
            return
        if isinstance(value, dict):
            for key, child in value.items():
                key_l = str(key).lower()
                if key_l in id_keys and isinstance(child, str) and child.strip():
                    found[key_l.replace("telnyx_", "")] = child.strip()
                walk(child, depth + 1)
        elif isinstance(value, list):
            for item in value[:30]:
                walk(item, depth + 1)

    walk(conversation)
    found.update(_metadata_ids(conversation.get("metadata") if isinstance(conversation.get("metadata"), dict) else {}))
    return found


def _collect_recording_candidates(db: Session, conversation: dict[str, Any]) -> list[dict[str, Any]]:
    """Gather every Telnyx /recordings row that might belong to this AI conversation."""
    ids = _extract_call_ids_from_conversation(conversation)
    seen: set[str] = set()
    candidates: list[dict[str, Any]] = []

    def add_rows(rows: list[dict[str, Any]]) -> None:
        for row in rows:
            rid = str(row.get("id") or "").strip()
            if rid and rid in seen:
                continue
            if rid:
                seen.add(rid)
            candidates.append(row)

    if ids.get("call_control_id"):
        add_rows(_list_recordings(db, call_control_id=ids["call_control_id"]))
    if ids.get("call_session_id"):
        add_rows(_list_recordings(db, call_session_id=ids["call_session_id"]))

    created = _to_utc_naive(conversation.get("created_at"))
    last_at = _to_utc_naive(conversation.get("last_message_at"))
    if created:
        window_start = created - timedelta(minutes=10)
        window_end = (last_at or created) + timedelta(minutes=15)
        add_rows(_list_recordings(db, created_gte=window_start, created_lte=window_end))

    return candidates


def _refresh_recording_row(db: Session, rec: dict[str, Any]) -> dict[str, Any]:
    recording_id = str(rec.get("id") or "").strip()
    if not recording_id:
        return rec
    body, err = _telnyx_request(db, "GET", f"/recordings/{recording_id}")
    if err or not isinstance(body, dict):
        return rec
    data = body.get("data")
    return data if isinstance(data, dict) else rec


def _recording_download(rec: dict[str, Any]) -> tuple[str | None, str | None]:
    """Telnyx often returns only MP3 for AI/WebRTC dual recordings — prefer WAV when present."""
    downloads = rec.get("download_urls") if isinstance(rec.get("download_urls"), dict) else {}
    for fmt in ("wav", "mp3"):
        url = str(downloads.get(fmt) or "").strip()
        if url.startswith("http"):
            return url, fmt
    return None, None


def _download_recording_bytes(url: str) -> bytes | None:
    try:
        response = httpx.get(url, timeout=90.0, follow_redirects=True, verify=httpx_ssl_verify())
        response.raise_for_status()
        return response.content
    except Exception:
        return None


def _wav_stereo_channel_rms(data: bytes) -> tuple[float, float] | None:
    """Return RMS for channel A (user) and channel B (agent) — Telnyx dual layout."""
    try:
        with wave.open(io.BytesIO(data), "rb") as handle:
            if handle.getnchannels() != 2 or handle.getsampwidth() != 2:
                return None
            frames = handle.readframes(handle.getnframes())
    except Exception:
        return None
    if not frames:
        return None
    samples = array.array("h")
    samples.frombytes(frames)
    left = samples[0::2]
    right = samples[1::2]

    def rms(channel: array.array[int]) -> float:
        if not channel:
            return 0.0
        return (sum(int(sample) * int(sample) for sample in channel) / len(channel)) ** 0.5

    return rms(left), rms(right)


def _prioritize_recording_rows(conversation: dict[str, Any], rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ids = _extract_call_ids_from_conversation(conversation)
    cc = ids.get("call_control_id")
    cs = ids.get("call_session_id")
    matched: list[dict[str, Any]] = []
    rest: list[dict[str, Any]] = []
    for row in rows:
        row_cc = str(row.get("call_control_id") or "").strip()
        row_cs = str(row.get("call_session_id") or "").strip()
        if (cc and row_cc == cc) or (cs and row_cs == cs):
            matched.append(row)
        else:
            rest.append(row)
    return matched + rest


def resolve_telnyx_recording(db: Session, conversation: dict[str, Any]) -> dict[str, Any] | None:
    """
  Telnyx portal dual recording: channel A = caller, channel B = agent.
  Only accept recordings that are dual AND have energy on both channels.
    """
    candidates = _prioritize_recording_rows(conversation, _collect_recording_candidates(db, conversation))
    dual_rows = [row for row in candidates if str(row.get("channels") or "").strip().lower() == "dual"]
    if not dual_rows:
        return None

    dual_rows.sort(key=lambda row: int(row.get("duration_millis") or 0), reverse=True)
    min_rms = 40.0

    for row in dual_rows:
        fresh = _refresh_recording_row(db, row)
        download_url, file_format = _recording_download(fresh)
        if not download_url or not file_format:
            continue
        audio = _download_recording_bytes(download_url)
        if not audio:
            continue
        user_rms: float | None = None
        agent_rms: float | None = None
        if file_format == "wav":
            levels = _wav_stereo_channel_rms(audio)
            if not levels:
                continue
            user_rms, agent_rms = levels
            if user_rms < min_rms or agent_rms < min_rms:
                continue
        return {
            "id": str(fresh.get("id") or "").strip() or None,
            "channels": "dual",
            "format": file_format,
            "download_url": download_url,
            "duration_millis": fresh.get("duration_millis"),
            "user_channel_rms": round(user_rms, 1) if user_rms is not None else None,
            "agent_channel_rms": round(agent_rms, 1) if agent_rms is not None else None,
            "audio_bytes": audio,
        }
    return None


def telnyx_recording_response(db: Session, row) -> tuple[Any, str | None]:
    """Stream validated dual-channel WAV from Telnyx (both caller + agent)."""
    from fastapi.responses import Response

    conversation, err = find_conversation_for_lead(db, row)
    if err or not conversation:
        return None, err or "Could not find Telnyx conversation"
    rec = resolve_telnyx_recording(db, conversation)
    if not rec:
        return (
            None,
            "No Telnyx dual-channel recording with both voices yet. "
            "Wait a minute after the call ends, then refresh. "
            "In Telnyx portal, confirm the conversation shows a dual waveform.",
        )
    audio = rec.get("audio_bytes")
    if not isinstance(audio, (bytes, bytearray)) or not audio:
        url = str(rec.get("download_url") or "").strip()
        audio = _download_recording_bytes(url) if url else None
    if not audio:
        return None, "Could not download Telnyx recording"
    fmt = str(rec.get("format") or "mp3").lower()
    media_type = "audio/wav" if fmt == "wav" else "audio/mpeg"
    filename = f"telnyx-{row.lead_code or row.id}.{fmt}"
    headers = {
        "Content-Disposition": f'inline; filename="{filename}"',
        "X-Recording-Channels": "dual",
        "X-Recording-Format": fmt,
        "X-Recording-User-Rms": str(rec.get("user_channel_rms") or ""),
        "X-Recording-Agent-Rms": str(rec.get("agent_channel_rms") or ""),
    }
    return Response(content=audio, media_type=media_type, headers=headers), None


def get_telnyx_media_for_lead(db: Session, row) -> dict[str, Any]:
    result: dict[str, Any] = {
        "source": "telnyx",
        "available": False,
        "conversation_id": None,
        "call_control_id": None,
        "transcript": None,
        "recording_url": None,
        "recording_id": None,
        "recording_channels": None,
        "recording_play_url": None,
        "messages": [],
        "error": None,
    }
    if str(row.voice_provider or "").strip().lower() != "telnyx":
        result["error"] = "Not a Telnyx call"
        return result

    try:
        return _get_telnyx_media_for_lead_impl(db, row, result)
    except Exception as exc:
        result["error"] = f"Telnyx media load failed: {exc}"
        return result


def _get_telnyx_media_for_lead_impl(db: Session, row, result: dict[str, Any]) -> dict[str, Any]:
    conversation, err = find_conversation_for_lead(db, row)
    if err or not conversation:
        result["error"] = err or "Could not find Telnyx conversation for this lead"
        return result

    conversation_id = str(conversation.get("id") or "").strip()
    result["conversation_id"] = conversation_id or None
    metadata = conversation.get("metadata") if isinstance(conversation.get("metadata"), dict) else {}
    result["call_control_id"] = str(metadata.get("call_control_id") or "").strip() or None

    messages, msg_err = fetch_conversation_messages(db, conversation_id)
    if msg_err and not messages:
        result["error"] = msg_err
        return result

    entries = transcript_entries_from_messages(messages)
    result["messages"] = entries
    transcript = transcript_from_entries(entries)
    if transcript:
        result["transcript"] = transcript

    recording = resolve_telnyx_recording(db, conversation)
    if recording:
        result["recording_id"] = recording.get("id")
        result["recording_channels"] = recording.get("channels")
        result["recording_play_url"] = f"/admin/frontpage/lead-sources/{row.id}/recording"
        result["user_channel_rms"] = recording.get("user_channel_rms")
        result["agent_channel_rms"] = recording.get("agent_channel_rms")

    if entries or recording:
        result["available"] = True
    if not result["available"]:
        result["error"] = "Telnyx conversation found but transcript/recording are not ready yet — try again in a minute"
    return result


def sync_telnyx_lead_artifacts(db: Session, row) -> dict[str, Any]:
    media = get_telnyx_media_for_lead(db, row)
    result = {
        "synced": media.get("available", False),
        "transcript_updated": False,
        "recording_available": bool(media.get("recording_play_url")),
        "recording_url": media.get("recording_play_url"),
        "conversation_id": media.get("conversation_id"),
        "error": media.get("error"),
    }
    conversation_id = str(media.get("conversation_id") or "").strip()
    if conversation_id and _looks_like_conversation_id(conversation_id):
        row.provider_call_id = conversation_id
    transcript = str(media.get("transcript") or "").strip()
    if transcript:
        row.transcript_text = transcript
        row.agent_response_text = None
        result["transcript_updated"] = True
    if result["transcript_updated"] or conversation_id:
        db.commit()
        db.refresh(row)
    return result


def _parse_insight_result(value: Any) -> tuple[str, Any | None]:
    text = str(value or "").strip()
    if not text:
        return "", None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return text, None
    return text, parsed


def fetch_conversation_insights(db: Session, conversation_id: str) -> dict[str, Any]:
    """Fetch Telnyx Assistant conversation insights (structured agent output)."""
    conv_id = str(conversation_id or "").strip()
    if not _looks_like_conversation_id(conv_id):
        return {
            "conversation_id": conv_id,
            "error": "Invalid Telnyx conversation id",
            "status": "invalid",
            "items": [],
        }

    body, err = _telnyx_request(
        db,
        "GET",
        f"/ai/conversations/{conv_id}/conversations-insights",
        timeout=30.0,
    )
    if err:
        if err == "Telnyx resource not found":
            return {
                "conversation_id": conv_id,
                "error": None,
                "status": "none",
                "items": [],
                "message": (
                    "Telnyx has no insight record for this conversation yet. "
                    "Insights appear after the call ends when Insights are enabled on the assistant."
                ),
            }
        return {
            "conversation_id": conv_id,
            "error": err,
            "status": "error",
            "items": [],
        }

    raw_batches = body.get("data") if isinstance(body, dict) else []
    if not isinstance(raw_batches, list):
        raw_batches = []

    items: list[dict[str, Any]] = []
    batch_statuses: list[str] = []
    for batch in raw_batches:
        if not isinstance(batch, dict):
            continue
        batch_status = str(batch.get("status") or "").strip() or "unknown"
        batch_statuses.append(batch_status)
        for ins in batch.get("conversation_insights") or []:
            if not isinstance(ins, dict):
                continue
            result_text, result_json = _parse_insight_result(ins.get("result"))
            items.append(
                {
                    "insight_id": ins.get("insight_id"),
                    "result": result_text,
                    "result_json": result_json,
                    "batch_id": batch.get("id"),
                    "batch_status": batch_status,
                    "created_at": batch.get("created_at"),
                }
            )

    if items:
        status = "completed"
    elif batch_statuses:
        status = batch_statuses[0]
    else:
        status = "none"

    return {
        "conversation_id": conv_id,
        "error": None,
        "status": status,
        "items": items,
        "meta": body.get("meta") if isinstance(body, dict) else None,
    }
