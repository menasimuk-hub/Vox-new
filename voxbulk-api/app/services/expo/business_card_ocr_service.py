"""Extract name / company / email / phone from an Expo business-card photo (OpenAI vision)."""

from __future__ import annotations

import base64
import json
import logging
import re
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.core.http_ssl import httpx_ssl_verify
from app.services.providers.openai_service import OpenAIProviderService
from app.services.survey_wa_voice_note_media_service import _download_auth_headers

logger = logging.getLogger(__name__)

_CARD_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "name": {"type": ["string", "null"]},
        "company": {"type": ["string", "null"]},
        "email": {"type": ["string", "null"]},
        "phone": {"type": ["string", "null"]},
    },
    "required": ["name", "company", "email", "phone"],
}


def extract_image_media_items(record: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Parse Meta / Telnyx inbound shapes for image attachments."""
    if not isinstance(record, dict):
        return []
    items: list[dict[str, Any]] = []

    def _append(raw: Any) -> None:
        if not isinstance(raw, dict):
            return
        url = str(raw.get("url") or raw.get("media_url") or raw.get("href") or raw.get("link") or "").strip()
        media_id = str(raw.get("id") or raw.get("media_id") or "").strip()
        content_type = str(raw.get("content_type") or raw.get("mime_type") or raw.get("type") or "").strip().lower()
        if content_type and not content_type.startswith("image") and content_type not in {"", "image"}:
            # Telnyx sometimes puts bare "image" as type
            if "image" not in content_type and not url and not media_id:
                return
        if not url and not media_id:
            return
        items.append(
            {
                "url": url,
                "provider_media_id": media_id,
                "content_type": content_type if content_type.startswith("image/") else "image/jpeg",
            }
        )

    img = record.get("image")
    if isinstance(img, dict):
        _append(img)
    media = record.get("media") or record.get("medias")
    if isinstance(media, list):
        for row in media:
            _append(row)
    elif isinstance(media, dict):
        _append(media)
    content = record.get("content") if isinstance(record.get("content"), dict) else {}
    if isinstance(content, dict):
        _append(content.get("image") if isinstance(content.get("image"), dict) else content)
    wa = record.get("whatsapp_message")
    if isinstance(wa, dict):
        _append(wa.get("image"))
        nested = wa.get("media")
        if isinstance(nested, list):
            for row in nested:
                _append(row)
        elif isinstance(nested, dict):
            _append(nested)

    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        key = f"{item.get('provider_media_id')}::{item.get('url')}"
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _resolve_meta_media_url(db: Session, media_id: str) -> str | None:
    mid = str(media_id or "").strip()
    if not mid:
        return None
    try:
        from app.services.meta_whatsapp_service import MetaWhatsappService
        from app.services.meta_whatsapp_config_service import graph_api_base

        config, enabled = MetaWhatsappService._config(db)
        if not enabled:
            return None
        token = MetaWhatsappService._require_token(config)
        base = graph_api_base(config)
        url = f"{base.rstrip('/')}/{mid}"
        with httpx.Client(timeout=30.0, verify=httpx_ssl_verify(), follow_redirects=True) as client:
            resp = client.get(url, headers={"Authorization": f"Bearer {token}"})
            resp.raise_for_status()
            data = resp.json() if resp.content else {}
        return str((data or {}).get("url") or "").strip() or None
    except Exception as exc:
        logger.warning("expo_card_meta_media_resolve_failed media_id=%s err=%s", mid, exc)
        return None


def download_image_bytes(db: Session, *, media_url: str, max_bytes: int = 8_000_000) -> tuple[bytes, str]:
    headers = _download_auth_headers(db, media_url)
    with httpx.Client(timeout=45.0, verify=httpx_ssl_verify(), follow_redirects=True) as client:
        with client.stream("GET", media_url, headers=headers) as response:
            response.raise_for_status()
            ctype = str(response.headers.get("content-type") or "image/jpeg").split(";")[0].strip().lower()
            chunks: list[bytes] = []
            total = 0
            for chunk in response.iter_bytes(chunk_size=65536):
                if not chunk:
                    continue
                total += len(chunk)
                if total > max_bytes:
                    raise ValueError("Business card image exceeds maximum size")
                chunks.append(chunk)
    return b"".join(chunks), ctype or "image/jpeg"


def _clean_phone(raw: str | None) -> str | None:
    text = str(raw or "").strip()
    if not text:
        return None
    digits = re.sub(r"[^\d+]", "", text)
    return digits[:32] if digits else None


def _clean_email(raw: str | None) -> str | None:
    text = str(raw or "").strip().lower()
    if not text or "@" not in text:
        return None
    return text[:255]


class ExpoBusinessCardService:
    @staticmethod
    def extract_from_inbound(db: Session, record: dict[str, Any] | None) -> dict[str, str | None]:
        """Download inbound WA image and OCR contact fields. Empty dict on failure."""
        items = extract_image_media_items(record)
        if not items:
            return {}
        item = items[0]
        url = str(item.get("url") or "").strip()
        media_id = str(item.get("provider_media_id") or "").strip()
        if not url and media_id:
            url = _resolve_meta_media_url(db, media_id) or ""
        if not url:
            logger.warning("expo_card_no_media_url media_id=%s", media_id)
            return {}
        try:
            raw, ctype = download_image_bytes(db, media_url=url)
        except Exception as exc:
            logger.warning("expo_card_download_failed err=%s", exc)
            return {}
        return ExpoBusinessCardService.extract_from_bytes(db, image_bytes=raw, content_type=ctype)

    @staticmethod
    def extract_from_bytes(
        db: Session,
        *,
        image_bytes: bytes,
        content_type: str = "image/jpeg",
    ) -> dict[str, str | None]:
        if not image_bytes:
            return {}
        mime = content_type if str(content_type).startswith("image/") else "image/jpeg"
        b64 = base64.b64encode(image_bytes).decode("ascii")
        data_url = f"data:{mime};base64,{b64}"
        try:
            config = OpenAIProviderService._config(db)
        except Exception as exc:
            logger.warning("expo_card_openai_unavailable err=%s", exc)
            return {}
        model = str(config.get("default_model") or "gpt-4o-mini").strip() or "gpt-4o-mini"
        # Prefer a vision-capable model when admin set something odd
        if "realtime" in model.lower() or model.startswith("whisper"):
            model = "gpt-4o-mini"
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You extract contact details from a business card photo. "
                        "Return JSON only. Use null when a field is missing or unreadable. "
                        "Prefer the person's name (not job title) for name."
                    ),
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Extract name, company, email, and phone from this business card.",
                        },
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                },
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "business_card_contact",
                    "schema": _CARD_SCHEMA,
                    "strict": True,
                },
            },
            "max_tokens": 300,
            "temperature": 0,
        }
        try:
            response = OpenAIProviderService._http_client().post(
                OpenAIProviderService._endpoint_url(config, "/v1/chat/completions"),
                json=payload,
                headers=OpenAIProviderService._headers(config),
                timeout=60.0,
            )
            response.raise_for_status()
            raw = response.json()
            choices = raw.get("choices") or []
            message = (choices[0] or {}).get("message") if choices else {}
            text = str((message or {}).get("content") or "").strip()
            parsed = json.loads(text) if text else {}
            if not isinstance(parsed, dict):
                return {}
            return {
                "name": (str(parsed.get("name") or "").strip() or None),
                "company": (str(parsed.get("company") or "").strip() or None),
                "email": _clean_email(parsed.get("email")),
                "phone": _clean_phone(parsed.get("phone")),
            }
        except Exception as exc:
            logger.warning("expo_card_ocr_failed err=%s", exc)
            return {}

    @staticmethod
    def confirmation_message(fields: dict[str, str | None] | None) -> str:
        fields = fields or {}
        lines: list[str] = []
        if fields.get("name"):
            lines.append(f"• Name: {fields['name']}")
        if fields.get("company"):
            lines.append(f"• Company: {fields['company']}")
        if fields.get("email"):
            lines.append(f"• Email: {fields['email']}")
        if fields.get("phone"):
            lines.append(f"• Phone: {fields['phone']}")
        if not lines:
            return "Thanks — I've got your business card photo."
        return "Got your details:\n" + "\n".join(lines)
