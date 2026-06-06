"""Platform Settings → WA Interview — WhatsApp template library."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.data.interview_whatsapp_template_catalog import (
    INTERVIEW_WA_TEMPLATE_KEYS,
    INTERVIEW_WA_TEMPLATE_SPECS,
    interview_catalog_telnyx_names,
    interview_spec_by_key,
    interview_spec_components,
)
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.survey_whatsapp_template_service import (
    SurveyWhatsappTemplateError,
    SurveyWhatsappTemplateService,
    _body_preview,
    _buttons_from_components,
    _content_hash,
    _dumps,
    _effective_components,
    _extract_example_values,
    _is_local_row,
    _loads,
    _now,
    _refresh_local_sync_status,
    normalize_wa_template_category,
    template_workflow_state,
    validate_meta_variable_order,
    ensure_meta_examples_on_components,
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


class InterviewWhatsappTemplateError(RuntimeError):
    def __init__(self, message: str, *, payload: dict[str, Any] | None = None):
        super().__init__(message)
        self.payload = payload


def interview_template_to_dict(row: TelnyxWhatsappTemplate) -> dict[str, Any]:
    base = template_to_dict(row)
    components = _effective_components(row)
    sync_status = _refresh_local_sync_status(row)
    row.local_sync_status = sync_status
    examples = _loads(row.example_values_json)
    if not isinstance(examples, list):
        examples = _extract_example_values(components)
    spec = interview_spec_by_key(str(row.sales_template_key or ""))
    workflow = template_workflow_state(row)
    return {
        **base,
        "display_name": row.display_name or (spec or {}).get("display_name") or row.name,
        "description": (spec or {}).get("description"),
        "sales_template_key": row.sales_template_key,
        "approval_status": str(row.status or "UNKNOWN").upper(),
        "sync_status_label": sync_status.replace("_", " ").title(),
        "active_for_interview": bool(getattr(row, "active_for_interview", True)),
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


class InterviewWhatsappTemplateService:
    @staticmethod
    def _is_interview_row(row: TelnyxWhatsappTemplate) -> bool:
        key = str(row.sales_template_key or "").strip().lower()
        if key in INTERVIEW_WA_TEMPLATE_KEYS:
            return True
        name = str(row.name or "").strip().lower()
        return name in interview_catalog_telnyx_names()

    @staticmethod
    def get_template(db: Session, template_id: int) -> TelnyxWhatsappTemplate | None:
        row = db.get(TelnyxWhatsappTemplate, template_id)
        if row is None or not InterviewWhatsappTemplateService._is_interview_row(row):
            return None
        return row

    @staticmethod
    def ensure_catalog_seeded(db: Session) -> list[TelnyxWhatsappTemplate]:
        rows: list[TelnyxWhatsappTemplate] = []
        now = _now()
        for spec in INTERVIEW_WA_TEMPLATE_SPECS:
            key = str(spec["sales_template_key"])
            telnyx_name = str(spec["telnyx_name"])
            existing = InterviewWhatsappTemplateService._find_row_for_spec(db, key, telnyx_name)
            components = interview_spec_components(spec)
            examples = [str(v) for v in spec.get("example_values") or []]
            if existing is None:
                local_id = f"{_LOCAL_ID_PREFIX}{uuid.uuid4().hex}"
                row = TelnyxWhatsappTemplate(
                    telnyx_record_id=local_id,
                    template_id=local_id,
                    name=telnyx_name,
                    display_name=str(spec.get("display_name") or telnyx_name),
                    language=default_wa_template_language(db),
                    category=str(spec.get("category") or "UTILITY"),
                    status="LOCAL_DRAFT",
                    sales_template_key=key,
                    body_preview=_body_preview(components),
                    draft_components_json=_dumps(components),
                    example_values_json=_dumps(examples),
                    local_sync_status="draft",
                    active_for_interview=True,
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
            if str(existing.name or "").strip().lower() != telnyx_name.strip().lower():
                existing.name = telnyx_name
                if _is_local_row(existing) and not existing.last_pushed_at:
                    existing.local_sync_status = "draft"
                    existing.last_push_error = None
                changed = True
            if not existing.display_name:
                existing.display_name = str(spec.get("display_name") or telnyx_name)
                changed = True
            if not existing.category:
                existing.category = str(spec.get("category") or "UTILITY")
                changed = True
            if not existing.draft_components_json and _is_local_row(existing):
                existing.draft_components_json = _dumps(components)
                existing.body_preview = _body_preview(components)
                existing.example_values_json = _dumps(examples)
                existing.local_sync_status = "draft"
                changed = True
            elif _is_local_row(existing) and not existing.last_pushed_at:
                draft_components = _loads(existing.draft_components_json)
                catalog_hash = _content_hash(components)
                draft_hash = _content_hash(draft_components if isinstance(draft_components, list) else None)
                needs_refresh = (
                    validate_meta_variable_order(
                        draft_components if isinstance(draft_components, list) else None
                    )
                    is not None
                    or (catalog_hash and catalog_hash != draft_hash)
                )
                if needs_refresh:
                    existing.draft_components_json = _dumps(components)
                    existing.body_preview = _body_preview(components)
                    existing.example_values_json = _dumps(examples)
                    existing.local_sync_status = "draft"
                    existing.last_push_error = None
                    changed = True
            if changed:
                existing.updated_at = now
                db.add(existing)
            rows.append(existing)
        db.commit()
        return rows

    @staticmethod
    def _find_row_for_spec(db: Session, sales_key: str, telnyx_name: str) -> TelnyxWhatsappTemplate | None:
        by_key = db.execute(
            select(TelnyxWhatsappTemplate)
            .where(TelnyxWhatsappTemplate.sales_template_key == sales_key)
            .order_by(TelnyxWhatsappTemplate.updated_at.desc())
        ).scalars().first()
        if by_key is not None:
            return by_key
        name_lower = telnyx_name.strip().lower()
        return db.execute(
            select(TelnyxWhatsappTemplate)
            .where(func.lower(TelnyxWhatsappTemplate.name) == name_lower)
            .order_by(TelnyxWhatsappTemplate.updated_at.desc())
        ).scalars().first()

    @staticmethod
    def list_templates(db: Session) -> list[dict[str, Any]]:
        InterviewWhatsappTemplateService.ensure_catalog_seeded(db)
        payload: list[dict[str, Any]] = []
        for key in INTERVIEW_WA_TEMPLATE_KEYS:
            spec = interview_spec_by_key(key)
            if not spec:
                continue
            row = InterviewWhatsappTemplateService._find_row_for_spec(
                db,
                key,
                str(spec.get("telnyx_name") or ""),
            )
            if row is None:
                continue
            payload.append(interview_template_to_dict(row))
        return payload

    @staticmethod
    def get_template_detail(db: Session, template_id: int) -> dict[str, Any] | None:
        row = InterviewWhatsappTemplateService.get_template(db, template_id)
        if row is None:
            return None
        return interview_template_to_dict(row)

    @staticmethod
    def save_draft(db: Session, row: TelnyxWhatsappTemplate, payload: dict[str, Any]) -> TelnyxWhatsappTemplate:
        if "display_name" in payload:
            row.display_name = str(payload.get("display_name") or row.display_name or row.name).strip() or row.name
        if "language" in payload and str(payload.get("language") or "").strip():
            lang_code, lang_error = normalize_wa_template_language(str(payload.get("language")), db=db)
            if lang_error:
                raise InterviewWhatsappTemplateError(
                    lang_error,
                    payload={"message": lang_error, "template_name": row.name, "requires_language_fix": True},
                )
            row.language = lang_code or default_wa_template_language(db)
        if "category" in payload:
            row.category = normalize_wa_template_category(payload.get("category"), required=False)
        if "active_for_interview" in payload:
            row.active_for_interview = bool(payload["active_for_interview"])
        components = payload.get("components")
        if isinstance(components, list):
            examples = payload.get("example_values")
            example_list = [str(v) for v in examples] if isinstance(examples, list) else None
            if example_list is None:
                loaded = _loads(row.example_values_json)
                example_list = [str(v) for v in loaded] if isinstance(loaded, list) else None
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
            raise InterviewWhatsappTemplateError(str(exc), payload=exc.payload) from exc

    @staticmethod
    def push_to_telnyx(db: Session, row: TelnyxWhatsappTemplate) -> dict[str, Any]:
        try:
            return SurveyWhatsappTemplateService.push_to_telnyx(db, row)
        except SurveyWhatsappTemplateError as exc:
            raise InterviewWhatsappTemplateError(str(exc), payload=exc.payload) from exc

    @staticmethod
    def refresh_telnyx_status(db: Session, row: TelnyxWhatsappTemplate) -> dict[str, Any]:
        try:
            return SurveyWhatsappTemplateService.refresh_telnyx_status(db, row)
        except SurveyWhatsappTemplateError as exc:
            raise InterviewWhatsappTemplateError(str(exc), payload=exc.payload) from exc

    @staticmethod
    def sync_from_telnyx(db: Session) -> dict[str, Any]:
        logger.info("interview_wa_template_sync_start")
        try:
            summary = TelnyxWhatsappTemplateSyncService.sync(db)
            InterviewWhatsappTemplateService.ensure_catalog_seeded(db)
            interview_names = interview_catalog_telnyx_names()
            matched = list(
                db.execute(
                    select(TelnyxWhatsappTemplate).where(
                        TelnyxWhatsappTemplate.sales_template_key.in_(list(INTERVIEW_WA_TEMPLATE_KEYS))
                    )
                ).scalars().all()
            )
            return {
                **summary,
                "ok": True,
                "message": f"Synced {summary.get('synced', 0)} Telnyx templates; {len(matched)} interview templates in library.",
                "interview_templates": len(matched),
                "interview_names": sorted(interview_names),
            }
        except TelnyxWhatsappTemplateSyncError as exc:
            return {
                "ok": False,
                "message": str(exc),
                "provider_error": str(exc),
                "errors": [str(exc)],
            }
        except Exception as exc:
            logger.exception("interview_wa_template_sync_failed")
            return {
                "ok": False,
                "message": f"WA Interview sync failed: {exc}",
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
                raise InterviewWhatsappTemplateError(
                    f"Telnyx delete failed: {exc}",
                    payload={"message": str(exc), "provider_error": str(exc)},
                ) from exc
        db.delete(row)
        db.commit()
        InterviewWhatsappTemplateService.ensure_catalog_seeded(db)
        return {
            "ok": True,
            "message": "Template deleted from Telnyx and database. A fresh local draft was recreated if needed.",
            "template_id": template_id,
        }

    @staticmethod
    def build_preview(
        db: Session,
        row: TelnyxWhatsappTemplate,
        *,
        first_name: str = "James",
        business_name: str = "menasim",
    ) -> dict[str, Any]:
        return SurveyWhatsappTemplateService.build_preview(
            db,
            row,
            business_name=business_name,
            first_name=first_name,
        )
