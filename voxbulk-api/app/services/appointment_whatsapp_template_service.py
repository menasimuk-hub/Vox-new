"""Appointment Manager WhatsApp template library (4 UTILITY templates)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data.appointment_whatsapp_template_catalog import (
    APPOINTMENT_WA_TEMPLATE_KEYS,
    APPOINTMENT_WA_TEMPLATE_SPECS,
    appointment_catalog_telnyx_names,
    appointment_spec_by_key,
    appointment_spec_components,
)
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.survey_whatsapp_template_service import (
    _body_preview,
    _buttons_from_components,
    _dumps,
    _is_local_row,
    _loads,
    _now,
)
from app.services.wa_template_meta_sync import default_wa_template_language

_LOCAL_ID_PREFIX = "local-"


class AppointmentWhatsappTemplateService:
    @staticmethod
    def _is_appointment_row(row: TelnyxWhatsappTemplate) -> bool:
        key = str(row.sales_template_key or "").strip().lower()
        if key in APPOINTMENT_WA_TEMPLATE_KEYS:
            return True
        name = str(row.name or "").strip().lower()
        return name in appointment_catalog_telnyx_names()

    @staticmethod
    def _find_row_for_spec(db: Session, sales_key: str, telnyx_name: str) -> TelnyxWhatsappTemplate | None:
        key = str(sales_key or "").strip().lower()
        name = str(telnyx_name or "").strip().lower()
        rows = list(
            db.execute(
                select(TelnyxWhatsappTemplate).where(
                    TelnyxWhatsappTemplate.sales_template_key == key,
                )
            ).scalars()
        )
        if rows:
            return rows[0]
        rows = list(
            db.execute(
                select(TelnyxWhatsappTemplate).where(
                    TelnyxWhatsappTemplate.name == name,
                )
            ).scalars()
        )
        return rows[0] if rows else None

    @staticmethod
    def ensure_catalog_seeded(db: Session) -> list[TelnyxWhatsappTemplate]:
        rows: list[TelnyxWhatsappTemplate] = []
        now = _now()
        for spec in APPOINTMENT_WA_TEMPLATE_SPECS:
            key = str(spec["sales_template_key"])
            telnyx_name = str(spec["telnyx_name"])
            existing = AppointmentWhatsappTemplateService._find_row_for_spec(db, key, telnyx_name)
            components = appointment_spec_components(spec)
            examples = [str(v) for v in spec.get("example_values") or []]
            if existing is None:
                local_id = f"{_LOCAL_ID_PREFIX}{uuid.uuid4().hex}"
                row = TelnyxWhatsappTemplate(
                    telnyx_record_id=local_id,
                    template_id=local_id,
                    name=telnyx_name,
                    display_name=str(spec.get("display_name") or telnyx_name),
                    customer_description=str(spec.get("description") or ""),
                    language=default_wa_template_language(db),
                    category=str(spec.get("category") or "UTILITY"),
                    status="LOCAL_DRAFT",
                    sales_template_key=key,
                    body_preview=_body_preview(components),
                    draft_components_json=_dumps(components),
                    example_values_json=_dumps(examples),
                    local_sync_status="draft",
                    active_for_appointment=True,
                    created_at=now,
                    updated_at=now,
                    synced_at=now,
                )
                db.add(row)
                db.flush()
                rows.append(row)
                continue

            changed = False
            if not existing.sales_template_key:
                existing.sales_template_key = key
                changed = True
            if not existing.display_name:
                existing.display_name = str(spec.get("display_name") or telnyx_name)
                changed = True
            if not existing.customer_description:
                existing.customer_description = str(spec.get("description") or "")
                changed = True
            if not getattr(existing, "active_for_appointment", True):
                existing.active_for_appointment = True
                changed = True
            if not existing.draft_components_json and _is_local_row(existing):
                existing.draft_components_json = _dumps(components)
                existing.body_preview = _body_preview(components)
                existing.example_values_json = _dumps(examples)
                existing.local_sync_status = "draft"
                changed = True
            if changed:
                existing.updated_at = now
                db.add(existing)
            rows.append(existing)
        db.commit()
        return rows

    @staticmethod
    def row_to_customer_dict(row: TelnyxWhatsappTemplate) -> dict[str, Any]:
        spec = appointment_spec_by_key(str(row.sales_template_key or row.name or ""))
        components = _loads(row.draft_components_json) or _loads(row.components_json)
        if not isinstance(components, list):
            components = appointment_spec_components(spec) if spec else []
        footer = next(
            (
                str(c.get("text") or "")
                for c in components
                if isinstance(c, dict) and str(c.get("type") or "").upper() == "FOOTER"
            ),
            str((spec or {}).get("footer") or ""),
        )
        body = row.body_preview or str((spec or {}).get("body") or "")
        return {
            "name": str(row.name or row.sales_template_key or ""),
            "label": row.display_name or str((spec or {}).get("display_name") or row.name),
            "description": row.customer_description or str((spec or {}).get("description") or ""),
            "body": body,
            "footer": footer,
            "buttons": _buttons_from_components(components if isinstance(components, list) else []),
            "approval_status": str(row.status or "UNKNOWN").upper(),
            "active": bool(getattr(row, "active_for_appointment", True)),
        }

    @staticmethod
    def list_customer_templates(db: Session) -> list[dict[str, Any]]:
        AppointmentWhatsappTemplateService.ensure_catalog_seeded(db)
        payload: list[dict[str, Any]] = []
        for key in APPOINTMENT_WA_TEMPLATE_KEYS:
            spec = appointment_spec_by_key(key)
            if not spec:
                continue
            row = AppointmentWhatsappTemplateService._find_row_for_spec(
                db,
                key,
                str(spec.get("telnyx_name") or ""),
            )
            if row is None or not getattr(row, "active_for_appointment", True):
                continue
            payload.append(AppointmentWhatsappTemplateService.row_to_customer_dict(row))
        return payload

    @staticmethod
    def get_template(db: Session, template_id: int) -> TelnyxWhatsappTemplate | None:
        row = db.get(TelnyxWhatsappTemplate, template_id)
        if row is None or not AppointmentWhatsappTemplateService._is_appointment_row(row):
            return None
        return row

    @staticmethod
    def list_admin_templates(db: Session) -> list[dict[str, Any]]:
        AppointmentWhatsappTemplateService.ensure_catalog_seeded(db)
        rows = list(
            db.execute(
                select(TelnyxWhatsappTemplate).where(
                    TelnyxWhatsappTemplate.sales_template_key.in_(APPOINTMENT_WA_TEMPLATE_KEYS),
                )
            ).scalars()
        )
        rows.sort(key=lambda r: APPOINTMENT_WA_TEMPLATE_KEYS.index(str(r.sales_template_key or "")) if str(r.sales_template_key or "") in APPOINTMENT_WA_TEMPLATE_KEYS else 99)
        return [AppointmentWhatsappTemplateService.row_to_admin_dict(row) for row in rows]

    @staticmethod
    def row_to_admin_dict(row: TelnyxWhatsappTemplate) -> dict[str, Any]:
        customer = AppointmentWhatsappTemplateService.row_to_customer_dict(row)
        return {
            **customer,
            "id": row.id,
            "name": row.name,
            "display_name": row.display_name or customer.get("label"),
            "status": str(row.status or "UNKNOWN").upper(),
            "local_sync_status": str(row.local_sync_status or "draft"),
            "active_for_appointment": bool(getattr(row, "active_for_appointment", True)),
            "language": row.language,
            "category": row.category,
        }

    @staticmethod
    def save_draft(db: Session, row: TelnyxWhatsappTemplate, payload: dict[str, Any]) -> TelnyxWhatsappTemplate:
        if "display_name" in payload:
            row.display_name = str(payload.get("display_name") or row.display_name or row.name).strip() or row.name
        if "customer_description" in payload:
            row.customer_description = str(payload.get("customer_description") or "").strip() or None
        if "active_for_appointment" in payload:
            row.active_for_appointment = bool(payload["active_for_appointment"])
        row.updated_at = _now()
        db.add(row)
        db.commit()
        db.refresh(row)
        return row
