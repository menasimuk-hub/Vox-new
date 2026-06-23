"""Appointment Manager WhatsApp template library (4 UTILITY templates)."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import func, select
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
    SurveyWhatsappTemplateError,
    SurveyWhatsappTemplateService,
    _body_preview,
    _buttons_from_components,
    _dumps,
    _effective_components,
    _extract_example_values,
    _is_local_row,
    _loads,
    _now,
    _refresh_local_sync_status,
    _try_link_existing_remote_template,
    ensure_meta_examples_on_components,
    normalize_wa_template_category,
    template_workflow_state,
    validate_meta_variable_order,
)
from app.services.telnyx_whatsapp_template_sync_service import (
    TelnyxWhatsappTemplateSyncError,
    TelnyxWhatsappTemplateSyncService,
    send_template_id_for_row,
    template_to_dict,
)
from app.services.wa_template_meta_sync import default_wa_template_language, normalize_wa_template_language

logger = logging.getLogger(__name__)

_LOCAL_ID_PREFIX = "local-"


class AppointmentWhatsappTemplateError(RuntimeError):
    def __init__(self, message: str, *, payload: dict[str, Any] | None = None):
        super().__init__(message)
        self.payload = payload


def appointment_template_to_dict(row: TelnyxWhatsappTemplate) -> dict[str, Any]:
    base = template_to_dict(row)
    components = _effective_components(row)
    sync_status = _refresh_local_sync_status(row)
    row.local_sync_status = sync_status
    examples = _loads(row.example_values_json)
    if not isinstance(examples, list):
        examples = _extract_example_values(components)
    spec = appointment_spec_by_key(str(row.sales_template_key or ""))
    workflow = template_workflow_state(row)
    return {
        **base,
        "display_name": row.display_name or (spec or {}).get("display_name") or row.name,
        "description": row.customer_description or (spec or {}).get("description"),
        "sales_template_key": row.sales_template_key,
        "approval_status": str(row.status or "UNKNOWN").upper(),
        "sync_status_label": sync_status.replace("_", " ").title(),
        "active_for_appointment": bool(getattr(row, "active_for_appointment", True)),
        "example_values": examples,
        "draft_components": _loads(row.draft_components_json),
        "remote_components": _loads(row.components_json),
        "buttons": _buttons_from_components(components),
        "footer": next(
            (
                str(c.get("text") or "")
                for c in components
                if isinstance(c, dict) and str(c.get("type") or "").upper() == "FOOTER"
            ),
            "",
        ),
        "last_pushed_at": row.last_pushed_at.isoformat() if row.last_pushed_at else None,
        "last_push_error": row.last_push_error,
        "is_local_only": _is_local_row(row),
        "send_template_id": send_template_id_for_row(row),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        **workflow,
    }


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
            if existing is not None and str(existing.status or "").upper() == "DELETED":
                continue
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
                if str(existing.status or "").upper() == "DELETED":
                    continue
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
        rows = [row for row in rows if str(row.status or "").upper() != "DELETED"]
        rows.sort(key=lambda r: APPOINTMENT_WA_TEMPLATE_KEYS.index(str(r.sales_template_key or "")) if str(r.sales_template_key or "") in APPOINTMENT_WA_TEMPLATE_KEYS else 99)
        return [appointment_template_to_dict(row) for row in rows]

    @staticmethod
    def get_template_detail(db: Session, template_id: int) -> dict[str, Any] | None:
        row = AppointmentWhatsappTemplateService.get_template(db, template_id)
        if row is None:
            return None
        return appointment_template_to_dict(row)

    @staticmethod
    def row_to_admin_dict(row: TelnyxWhatsappTemplate) -> dict[str, Any]:
        return appointment_template_to_dict(row)

    @staticmethod
    def save_draft(db: Session, row: TelnyxWhatsappTemplate, payload: dict[str, Any]) -> TelnyxWhatsappTemplate:
        if "display_name" in payload:
            row.display_name = str(payload.get("display_name") or row.display_name or row.name).strip() or row.name
        if "customer_description" in payload:
            row.customer_description = str(payload.get("customer_description") or "").strip() or None
        if "language" in payload and str(payload.get("language") or "").strip():
            lang_code, lang_error = normalize_wa_template_language(str(payload.get("language")), db=db)
            if lang_error:
                raise AppointmentWhatsappTemplateError(
                    lang_error,
                    payload={"message": lang_error, "template_name": row.name, "requires_language_fix": True},
                )
            row.language = lang_code or default_wa_template_language(db)
        if "category" in payload:
            row.category = normalize_wa_template_category(payload.get("category"), required=False)
        if "active_for_appointment" in payload:
            row.active_for_appointment = bool(payload["active_for_appointment"])
        components = payload.get("components")
        if isinstance(components, list):
            examples = payload.get("example_values")
            example_list = [str(v) for v in examples] if isinstance(examples, list) else None
            if example_list is None:
                loaded = _loads(row.example_values_json)
                example_list = [str(v) for v in loaded] if isinstance(loaded, list) else None
            var_order_error = validate_meta_variable_order(components)
            if var_order_error:
                raise AppointmentWhatsappTemplateError(
                    var_order_error,
                    payload={"message": var_order_error, "template_name": row.name},
                )
            components = ensure_meta_examples_on_components(components, example_list, row=row)
            row.draft_components_json = _dumps(components)
            row.body_preview = _body_preview(components)
            row.example_values_json = _dumps(_extract_example_values(components))
        examples = payload.get("example_values")
        if isinstance(examples, list):
            row.example_values_json = _dumps([str(v) for v in examples])
        row.local_sync_status = _refresh_local_sync_status(row)
        row.updated_at = _now()
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def rename_for_meta_sync(db: Session, row: TelnyxWhatsappTemplate, new_name: str) -> TelnyxWhatsappTemplate:
        try:
            return SurveyWhatsappTemplateService.rename_for_meta_sync(db, row, new_name)
        except SurveyWhatsappTemplateError as exc:
            raise AppointmentWhatsappTemplateError(str(exc), payload=exc.payload) from exc

    @staticmethod
    def push_to_telnyx(db: Session, row: TelnyxWhatsappTemplate) -> dict[str, Any]:
        try:
            return SurveyWhatsappTemplateService.push_to_telnyx(db, row)
        except SurveyWhatsappTemplateError as exc:
            raise AppointmentWhatsappTemplateError(str(exc), payload=exc.payload) from exc

    @staticmethod
    def refresh_telnyx_status(db: Session, row: TelnyxWhatsappTemplate) -> dict[str, Any]:
        try:
            return SurveyWhatsappTemplateService.refresh_telnyx_status(db, row)
        except SurveyWhatsappTemplateError as exc:
            raise AppointmentWhatsappTemplateError(str(exc), payload=exc.payload) from exc

    @staticmethod
    def sync_from_telnyx(db: Session) -> dict[str, Any]:
        logger.info("appointment_wa_template_sync_start")
        try:
            summary = TelnyxWhatsappTemplateSyncService.sync(db)
            AppointmentWhatsappTemplateService.ensure_catalog_seeded(db)
            linked = 0
            for key in APPOINTMENT_WA_TEMPLATE_KEYS:
                spec = appointment_spec_by_key(key)
                if not spec:
                    continue
                row = AppointmentWhatsappTemplateService._find_row_for_spec(
                    db,
                    key,
                    str(spec.get("telnyx_name") or ""),
                )
                if row is None or not _is_local_row(row):
                    continue
                lang_code, _ = normalize_wa_template_language(row.language, db=db)
                result = _try_link_existing_remote_template(
                    db,
                    row,
                    language=lang_code or default_wa_template_language(db),
                )
                if result is not None:
                    linked += 1
            matched = list(
                db.execute(
                    select(TelnyxWhatsappTemplate).where(
                        TelnyxWhatsappTemplate.sales_template_key.in_(list(APPOINTMENT_WA_TEMPLATE_KEYS))
                    )
                ).scalars().all()
            )
            return {
                **summary,
                "ok": True,
                "message": f"Synced {summary.get('synced', 0)} Telnyx templates; {len(matched)} appointment templates in library."
                + (f" Linked {linked} existing remote template(s)." if linked else ""),
                "appointment_templates": len(matched),
                "appointment_linked": linked,
            }
        except TelnyxWhatsappTemplateSyncError as exc:
            return {
                "ok": False,
                "message": str(exc),
                "provider_error": str(exc),
                "errors": [str(exc)],
            }
        except Exception as exc:
            logger.exception("appointment_wa_template_sync_failed")
            return {
                "ok": False,
                "message": f"WA Appointment sync failed: {exc}",
                "errors": [str(exc)],
            }

    @staticmethod
    def delete_template(db: Session, row: TelnyxWhatsappTemplate) -> dict[str, Any]:
        record_id = str(row.telnyx_record_id or "").strip()
        template_id = int(row.id)
        if record_id and not record_id.startswith(_LOCAL_ID_PREFIX):
            try:
                TelnyxWhatsappTemplateSyncService.delete_remote_template(db, record_id)
            except TelnyxWhatsappTemplateSyncError as exc:
                raise AppointmentWhatsappTemplateError(
                    f"Telnyx delete failed: {exc}",
                    payload={"message": str(exc), "provider_error": str(exc)},
                ) from exc
        row.status = "DELETED"
        row.active_for_appointment = False
        row.local_sync_status = "deleted"
        row.updated_at = _now()
        db.add(row)
        db.commit()
        return {
            "ok": True,
            "message": "Template deleted from Telnyx and removed from the appointment catalog.",
            "template_id": template_id,
        }

    @staticmethod
    def build_preview(
        db: Session,
        row: TelnyxWhatsappTemplate,
        *,
        first_name: str = "Alex",
        business_name: str = "Your clinic",
    ) -> dict[str, Any]:
        return SurveyWhatsappTemplateService.build_preview(
            db,
            row,
            business_name=business_name,
            first_name=first_name,
        )
