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
    SYNC_BRANCH_APPROVED_UPDATE,
    SYNC_BRANCH_FIRST_PUSH,
    SYNC_BRANCH_REJECTED_RECOVERY,
    SYNC_BRANCH_STATUS_REFRESH,
    SYNC_IN_SYNC,
    SurveyWhatsappTemplateError,
    SurveyWhatsappTemplateService,
    _effective_components,
    _has_remote_telnyx_id,
    _prefetch_remote_templates_for_push,
    _refresh_local_sync_status,
    normalize_wa_template_category,
    template_row_has_buttons,
)
from app.services.telnyx_whatsapp_template_sync_service import (
    TelnyxWhatsappTemplateSyncError,
    TelnyxWhatsappTemplateSyncService,
)

logger = logging.getLogger(__name__)


def _classify_push_outcome(result: dict[str, Any]) -> str:
    if result.get("linked") or result.get("skipped_push"):
        return "linked"
    if result.get("skipped"):
        return "skipped"
    mode = str(result.get("telnyx_request_mode") or "").strip().lower()
    if mode in {"patch_template", "create_or_update_template"}:
        return "content_updated"
    branch = str(result.get("sync_branch") or "").strip()
    if branch == SYNC_BRANCH_STATUS_REFRESH:
        return "status_refreshed"
    if branch in {SYNC_BRANCH_APPROVED_UPDATE, SYNC_BRANCH_FIRST_PUSH, SYNC_BRANCH_REJECTED_RECOVERY}:
        return "content_updated"
    return "content_updated"


def _normalize_batch_result(row: TelnyxWhatsappTemplate, raw: dict[str, Any]) -> dict[str, Any]:
    outcome = _classify_push_outcome(raw)
    return {
        "template_id": int(row.id),
        "template_name": str(row.name or row.id),
        "outcome": outcome,
        "sync_branch": raw.get("sync_branch"),
        "message": raw.get("message"),
        "ok": raw.get("ok", True),
        "label": str(row.name or row.id),
    }


def _normalize_batch_error(row: TelnyxWhatsappTemplate | None, label: str, error: str) -> dict[str, Any]:
    return {
        "template_id": int(row.id) if row is not None else None,
        "template_name": label,
        "outcome": "failed",
        "error": error,
        "label": label,
    }


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
    """Refresh approval status from Meta only — never overwrite local draft/body text."""
    from app.services.survey_whatsapp_template_service import _apply_remote_link_only

    status = str(live.get("status") or "UNKNOWN").strip().upper()
    row.status = status
    row.rejection_reason = str(live.get("rejection_reason") or "").strip() or None
    remote_category = normalize_wa_template_category(live.get("category"), required=False)
    if remote_category:
        row.category = remote_category
    if status == "APPROVED":
        row.last_push_error = None
    if not _has_remote_telnyx_id(row):
        _apply_remote_link_only(db, row, live)
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
    def _collect_all_industry_templates(
        db: Session,
        industry_id: str,
    ) -> tuple[list[TelnyxWhatsappTemplate], list[dict[str, Any]]]:
        from app.services.industry_service import _template_ids_for_industry

        work: list[TelnyxWhatsappTemplate] = []
        skipped: list[dict[str, Any]] = []
        seen: set[int] = set()

        for tid in sorted(_template_ids_for_industry(db, industry_id)):
            row = db.get(TelnyxWhatsappTemplate, int(tid))
            if row is None or int(row.id) in seen:
                continue
            seen.add(int(row.id))
            if not _effective_components(row):
                skipped.append(
                    {
                        "template_id": int(row.id),
                        "template_name": str(row.name or row.id),
                        "outcome": "skipped",
                        "reason": "no_components",
                        "message": "No template components — skipped",
                    }
                )
                continue
            work.append(row)
        work.sort(key=lambda item: str(item.name or item.id))
        return work, skipped

    @staticmethod
    def push_changed_batch(
        db: Session,
        *,
        industry_id: str | None = None,
        offset: int = 0,
        limit: int | None = 10,
        force_push: bool = False,
        force_utility_category: bool = False,
    ) -> dict[str, Any]:
        from app.services.wa_template_push_batch_service import run_batched_push

        pre_skipped: list[dict[str, Any]] = []
        prefetched: list[dict[str, Any]] | None = None

        if force_push and industry_id:
            work, pre_skipped = WaTemplateSyncService._collect_all_industry_templates(db, industry_id)
            prefetched = _prefetch_remote_templates_for_push(db)
        elif force_push:
            work = [
                row
                for row in db.execute(select(TelnyxWhatsappTemplate)).scalars().all()
                if _effective_components(row)
            ]
            work.sort(key=lambda item: str(item.name or item.id))
            prefetched = _prefetch_remote_templates_for_push(db)
        else:
            work = WaTemplateSyncService._collect_push_work(db, industry_id=industry_id)

        def push_one(row: TelnyxWhatsappTemplate) -> dict[str, Any]:
            if force_utility_category:
                SurveyWhatsappTemplateService.ensure_utility_category_for_sync_push(db, row)
            if force_push:
                return SurveyWhatsappTemplateService.push_to_telnyx(
                    db,
                    row,
                    force_approved_update=True,
                    remote_items=prefetched,
                )
            return SurveyWhatsappTemplateService.push_to_telnyx(db, row)

        batch = run_batched_push(
            work,
            offset=offset,
            limit=limit,
            push_one=push_one,
            item_label=lambda row: str(row.name or row.id),
        )

        normalized_results: list[dict[str, Any]] = list(pre_skipped) if offset == 0 else []
        refreshed = 0
        content_updated = 0
        linked = 0
        skipped_count = len(pre_skipped) if offset == 0 else 0

        row_by_label = {str(row.name or row.id): row for row in work}
        for raw in batch.get("results") or []:
            label = str(raw.get("label") or raw.get("template_name") or "")
            row = row_by_label.get(label)
            if row is None:
                for candidate in work:
                    if str(candidate.name or candidate.id) == label:
                        row = candidate
                        break
            if row is None:
                continue
            normalized = _normalize_batch_result(row, raw)
            normalized_results.append(normalized)
            outcome = normalized["outcome"]
            if outcome == "status_refreshed":
                refreshed += 1
            elif outcome == "content_updated":
                content_updated += 1
            elif outcome == "linked":
                linked += 1
            elif outcome == "skipped":
                skipped_count += 1

        normalized_errors: list[dict[str, Any]] = []
        for err in batch.get("errors") or []:
            label = str(err.get("label") or "")
            row = row_by_label.get(label)
            normalized_errors.append(
                _normalize_batch_error(row, label, str(err.get("error") or "Push failed"))
            )

        total_with_skipped = len(work) + len(pre_skipped)
        return {
            "ok": batch.get("ok", True),
            "pushed": content_updated,
            "content_updated": content_updated,
            "refreshed": refreshed,
            "linked": linked,
            "skipped": skipped_count + int(batch.get("skipped") or 0),
            "error_count": batch.get("error_count", 0),
            "errors": normalized_errors,
            "results": normalized_results,
            "offset": batch.get("offset", offset),
            "next_offset": batch.get("next_offset", offset),
            "has_more": bool(batch.get("has_more")),
            "total": total_with_skipped,
            "needs_push_total": len(work),
            "force_push": force_push,
            "force_utility_category": force_utility_category,
            "processed": batch.get("next_offset", offset),
            "message": batch.get("message")
            or (
                f"Updated {content_updated} of {len(work)} template(s) on Meta"
                if force_push
                else f"Pushed {batch.get('pushed', 0)} of {len(work)} changed template(s) to Meta"
            ),
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
        force_push: bool = True,
        force_utility_category: bool = True,
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
                db,
                industry_id=industry_id,
                offset=offset,
                limit=limit,
                force_push=force_push,
                force_utility_category=force_utility_category,
            )

        push = WaTemplateSyncService.push_changed_batch(
            db,
            industry_id=industry_id,
            offset=offset,
            limit=limit,
            force_push=force_push,
            force_utility_category=force_utility_category,
        )
        return push

    @staticmethod
    def _merge_industry_sync_response(
        pull: dict[str, Any] | None,
        push: dict[str, Any],
        *,
        offset: int,
    ) -> dict[str, Any]:
        return {
            "ok": (pull.get("ok", True) if pull else True) and push.get("ok", True),
            "pull": pull,
            "push": push,
            "pushed": push.get("pushed", 0),
            "content_updated": push.get("content_updated", push.get("pushed", 0)),
            "refreshed": push.get("refreshed", 0),
            "linked": push.get("linked", 0),
            "skipped": push.get("skipped", 0),
            "error_count": push.get("error_count", 0),
            "errors": push.get("errors") or [],
            "results": push.get("results") or [],
            "total": push.get("total", 0),
            "processed": push.get("processed", push.get("next_offset", offset)),
            "has_more": bool(push.get("has_more")),
            "next_offset": push.get("next_offset", offset),
            "force_push": push.get("force_push", False),
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
