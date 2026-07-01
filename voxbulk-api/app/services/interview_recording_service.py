"""Fetch interview candidate recordings for dashboard playback (fresh Telnyx URLs)."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.models.service_order import ServiceOrderRecipient

logger = logging.getLogger(__name__)

USER_RECORDING_UNAVAILABLE = "Interview recording is temporarily unavailable. Please try again in a minute."
USER_RECORDING_PROCESSING = "Recording is still processing. Please try again shortly."


def _loads(raw: str | None) -> dict[str, Any]:
    try:
        data = json.loads(raw or "{}")
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _media_type_for_format(fmt: str) -> str:
    return "audio/wav" if str(fmt or "").lower() == "wav" else "audio/mpeg"


def _persist_recording_meta(db: Session, recipient: ServiceOrderRecipient, parsed: dict[str, Any], rec: dict[str, Any]) -> None:
    merged = dict(parsed)
    if rec.get("id"):
        merged["telnyx_recording_id"] = rec.get("id")
    merged["recording_resolved_at"] = datetime.utcnow().isoformat()
    if rec.get("download_url"):
        merged["telnyx_recording_download_url"] = str(rec["download_url"])
    recipient.result_json = json.dumps(merged, ensure_ascii=False)
    db.add(recipient)
    db.commit()


def _resolve_from_conversation(db: Session, conversation_id: str) -> dict[str, Any] | None:
    from app.services.telnyx_conversation_service import (
        fetch_conversation_by_id,
        resolve_telnyx_recording_relaxed,
    )

    conversation = fetch_conversation_by_id(db, conversation_id)
    if not conversation:
        return None
    return resolve_telnyx_recording_relaxed(db, conversation)


def _download_url_bytes(url: str) -> tuple[bytes | None, str]:
    try:
        with httpx.Client(timeout=30.0, follow_redirects=True) as client:
            resp = client.get(url)
            resp.raise_for_status()
        media_type = resp.headers.get("content-type") or "audio/mpeg"
        return resp.content, media_type
    except Exception as exc:
        logger.warning("interview_recording_url_fetch_failed url=%s err=%s", url[:80], exc)
        return None, "audio/mpeg"


def fetch_interview_recording(
    db: Session,
    recipient: ServiceOrderRecipient,
) -> tuple[bytes, str] | None:
    """
    Return (audio_bytes, media_type) for a completed interview recipient.
    Always prefers a fresh Telnyx resolve when conversation_id is known.
    """
    parsed = _loads(recipient.result_json)
    conversation_id = str(
        parsed.get("telnyx_conversation_id") or parsed.get("provider_call_id") or ""
    ).strip()

    if conversation_id:
        rec = _resolve_from_conversation(db, conversation_id)
        if rec:
            audio = rec.get("audio_bytes")
            if isinstance(audio, (bytes, bytearray)) and audio:
                _persist_recording_meta(db, recipient, parsed, rec)
                return bytes(audio), _media_type_for_format(str(rec.get("format") or "mp3"))
            url = str(rec.get("download_url") or "").strip()
            if url.startswith("http"):
                content, media_type = _download_url_bytes(url)
                if content:
                    _persist_recording_meta(db, recipient, parsed, rec)
                    return content, media_type

    download_url = str(parsed.get("telnyx_recording_download_url") or "").strip()
    if download_url.startswith("http"):
        content, media_type = _download_url_bytes(download_url)
        if content:
            return content, media_type
        if conversation_id:
            rec = _resolve_from_conversation(db, conversation_id)
            if rec:
                audio = rec.get("audio_bytes")
                if isinstance(audio, (bytes, bytearray)) and audio:
                    _persist_recording_meta(db, recipient, parsed, rec)
                    return bytes(audio), _media_type_for_format(str(rec.get("format") or "mp3"))
                url = str(rec.get("download_url") or "").strip()
                if url.startswith("http"):
                    content, media_type = _download_url_bytes(url)
                    if content:
                        _persist_recording_meta(db, recipient, parsed, rec)
                        return content, media_type

    if conversation_id:
        rec = _resolve_from_conversation(db, conversation_id)
        if rec:
            audio = rec.get("audio_bytes")
            if isinstance(audio, (bytes, bytearray)) and audio:
                _persist_recording_meta(db, recipient, parsed, rec)
                return bytes(audio), _media_type_for_format(str(rec.get("format") or "mp3"))

    return None
