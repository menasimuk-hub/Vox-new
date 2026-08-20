"""Extract name / company / email / phone from an Expo business-card photo (OpenAI vision)."""

from __future__ import annotations

import base64
import json
import logging
import re
import uuid
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
    from urllib.parse import urljoin

    from app.utils.safe_outbound_url import classify_media_download_host, media_url_hostname

    initial_kind = classify_media_download_host(media_url_hostname(media_url))
    if initial_kind is None:
        raise ValueError("Media URL host is not allowlisted for download")

    current_url = str(media_url)
    with httpx.Client(timeout=45.0, verify=httpx_ssl_verify(), follow_redirects=False) as client:
        for _redir in range(5):
            headers = _download_auth_headers(db, current_url)
            with client.stream("GET", current_url, headers=headers) as response:
                if response.status_code in {301, 302, 303, 307, 308}:
                    loc = str(response.headers.get("location") or "").strip()
                    if not loc:
                        raise ValueError("Media download redirect missing Location")
                    next_url = urljoin(current_url, loc)
                    next_kind = classify_media_download_host(media_url_hostname(next_url))
                    if next_kind != initial_kind:
                        raise ValueError("Media download redirect left allowlisted host")
                    current_url = next_url
                    continue
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
        raise ValueError("Media download exceeded redirect limit")


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


def is_placeholder_phone(phone: str | None) -> bool:
    p = str(phone or "").strip().lower()
    return (not p) or p.startswith("web-pending-") or p.startswith("web-card-")


def is_placeholder_email(email: str | None) -> bool:
    e = str(email or "").strip().lower()
    return (not e) or e.endswith("@expo.local") or e in {"pending@expo.local", "card@expo.local"}


def _normalize_card_image_bytes(image_bytes: bytes, content_type: str = "image/jpeg") -> tuple[bytes, str]:
    """Convert HEIC/PNG/WebP (etc.) to JPEG so vision OCR accepts the payload."""
    mime = str(content_type or "").split(";")[0].strip().lower() or "image/jpeg"
    if mime in {"image/jpeg", "image/jpg"} and len(image_bytes) < 6_000_000:
        return image_bytes, "image/jpeg"
    try:
        import io

        from PIL import Image, ImageOps

        img = Image.open(io.BytesIO(image_bytes))
        img = ImageOps.exif_transpose(img)
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        elif img.mode == "L":
            img = img.convert("RGB")
        # Cap long edge for vision API cost/latency
        max_edge = 1280
        w, h = img.size
        scale = min(1.0, max_edge / float(max(w, h) or 1))
        if scale < 1.0:
            img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=82, optimize=True)
        return buf.getvalue(), "image/jpeg"
    except Exception as exc:
        logger.warning("expo_card_image_normalize_failed err=%s mime=%s", exc, mime)
        return image_bytes, mime if mime.startswith("image/") else "image/jpeg"


def _parse_card_json(text: str) -> dict[str, Any]:
    raw = str(text or "").strip()
    if not raw:
        return {}
    # Models often wrap JSON in ```json fences
    if "```" in raw:
        start = raw.find("```")
        chunk = raw[start + 3 :]
        if chunk.lstrip().lower().startswith("json"):
            chunk = chunk.lstrip()[4:]
        end = chunk.find("```")
        if end >= 0:
            chunk = chunk[:end]
        raw = chunk.strip()
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        # Best-effort: first {...} block
        m = re.search(r"\{[\s\S]*\}", raw)
        if not m:
            return {}
        try:
            parsed = json.loads(m.group(0))
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}


def _fields_from_parsed(parsed: dict[str, Any]) -> dict[str, str | None]:
    return {
        "name": (str(parsed.get("name") or "").strip() or None),
        "company": (str(parsed.get("company") or "").strip() or None),
        "email": _clean_email(parsed.get("email")),
        "phone": _clean_phone(parsed.get("phone")),
    }


def _ocr_prompt_messages(data_url: str) -> list[dict[str, Any]]:
    return [
        {
            "role": "system",
            "content": (
                "You extract contact details from a business card photo. "
                "Return JSON only with keys name, company, email, phone. "
                "Use null when a field is missing or unreadable. "
                "Prefer the person's full name (not job title) for name. "
                "Company is the organisation / brand name on the card. "
                "If no company is printed, use null (do not invent one from the email domain). "
                "Phone should include country code when visible."
            ),
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": "Extract name, company, email, and phone from this business card. JSON only.",
                },
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        },
    ]


def _extract_via_deepinfra(db: Session, *, data_url: str) -> dict[str, str | None]:
    """Vision OCR via DeepInfra (Gemma) — avoids OpenAI 429 rate limits on Expo cards."""
    try:
        config = OpenAIProviderService._deepinfra_config_from_db_or_env(db)
    except Exception as exc:
        logger.warning("expo_card_deepinfra_unavailable err=%s", exc)
        return {}
    model = "google/gemma-3-12b-it"
    payload = {
        "model": model,
        "messages": _ocr_prompt_messages(data_url),
        "max_tokens": 400,
        "temperature": 0,
    }
    try:
        response = OpenAIProviderService._http_client().post(
            OpenAIProviderService._endpoint_url({**config, "provider": "deepinfra"}, "/v1/chat/completions"),
            json=payload,
            headers=OpenAIProviderService._headers(config),
            timeout=90.0,
        )
        response.raise_for_status()
        raw = response.json()
        choices = raw.get("choices") or []
        message = (choices[0] or {}).get("message") if choices else {}
        text = str((message or {}).get("content") or "").strip()
        parsed = _parse_card_json(text)
        fields = _fields_from_parsed(parsed)
        if any(fields.values()):
            logger.info(
                "expo_card_ocr_ok provider=deepinfra model=%s name=%s company=%s email=%s phone=%s",
                model,
                bool(fields.get("name")),
                bool(fields.get("company")),
                bool(fields.get("email")),
                bool(fields.get("phone")),
            )
            return fields
        logger.warning("expo_card_deepinfra_empty_parse text=%s", text[:200])
        return {}
    except Exception as exc:
        logger.warning("expo_card_deepinfra_failed err=%s", exc)
        return {}


def _extract_via_openai(db: Session, *, data_url: str) -> dict[str, str | None]:
    try:
        config = OpenAIProviderService._config(db)
    except Exception as exc:
        logger.warning("expo_card_openai_unavailable err=%s", exc)
        return {}
    models = ("gpt-4o-mini", "gpt-4o")
    payload_base = {
        "messages": _ocr_prompt_messages(data_url),
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "business_card_contact",
                "schema": _CARD_SCHEMA,
                "strict": True,
            },
        },
        "max_tokens": 400,
        "temperature": 0,
    }
    last_err: Exception | None = None
    for model in models:
        payload = {**payload_base, "model": model}
        for attempt in range(2):
            try:
                response = OpenAIProviderService._http_client().post(
                    OpenAIProviderService._endpoint_url(config, "/v1/chat/completions"),
                    json=payload,
                    headers=OpenAIProviderService._headers(config),
                    timeout=90.0,
                )
                if response.status_code == 429:
                    import time

                    time.sleep(1.2 * (attempt + 1))
                    last_err = RuntimeError(f"429 Too Many Requests model={model}")
                    continue
                response.raise_for_status()
                raw = response.json()
                choices = raw.get("choices") or []
                message = (choices[0] or {}).get("message") if choices else {}
                text = str((message or {}).get("content") or "").strip()
                parsed = _parse_card_json(text)
                fields = _fields_from_parsed(parsed)
                if any(fields.values()):
                    logger.info(
                        "expo_card_ocr_ok provider=openai model=%s name=%s company=%s email=%s phone=%s",
                        model,
                        bool(fields.get("name")),
                        bool(fields.get("company")),
                        bool(fields.get("email")),
                        bool(fields.get("phone")),
                    )
                    return fields
                return {}
            except Exception as exc:
                last_err = exc
                logger.warning("expo_card_ocr_failed model=%s attempt=%s err=%s", model, attempt + 1, exc)
                if "429" in str(exc):
                    import time

                    time.sleep(1.2 * (attempt + 1))
                    continue
                break
    logger.warning("expo_card_openai_exhausted err=%s", last_err)
    return {}


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
        # Cap payload size for vision APIs (DeepInfra / OpenAI)
        image_bytes, mime = _normalize_card_image_bytes(image_bytes, content_type)
        b64 = base64.b64encode(image_bytes).decode("ascii")
        data_url = f"data:{mime};base64,{b64}"
        # Prefer DeepInfra Gemma vision — OpenAI is often rate-limited (429) on this account
        fields = _extract_via_deepinfra(db, data_url=data_url)
        if any(fields.values()):
            return fields
        return _extract_via_openai(db, data_url=data_url)

    @staticmethod
    def save_inbound_image(
        db: Session,
        *,
        org_id: str,
        booth_id: str,
        record: dict[str, Any] | None,
    ) -> tuple[dict[str, str | None], str | None]:
        """OCR + optionally persist card image under data/expo-cards/. Returns (fields, relative_path)."""
        items = extract_image_media_items(record)
        if not items:
            return {}, None
        item = items[0]
        url = str(item.get("url") or "").strip()
        media_id = str(item.get("provider_media_id") or "").strip()
        if not url and media_id:
            url = _resolve_meta_media_url(db, media_id) or ""
        if not url:
            return {}, None
        try:
            raw, ctype = download_image_bytes(db, media_url=url)
        except Exception as exc:
            logger.warning("expo_card_download_failed err=%s", exc)
            return {}, None
        fields = ExpoBusinessCardService.extract_from_bytes(db, image_bytes=raw, content_type=ctype)
        rel = ExpoBusinessCardService.persist_card_bytes(
            org_id=org_id, booth_id=booth_id, image_bytes=raw, content_type=ctype
        )
        return fields, rel

    @staticmethod
    def persist_card_bytes(
        *,
        org_id: str,
        booth_id: str,
        image_bytes: bytes,
        content_type: str = "image/jpeg",
    ) -> str | None:
        try:
            from pathlib import Path

            normalized, mime = _normalize_card_image_bytes(image_bytes, content_type)
            root = Path(__file__).resolve().parents[3] / "data" / "expo-cards" / str(org_id)
            root.mkdir(parents=True, exist_ok=True)
            ext = ".jpg"
            if "png" in mime:
                ext = ".png"
            elif "webp" in mime:
                ext = ".webp"
            name = f"{booth_id[:8]}-{uuid.uuid4().hex[:10]}{ext}"
            abs_path = root / name
            abs_path.write_bytes(normalized)
            return f"data/expo-cards/{org_id}/{name}"
        except Exception as exc:
            logger.warning("expo_card_save_failed err=%s", exc)
            return None

    @staticmethod
    def save_from_bytes(
        db: Session,
        *,
        org_id: str,
        booth_id: str,
        image_bytes: bytes,
        content_type: str = "image/jpeg",
    ) -> tuple[dict[str, str | None], str | None]:
        """OCR + persist a browser-uploaded business card image."""
        if not image_bytes:
            return {}, None
        normalized, mime = _normalize_card_image_bytes(image_bytes, content_type)
        fields = ExpoBusinessCardService.extract_from_bytes(
            db, image_bytes=normalized, content_type=mime
        )
        rel = ExpoBusinessCardService.persist_card_bytes(
            org_id=org_id,
            booth_id=booth_id,
            image_bytes=normalized,
            content_type=mime,
        )
        return fields, rel

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
