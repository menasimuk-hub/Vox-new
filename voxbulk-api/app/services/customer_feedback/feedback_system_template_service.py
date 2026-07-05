"""Customer Feedback global (shared) WhatsApp system templates."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.customer_feedback import FeedbackWaTemplate
from app.services.customer_feedback.catalog_service import FeedbackCatalogService
from app.services.customer_feedback.feedback_telnyx_push_service import (
    FeedbackTelnyxPushError,
    _apply_remote_status,
    feedback_meta_template_name,
    find_remote_feedback_template,
    normalize_feedback_language,
    push_feedback_template_to_telnyx,
)
from app.services.customer_feedback.survey_config_service import SYSTEM_TEMPLATE_KEYS

CF_SYSTEM_TEMPLATE_META: list[dict[str, str]] = [
    {"key": "thank_you", "label": "Thank you"},
    {"key": "tell_us_more", "label": "Tell us more"},
    {"key": "marketing_opt_in", "label": "Opt in"},
    {"key": "open_question", "label": "Share your feedback"},
]


class FeedbackSystemTemplateError(ValueError):
    pass


def _is_system_row(row: FeedbackWaTemplate) -> bool:
    return row.industry_id is None and row.survey_type_id is None


class FeedbackSystemTemplateService:
    @staticmethod
    def list_grouped_admin(db: Session) -> dict[str, Any]:
        rows = list(
            db.execute(
                select(FeedbackWaTemplate)
                .where(
                    FeedbackWaTemplate.industry_id.is_(None),
                    FeedbackWaTemplate.survey_type_id.is_(None),
                )
                .order_by(FeedbackWaTemplate.template_key, FeedbackWaTemplate.language)
            ).scalars().all()
        )
        grouped: dict[str, list[dict[str, Any]]] = {meta["key"]: [] for meta in CF_SYSTEM_TEMPLATE_META}
        for row in rows:
            key = str(row.template_key or "").strip()
            if key in grouped:
                grouped[key].append(FeedbackCatalogService.template_to_dict(row))
        return {
            "ok": True,
            "kinds": [
                {
                    "key": meta["key"],
                    "label": meta["label"],
                    "templates": grouped[meta["key"]],
                    "count": len(grouped[meta["key"]]),
                }
                for meta in CF_SYSTEM_TEMPLATE_META
            ],
            "system_template_keys": sorted(SYSTEM_TEMPLATE_KEYS),
        }

    @staticmethod
    def pull_from_meta(db: Session) -> dict[str, Any]:
        from app.services.telnyx_whatsapp_template_sync_service import TelnyxWhatsappTemplateSyncService

        rows = list(
            db.execute(
                select(FeedbackWaTemplate)
                .where(
                    FeedbackWaTemplate.industry_id.is_(None),
                    FeedbackWaTemplate.survey_type_id.is_(None),
                )
                .order_by(FeedbackWaTemplate.template_key)
            ).scalars().all()
        )
        remote_items = TelnyxWhatsappTemplateSyncService.fetch_remote_templates(db)
        matched = 0
        updated = 0
        errors: list[dict[str, Any]] = []
        for row in rows:
            key = str(row.template_key or "").strip()
            if key not in SYSTEM_TEMPLATE_KEYS or not row.sync_from_meta:
                continue
            try:
                meta_name = feedback_meta_template_name(row)
                language = normalize_feedback_language(row.language)
                remote = find_remote_feedback_template(remote_items, name=meta_name, language=language)
                if remote is None:
                    continue
                matched += 1
                before = str(row.body_text or "")
                _apply_remote_status(db, row, remote)
                if str(row.body_text or "") != before:
                    updated += 1
            except Exception as exc:  # noqa: BLE001
                errors.append({"template_id": row.id, "template_key": key, "error": str(exc)[:200]})
        db.commit()
        return {
            "ok": len(errors) == 0,
            "matched": matched,
            "updated": updated,
            "failed": len(errors),
            "errors": errors,
            "message": f"Pulled {matched} system template(s) from Meta ({updated} body updated)",
        }

    @staticmethod
    def get_system_template(db: Session, template_id: str) -> FeedbackWaTemplate:
        row = db.get(FeedbackWaTemplate, str(template_id).strip())
        if row is None or not _is_system_row(row):
            raise FeedbackSystemTemplateError("System template not found.")
        return row

    @staticmethod
    def set_sync_from_meta(db: Session, template_id: str, *, sync_from_meta: bool) -> dict[str, Any]:
        row = FeedbackSystemTemplateService.get_system_template(db, template_id)
        row.sync_from_meta = bool(sync_from_meta)
        row.updated_at = datetime.utcnow()
        db.add(row)
        db.commit()
        db.refresh(row)
        return FeedbackCatalogService.template_to_dict(row)

    @staticmethod
    def pull_one_from_meta(db: Session, template_id: str) -> dict[str, Any]:
        from app.services.telnyx_whatsapp_template_sync_service import TelnyxWhatsappTemplateSyncService

        row = FeedbackSystemTemplateService.get_system_template(db, template_id)
        if not row.sync_from_meta:
            raise FeedbackSystemTemplateError("Enable “Sync from Meta” on this template first.")
        remote_items = TelnyxWhatsappTemplateSyncService.fetch_remote_templates(db)
        meta_name = feedback_meta_template_name(row)
        language = normalize_feedback_language(row.language)
        remote = find_remote_feedback_template(remote_items, name=meta_name, language=language)
        if remote is None:
            raise FeedbackSystemTemplateError("No matching Meta template found for this row.")
        before = str(row.body_text or "")
        _apply_remote_status(db, row, remote)
        updated = str(row.body_text or "") != before
        db.commit()
        return {
            "ok": True,
            "updated": updated,
            "item": FeedbackCatalogService.template_to_dict(row),
            "message": "Pulled from Meta" if updated else "Already in sync with Meta",
        }

    @staticmethod
    def push_all(db: Session) -> dict[str, Any]:
        rows = list(
            db.execute(
                select(FeedbackWaTemplate)
                .where(
                    FeedbackWaTemplate.industry_id.is_(None),
                    FeedbackWaTemplate.survey_type_id.is_(None),
                    FeedbackWaTemplate.is_active.is_(True),
                )
                .order_by(FeedbackWaTemplate.template_key)
            ).scalars().all()
        )
        pushed = 0
        linked = 0
        failed = 0
        errors: list[dict[str, Any]] = []
        for row in rows:
            key = str(row.template_key or "").strip()
            if key not in SYSTEM_TEMPLATE_KEYS:
                continue
            try:
                result = push_feedback_template_to_telnyx(db, row)
                if result.get("linked"):
                    linked += 1
                else:
                    pushed += 1
            except FeedbackTelnyxPushError as exc:
                failed += 1
                errors.append({"template_id": row.id, "template_key": key, "error": str(exc)})
        return {
            "ok": failed == 0,
            "message": f"Pushed {pushed} template(s) to Meta"
            + (f", {linked} linked" if linked else "")
            + (f", {failed} failed" if failed else ""),
            "pushed": pushed,
            "linked": linked,
            "failed": failed,
            "errors": errors,
        }

    @staticmethod
    def push_one(db: Session, template_id: str) -> dict[str, Any]:
        row = FeedbackSystemTemplateService.get_system_template(db, template_id)
        try:
            return push_feedback_template_to_telnyx(db, row)
        except FeedbackTelnyxPushError as exc:
            raise FeedbackSystemTemplateError(str(exc)) from exc
