"""Fetch Telnyx/Meta WhatsApp templates and store them for sends by template_id."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import Any

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.http_ssl import httpx_ssl_verify
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.sales_whatsapp_telnyx_service import (
    TELNYX_SALES_TEMPLATE_NAMES,
    TEST_TEMPLATE_VARIABLES,
    build_telnyx_components,
    build_test_components_for_template_name,
    template_key_for_telnyx_name,
)
from app.services.telnyx_api_key import normalize_telnyx_api_key, require_telnyx_api_key
from app.services.telnyx_messaging_service import _TEMPLATE_UUID_RE
from app.services.telnyx_voice_service import _telnyx_config, _telnyx_headers, _telnyx_http_error_detail, TelnyxConfigError

logger = logging.getLogger(__name__)

TELNYX_WHATSAPP_TEMPLATES_URL = "https://api.telnyx.com/v2/whatsapp/message_templates"
_VAR_RE = re.compile(r"\{\{(\d+)\}\}")


class TelnyxWhatsappTemplateSyncError(RuntimeError):
    pass


def _now() -> datetime:
    return datetime.utcnow()


def _sales_key_for_name(name: str | None) -> str | None:
    return template_key_for_telnyx_name(name)


def _body_preview(components: list[Any] | None) -> str | None:
    if not isinstance(components, list):
        return None
    for comp in components:
        if not isinstance(comp, dict):
            continue
        if str(comp.get("type") or "").upper() == "BODY":
            text = str(comp.get("text") or "").strip()
            return text[:2000] if text else None
    return None


def _body_variable_count(components: list[Any] | None) -> int:
    preview = _body_preview(components)
    if not preview:
        return 0
    nums = {int(m.group(1)) for m in _VAR_RE.finditer(preview)}
    return max(nums) if nums else 0


def _send_template_id_from_api_item(item: dict[str, Any]) -> str:
    """Telnyx send API uses list `id` (UUID). `template_id` is often Meta's numeric id."""
    telnyx_id = str(item.get("id") or "").strip()
    meta_id = str(item.get("template_id") or "").strip()
    if telnyx_id and (_TEMPLATE_UUID_RE.match(telnyx_id) or not meta_id.isdigit()):
        return telnyx_id
    if meta_id and _TEMPLATE_UUID_RE.match(meta_id):
        return meta_id
    return telnyx_id or meta_id


def send_template_id_for_row(row: TelnyxWhatsappTemplate) -> str:
    """Id to pass to Telnyx messages API (prefer Telnyx UUID over Meta numeric)."""
    record = str(row.telnyx_record_id or "").strip()
    stored = str(row.template_id or "").strip()
    if stored and not (stored.isdigit() and len(stored) >= 10):
        return stored
    if record and (_TEMPLATE_UUID_RE.match(record) or not stored.isdigit()):
        return record
    return stored or record


def template_to_dict(row: TelnyxWhatsappTemplate) -> dict[str, Any]:
    send_id = send_template_id_for_row(row)
    return {
        "id": row.id,
        "telnyx_record_id": row.telnyx_record_id,
        "template_id": send_id,
        "meta_template_id": (
            row.template_id
            if row.template_id != send_id and str(row.template_id or "").isdigit()
            else None
        ),
        "name": row.name,
        "language": row.language,
        "category": row.category,
        "status": row.status,
        "sales_template_key": row.sales_template_key,
        "body_preview": row.body_preview,
        "waba_id": row.waba_id,
        "rejection_reason": row.rejection_reason,
        "synced_at": row.synced_at.isoformat() if row.synced_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


class TelnyxWhatsappTemplateSyncService:
    @staticmethod
    def _config(db: Session) -> dict[str, Any]:
        try:
            return _telnyx_config(db)
        except TelnyxConfigError as e:
            raise TelnyxWhatsappTemplateSyncError(str(e)) from e

    @staticmethod
    def fetch_from_telnyx(db: Session) -> list[dict[str, Any]]:
        config = TelnyxWhatsappTemplateSyncService._config(db)
        api_key = normalize_telnyx_api_key(str(config.get("api_key") or ""))
        if not api_key:
            api_key, _ = require_telnyx_api_key(db)

        waba_id = str(config.get("whatsapp_waba_id") or config.get("waba_id") or "").strip()
        params: dict[str, Any] = {"page[size]": 250, "page[number]": 1}
        if waba_id:
            params["filter[waba_id]"] = waba_id

        rows: list[dict[str, Any]] = []
        try:
            with httpx.Client(timeout=30.0, verify=httpx_ssl_verify()) as client:
                while True:
                    response = client.get(
                        TELNYX_WHATSAPP_TEMPLATES_URL,
                        params=params,
                        headers=_telnyx_headers(api_key),
                    )
                    response.raise_for_status()
                    body = response.json()
                    chunk = body.get("data") if isinstance(body, dict) else []
                    if isinstance(chunk, list):
                        rows.extend(item for item in chunk if isinstance(item, dict))

                    meta = body.get("meta") if isinstance(body, dict) else {}
                    if not isinstance(meta, dict):
                        break
                    page_number = int(meta.get("page_number") or params["page[number]"])
                    total_pages = int(meta.get("total_pages") or 1)
                    if page_number >= total_pages:
                        break
                    params["page[number]"] = page_number + 1
        except httpx.HTTPStatusError as e:
            raise TelnyxWhatsappTemplateSyncError(_telnyx_http_error_detail(e)) from e
        except Exception as e:
            raise TelnyxWhatsappTemplateSyncError(str(e)) from e

        return rows

    @staticmethod
    def sync(db: Session) -> dict[str, Any]:
        remote = TelnyxWhatsappTemplateSyncService.fetch_from_telnyx(db)
        now = _now()
        synced = 0
        approved = 0
        for item in remote:
            record_id = str(item.get("id") or "").strip()
            meta_template_id = str(item.get("template_id") or "").strip()
            send_template_id = _send_template_id_from_api_item(item)
            name = str(item.get("name") or "").strip()
            if not record_id or not send_template_id or not name:
                continue

            language = str(item.get("language") or "en_US").strip() or "en_US"
            status = str(item.get("status") or "UNKNOWN").strip().upper()
            category = str(item.get("category") or "").strip() or None
            components = item.get("components")
            components_json = json.dumps(components, ensure_ascii=False) if components is not None else None
            waba = item.get("whatsapp_business_account")
            waba_id = str(waba.get("id") or "").strip() if isinstance(waba, dict) else None
            sales_key = _sales_key_for_name(name)

            existing = db.execute(
                select(TelnyxWhatsappTemplate).where(TelnyxWhatsappTemplate.telnyx_record_id == record_id)
            ).scalar_one_or_none()
            if existing is None:
                existing = TelnyxWhatsappTemplate(
                    telnyx_record_id=record_id,
                    template_id=send_template_id,
                    name=name,
                    language=language,
                    created_at=now,
                )
                db.add(existing)

            existing.template_id = send_template_id
            existing.name = name
            existing.language = language
            existing.category = category
            existing.status = status
            existing.sales_template_key = sales_key
            existing.body_preview = _body_preview(components if isinstance(components, list) else None)
            existing.components_json = components_json
            existing.waba_id = waba_id
            existing.rejection_reason = str(item.get("rejection_reason") or "").strip() or None
            existing.synced_at = now
            existing.updated_at = now
            synced += 1
            if status == "APPROVED":
                approved += 1

        db.commit()
        stored = list(db.execute(select(TelnyxWhatsappTemplate).order_by(TelnyxWhatsappTemplate.name.asc())).scalars().all())
        return {
            "ok": True,
            "synced": synced,
            "approved": approved,
            "templates": [template_to_dict(row) for row in stored],
        }

    @staticmethod
    def list_stored(db: Session, *, approved_only: bool = False) -> list[dict[str, Any]]:
        q = select(TelnyxWhatsappTemplate).order_by(TelnyxWhatsappTemplate.name.asc())
        rows = list(db.execute(q).scalars().all())
        if approved_only:
            rows = [row for row in rows if str(row.status or "").upper() == "APPROVED"]
        return [template_to_dict(row) for row in rows]

    @staticmethod
    def get_for_sales_key(db: Session, template_key: str) -> TelnyxWhatsappTemplate | None:
        key = str(template_key or "").strip().lower()
        if not key:
            return None
        rows = list(
            db.execute(
                select(TelnyxWhatsappTemplate)
                .where(TelnyxWhatsappTemplate.sales_template_key == key)
                .order_by(TelnyxWhatsappTemplate.updated_at.desc())
            ).scalars().all()
        )
        for row in rows:
            if str(row.status or "").upper() == "APPROVED":
                return row
        return rows[0] if rows else None

    @staticmethod
    def resolve_for_send(
        db: Session,
        *,
        template_name: str | None = None,
        template_id: str | None = None,
        sales_template_key: str | None = None,
    ) -> TelnyxWhatsappTemplate | None:
        tid = str(template_id or "").strip()
        if tid:
            row = db.execute(
                select(TelnyxWhatsappTemplate).where(TelnyxWhatsappTemplate.template_id == tid).limit(1)
            ).scalar_one_or_none()
            if row is None:
                row = db.execute(
                    select(TelnyxWhatsappTemplate).where(TelnyxWhatsappTemplate.telnyx_record_id == tid).limit(1)
                ).scalar_one_or_none()
            if row is not None:
                return row

        name = str(template_name or "").strip()
        if name:
            name_lower = name.lower()
            rows = list(
                db.execute(
                    select(TelnyxWhatsappTemplate)
                    .where(func.lower(TelnyxWhatsappTemplate.name) == name_lower)
                    .order_by(TelnyxWhatsappTemplate.updated_at.desc())
                ).scalars().all()
            )
            for row in rows:
                if str(row.status or "").upper() == "APPROVED":
                    return row
            if rows:
                return rows[0]

        if sales_template_key:
            return TelnyxWhatsappTemplateSyncService.get_for_sales_key(db, sales_template_key)

        return None

    @staticmethod
    def build_components_for_row(
        row: TelnyxWhatsappTemplate | None,
        *,
        variables: dict[str, str] | None = None,
    ) -> list[dict[str, Any]] | None:
        if row is None:
            return None
        vars_ = variables or TEST_TEMPLATE_VARIABLES
        if row.sales_template_key:
            return build_telnyx_components(row.sales_template_key, vars_)
        built = build_test_components_for_template_name(row.name)
        if built is not None:
            return built
        try:
            components = json.loads(row.components_json or "null")
        except json.JSONDecodeError:
            components = None
        count = _body_variable_count(components if isinstance(components, list) else None)
        if count <= 0:
            return None
        first = str(vars_.get("first_name") or "Alex")
        filler = [
            first,
            str(vars_.get("offer_line") or "VOXBULK offer"),
            str(vars_.get("offer_summary") or "Special offer"),
        ]
        values = filler[:count]
        while len(values) < count:
            values.append("—")
        return [{"type": "body", "parameters": [{"type": "text", "text": v[:1024]} for v in values]}]

    @staticmethod
    def sales_template_names() -> dict[str, str]:
        return dict(TELNYX_SALES_TEMPLATE_NAMES)
