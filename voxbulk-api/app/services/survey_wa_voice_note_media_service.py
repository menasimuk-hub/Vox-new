"""Download and store inbound WhatsApp voice-note media."""

from __future__ import annotations

import logging
import mimetypes
import os
import re
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.http_ssl import httpx_ssl_verify
from app.services.provider_settings import ProviderSettingsService
from app.services.survey_wa_voice_note_settings import voice_note_settings

logger = logging.getLogger(__name__)
LOG_PREFIX = "[survey-wa-voice-media]"


def extract_media_items(record: dict[str, Any]) -> list[dict[str, Any]]:
    """Parse Telnyx or Meta Cloud API inbound record for audio media attachments."""
    items: list[dict[str, Any]] = []

    def _append(raw: dict[str, Any]) -> None:
        url = str(raw.get("url") or raw.get("media_url") or raw.get("href") or "").strip()
        if not url:
            return
        content_type = str(raw.get("content_type") or raw.get("mime_type") or raw.get("type") or "").strip().lower()
        media_id = str(raw.get("id") or raw.get("media_id") or raw.get("hash") or "").strip()
        filename = str(raw.get("filename") or raw.get("name") or "").strip()
        items.append(
            {
                "url": url,
                "content_type": content_type,
                "provider_media_id": media_id or _media_id_from_url(url),
                "original_filename": filename,
            }
        )

    def _append_block(raw: Any) -> None:
        if isinstance(raw, dict):
            _append(raw)

    media = record.get("media")
    if isinstance(media, list):
        for row in media:
            _append_block(row)
    elif isinstance(media, dict):
        _append_block(media)

    # Meta Cloud API — top-level audio/voice on inbound message dict
    for key in ("audio", "voice", "ptt"):
        _append_block(record.get(key))

    whatsapp_message = record.get("whatsapp_message")
    if isinstance(whatsapp_message, dict):
        for key in ("audio", "voice", "ptt"):
            _append_block(whatsapp_message.get(key))
        nested = whatsapp_message.get("media") or whatsapp_message.get("audio")
        if isinstance(nested, list):
            for row in nested:
                _append_block(row)
        elif isinstance(nested, dict):
            _append_block(nested)

    body = record.get("body")
    if isinstance(body, dict):
        nested = body.get("media") or body.get("audio")
        if isinstance(nested, dict):
            _append_block(nested)
        elif isinstance(nested, list):
            for row in nested:
                _append_block(row)

    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        key = f"{item.get('provider_media_id')}::{item.get('url')}"
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _media_id_from_url(url: str) -> str:
    path = urlparse(url).path.rstrip("/")
    tail = path.split("/")[-1] if path else ""
    return tail or str(uuid.uuid4())


def _guess_extension(content_type: str, filename: str) -> str:
    if filename and "." in filename:
        ext = Path(filename).suffix.lower()
        if ext:
            return ext
    guessed = mimetypes.guess_extension(content_type.split(";")[0].strip()) if content_type else None
    return guessed or ".ogg"


def _is_allowed_mime(content_type: str, allowed: list[str]) -> bool:
    clean = str(content_type or "").split(";")[0].strip().lower()
    if not clean:
        return False
    if clean in allowed:
        return True
    base = clean.split("/")[0]
    return base == "audio" and any(a.startswith("audio/") for a in allowed)


def storage_path_for_job(*, org_id: str, order_id: str, job_id: str, extension: str) -> Path:
    cfg = voice_note_settings()
    root = Path(cfg["voice_note_storage_dir"])
    if not root.is_absolute():
        root = Path.cwd() / root
    safe_ext = re.sub(r"[^a-z0-9.]+", "", extension.lower()) or ".ogg"
    if not safe_ext.startswith("."):
        safe_ext = f".{safe_ext}"
    return root / str(org_id) / str(order_id) / f"{job_id}{safe_ext}"


def resolve_telnyx_api_key(db: Session) -> str:
    cfg, _enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="telnyx")
    config = cfg if isinstance(cfg, dict) else {}
    key = str(config.get("api_key") or config.get("access_token") or "").strip()
    if key:
        return key
    return str(get_settings().telnyx_api_key or "").strip()


def _download_auth_headers(db: Session, media_url: str) -> dict[str, str]:
    """Meta lookaside URLs need Graph access token; Telnyx storage uses Telnyx API key."""
    headers = {"Accept": "*/*"}
    low = str(media_url or "").lower()
    if any(host in low for host in ("lookaside.fbsbx.com", "fbcdn.net", "graph.facebook.com")):
        try:
            from app.services.meta_whatsapp_service import MetaWhatsappConfigError, MetaWhatsappService

            config, enabled = MetaWhatsappService._config(db)
            if enabled:
                token = MetaWhatsappService._require_token(config)
                headers["Authorization"] = f"Bearer {token}"
                return headers
        except MetaWhatsappConfigError as exc:
            logger.warning("%s meta_media_auth_unavailable err=%s", LOG_PREFIX, exc)
        except Exception as exc:
            logger.warning("%s meta_media_auth_failed err=%s", LOG_PREFIX, exc)
    api_key = resolve_telnyx_api_key(db)
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def download_media_file(
    db: Session,
    *,
    media_url: str,
    content_type: str,
    original_filename: str,
    dest_path: Path,
    max_bytes: int,
    timeout_seconds: int,
) -> tuple[Path, int, str]:
    cfg = voice_note_settings()
    allowed = cfg["voice_note_allowed_mime_types"]
    if content_type and not _is_allowed_mime(content_type, allowed):
        raise ValueError(f"Unsupported audio MIME type: {content_type}")

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    headers = _download_auth_headers(db, media_url)

    logger.info("%s download_started url=%s dest=%s", LOG_PREFIX, media_url[:180], dest_path)
    last_error: Exception | None = None
    for attempt in range(1, 4):
        try:
            with httpx.Client(timeout=float(timeout_seconds), verify=httpx_ssl_verify(), follow_redirects=True) as client:
                with client.stream("GET", media_url, headers=headers) as response:
                    response.raise_for_status()
                    ctype = str(response.headers.get("content-type") or content_type or "").split(";")[0].strip().lower()
                    if ctype and not _is_allowed_mime(ctype, allowed):
                        raise ValueError(f"Downloaded file has unsupported MIME type: {ctype}")
                    if not ctype:
                        ctype = "audio/ogg"
                    total = 0
                    with dest_path.open("wb") as handle:
                        for chunk in response.iter_bytes(chunk_size=65536):
                            if not chunk:
                                continue
                            total += len(chunk)
                            if total > max_bytes:
                                raise ValueError("Voice note exceeds maximum allowed file size")
                            handle.write(chunk)
            logger.info("%s download_completed path=%s bytes=%s", LOG_PREFIX, dest_path, total)
            return dest_path, total, ctype or content_type
        except Exception as exc:
            last_error = exc
            logger.warning("%s download_attempt_failed attempt=%s err=%s", LOG_PREFIX, attempt, exc)
            if dest_path.exists():
                try:
                    dest_path.unlink()
                except OSError:
                    pass
    raise ValueError(str(last_error) if last_error else "Media download failed")
