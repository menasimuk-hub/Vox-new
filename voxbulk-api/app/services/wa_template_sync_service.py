"""Hub v2 — Meta template sync: pull status/category from Meta, push DB draft (same name)."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.survey_type import SurveyType
from app.models.survey_type_template import SurveyTypeTemplate
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.survey_type_template_service import SurveyTypeTemplateService
from app.services.survey_whatsapp_template_service import (
    SYNC_IN_SYNC,
    SurveyWhatsappTemplateError,
    SurveyWhatsappTemplateService,
    _effective_components,
    _has_remote_telnyx_id,
    _refresh_local_sync_status,
    normalize_wa_template_category,
    template_row_has_buttons,
)
from app.services.telnyx_whatsapp_template_sync_service import (
    TelnyxWhatsappTemplateSyncError,
    TelnyxWhatsappTemplateSyncService,
)

logger = logging.getLogger(__name__)


def _row_needs_push(row: TelnyxWhatsappTemplate) -> bool:
    if not _effective_components(row):
        return False
    sync_status = _refresh_local_sync_status(row)
    if sync_status != SYNC_IN_SYNC:
        return True
    if template_row_has_buttons(row) and not _has_remote_telnyx_id(row):
        return True
    return False


def _apply_live_meta_to_row(db: Session, row: TelnyxWhatsappTemplate, live: dict[str, Any]) -> None:
    """Meta is source of truth for status, category, rejection — not draft content."""
    from app.services.survey_whatsapp_template_service import _apply_remote_telnyx_item

    status = str(live.get("status") or "UNKNOWN").strip().upper()
    row.status = status
    row.rejection_reason = str(live.get("rejection_reason") or "").strip() or None
    remote_category = normalize_wa_template_category(live.get("category"), required=False)
    if remote_category:
        row.category = remote_category
    if status == "APPROVED":
        row.last_push_error = None
    _apply_remote_telnyx_item(db, row, live, overwrite_draft=False)
    row.local_sync_status = _refresh_local_sync_status(row)


class WaTemplateSyncService:
    @staticmethod
    def pull_catalog(db: Session) -> dict[str, Any]:
        """Pull Meta catalog into local rows — status/category + remote mirror; never overwrite draft."""
        try:
            result = TelnyxWhatsappTemplateSyncService.sync(db)
        except TelnyxWhatsappTemplateSyncError as exc:
            return {"ok": False, "error": str(exc)[:400]}
        return {
            "ok": True,
            "synced": int(result.get("synced") or 0),
            "approved": int(result.get("approved") or 0),
            "removed": int(result.get("removed") or 0),
            "remote_count": int(result.get("remote_count") or 0),
            "message": f"Pulled Meta catalog ({result.get('synced') or 0} templates updated locally)",
        }

    @staticmethod
    def pull_statuses(db: Session, *, row_ids: list[int] | None = None) -> dict[str, Any]:
        """Refresh status + category from live Meta for local rows (no draft overwrite)."""
        try:
            remote = TelnyxWhatsappTemplateSyncService.fetch_remote_templates(db)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)[:400]}

        by_record, by_name_lang = TelnyxWhatsappTemplateSyncService._live_index(remote)
        if row_ids:
            rows = [db.get(TelnyxWhatsappTemplate, int(rid)) for rid in row_ids]
            rows = [r for r in rows if r is not None]
        else:
            rows = list(db.execute(select(TelnyxWhatsappTemplate)).scalars().all())

        updated = 0
        for row in rows:
            live = TelnyxWhatsappTemplateSyncService._match_live_item(
                row, by_record=by_record, by_name_lang=by_name_lang
            )
            if live is None:
                continue
            _apply_live_meta_to_row(db, row, live)
            updated += 1
        db.commit()
        return {
            "ok": True,
            "updated": updated,
            "message": f"Refreshed status/category for {updated} template(s) from Meta",
        }

    @staticmethod
    def _collect_push_work(db: Session, *, industry_id: str | None = None) -> list[TelnyxWhatsappTemplate]:
        work: list[TelnyxWhatsappTemplate] = []
        seen: set[int] = set()

        if industry_id:
            from app.services.survey_type_service import SurveyTypeService

            for item in SurveyTypeService.list_types(db, industry_id=industry_id):
                type_id = str(item.get("id") or "").strip()
                if not type_id:
                    continue
                for mapping in SurveyTypeTemplateService.list_for_survey_type(db, type_id):
                    row = db.get(TelnyxWhatsappTemplate, mapping.template_id)
                    if row is None or int(row.id) in seen:
                        continue
                    if _row_needs_push(row):
                        work.append(row)
                        seen.add(int(row.id))
            return work

        rows = list(db.execute(select(TelnyxWhatsappTemplate)).scalars().all())
        for row in rows:
            if int(row.id) in seen:
                continue
            if _row_needs_push(row):
                work.append(row)
                seen.add(int(row.id))
        return work

    @staticmethod
    def push_changed_batch(
        db: Session,
        *,
        industry_id: str | None = None,
        offset: int = 0,
        limit: int | None = 10,
    ) -> dict[str, Any]:
        from app.services.wa_template_push_batch_service import run_batched_push

        work = WaTemplateSyncService._collect_push_work(db, industry_id=industry_id)

        def push_one(row: TelnyxWhatsappTemplate) -> dict[str, Any]:
            return SurveyWhatsappTemplateService.push_to_telnyx(db, row)

        batch = run_batched_push(
            work,
            offset=offset,
            limit=limit,
            push_one=push_one,
            item_label=lambda row: str(row.name or row.id),
        )
        return {
            "ok": batch.get("ok", True),
            "pushed": batch.get("pushed", 0),
            "error_count": batch.get("error_count", 0),
            "errors": batch.get("errors") or [],
            "results": batch.get("results") or [],
            "offset": batch.get("offset", offset),
            "next_offset": batch.get("next_offset", offset),
            "has_more": bool(batch.get("has_more")),
            "total": batch.get("total", len(work)),
            "needs_push_total": len(work),
            "message": batch.get("message")
            or f"Pushed {batch.get('pushed', 0)} of {len(work)} changed template(s) to Meta",
        }

    @staticmethod
    def sync_single(db: Session, template_id: int) -> dict[str, Any]:
        row = db.get(TelnyxWhatsappTemplate, int(template_id))
        if row is None:
            raise SurveyWhatsappTemplateError("Template not found")
        pull = WaTemplateSyncService.pull_statuses(db, row_ids=[int(template_id)])
        if not _row_needs_push(row):
            db.refresh(row)
            return {
                "ok": True,
                "pulled": pull,
                "pushed": False,
                "message": "Status refreshed from Meta — draft already matches Meta.",
            }
        push = SurveyWhatsappTemplateService.push_to_telnyx(db, row)
        return {
            "ok": True,
            "pulled": pull,
            "pushed": True,
            "push": push,
            "message": push.get("message") or "Template submitted to Meta for review.",
        }

    @staticmethod
    def sync_industry(
        db: Session,
        industry_id: str,
        *,
        offset: int = 0,
        limit: int | None = 10,
        phase: str = "full",
    ) -> dict[str, Any]:
        type_ids = [
            str(r)
            for r in db.execute(select(SurveyType.id).where(SurveyType.industry_id == industry_id)).scalars().all()
        ]
        row_ids: list[int] = []
        for tid in type_ids:
            for mapping in SurveyTypeTemplateService.list_for_survey_type(db, tid):
                row_ids.append(int(mapping.template_id))

        if phase == "pull":
            return WaTemplateSyncService.pull_statuses(db, row_ids=row_ids or None)

        if phase == "push":
            return WaTemplateSyncService.push_changed_batch(
                db, industry_id=industry_id, offset=offset, limit=limit
            )

        pull: dict[str, Any] | None = None
        if phase == "full" and offset == 0:
            pull = WaTemplateSyncService.pull_statuses(db, row_ids=row_ids or None)
        push = WaTemplateSyncService.push_changed_batch(
            db, industry_id=industry_id, offset=offset, limit=limit
        )
        return {
            "ok": (pull.get("ok", True) if pull else True) and push.get("ok", True),
            "pull": pull,
            "push": push,
            "pushed": push.get("pushed", 0),
            "has_more": bool(push.get("has_more")),
            "next_offset": push.get("next_offset", offset),
            "message": push.get("message") or "Industry templates synced with Meta",
        }

    @staticmethod
    def sync_all(
        db: Session,
        *,
        offset: int = 0,
        limit: int | None = 10,
        phase: str = "full",
    ) -> dict[str, Any]:
        if phase == "pull":
            catalog = WaTemplateSyncService.pull_catalog(db)
            status = WaTemplateSyncService.pull_statuses(db)
            return {
                "ok": catalog.get("ok", True) and status.get("ok", True),
                "catalog": catalog,
                "status": status,
                "message": f"{catalog.get('message', '')} {status.get('message', '')}".strip(),
            }
        if phase == "push":
            return WaTemplateSyncService.push_changed_batch(db, offset=offset, limit=limit)
        pull_catalog = WaTemplateSyncService.pull_catalog(db)
        pull_status = WaTemplateSyncService.pull_statuses(db)
        push = WaTemplateSyncService.push_changed_batch(db, offset=offset, limit=limit)
        return {
            "ok": all(
                x.get("ok", True)
                for x in (pull_catalog, pull_status, push)
            ),
            "catalog": pull_catalog,
            "status": pull_status,
            "push": push,
            "has_more": bool(push.get("has_more")),
            "next_offset": push.get("next_offset", offset),
            "message": (
                f"Pull: {pull_catalog.get('synced', 0)} catalog row(s). "
                f"Push: {push.get('pushed', 0)} changed template(s)."
            ),
        }
