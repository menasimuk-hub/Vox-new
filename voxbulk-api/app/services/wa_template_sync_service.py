"""Hub v2 — Meta template sync: pull status/category from Meta, push DB draft (same name)."""

from __future__ import annotations

import json
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


def _apply_live_meta_to_row(
    db: Session,
    row: TelnyxWhatsappTemplate,
    live: dict[str, Any],
    *,
    mirror_remote_body: bool = False,
) -> None:
    """Refresh approval status from Meta; optionally import body for system templates when Meta sync is on."""
    from app.services.survey_whatsapp_template_service import _apply_remote_link_only, _sync_content_hash

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
    remote_components = live.get("components")
    if isinstance(remote_components, str):
        try:
            remote_components = json.loads(remote_components)
        except json.JSONDecodeError:
            remote_components = None
    if mirror_remote_body and isinstance(remote_components, list):
        row.components_json = json.dumps(remote_components)
        from app.services.wa_system_template_routing_service import WaSystemTemplateRoutingService

        row.remote_content_hash = _sync_content_hash(remote_components)
        WaSystemTemplateRoutingService.apply_survey_remote_content_to_row(db, row, remote_components)
    row.local_sync_status = _refresh_local_sync_status(row)


class WaTemplateSyncService:
    @staticmethod
    def pull_catalog(db: Session, *, remote: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        """Disabled — local DB is source of truth (see docs/wa-template-sync-contract.md)."""
        _ = (db, remote)
        return {
            "ok": True,
            "synced": 0,
            "approved": 0,
            "removed": 0,
            "remote_count": 0,
            "catalog_import_disabled": True,
            "message": "Catalog import disabled — use status-only pull (DB is source of truth).",
        }

    @staticmethod
    def pull_from_meta(
        db: Session,
        *,
        status_only: bool = True,
        connection_profile_id: str | None = None,
        service_code: str | None = "survey",
    ) -> dict[str, Any]:
        """Fetch Meta once and refresh approval fields only — never import names/bodies (DB is master)."""
        try:
            remote = TelnyxWhatsappTemplateSyncService.fetch_remote_templates(
                db,
                connection_profile_id=connection_profile_id,
                service_code=service_code,
            )
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)[:400]}
        from app.services.wa_template_product_scope import filter_remote_for_service_code

        remote = filter_remote_for_service_code(remote, service_code)
        status = WaTemplateSyncService.pull_statuses(
            db,
            remote=remote,
            mirror_remote_body=False,
            connection_profile_id=connection_profile_id,
            service_code=service_code,
        )
        ok = bool(status.get("ok", True))
        catalog_note = None
        if not status_only:
            catalog_note = WaTemplateSyncService.pull_catalog(db, remote=remote)
        return {
            "ok": ok,
            "status_only": True,
            "catalog_import_disabled": True,
            "catalog": catalog_note,
            "status_pull": status,
            "remote_count": len(remote),
            "message": status.get("message") or f"Refreshed status for {status.get('updated', 0)} template(s)",
        }

    @staticmethod
    def pull_statuses(
        db: Session,
        *,
        row_ids: list[int] | None = None,
        remote: list[dict[str, Any]] | None = None,
        mirror_remote_body: bool = False,
        connection_profile_id: str | None = None,
        service_code: str | None = "survey",
    ) -> dict[str, Any]:
        """Refresh status + category from live Meta for local rows (no draft overwrite)."""
        try:
            items = (
                remote
                if remote is not None
                else TelnyxWhatsappTemplateSyncService.fetch_remote_templates(
                    db,
                    connection_profile_id=connection_profile_id,
                    service_code=service_code,
                )
            )
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)[:400]}

        from app.services.connection.constants import SERVICE_CUSTOMER_FEEDBACK, normalize_service_code
        from app.services.wa_template_product_scope import filter_remote_for_service_code, is_survey_platform_row

        code = normalize_service_code(service_code) or "survey"
        items = filter_remote_for_service_code(items, code)
        by_record, by_name_lang = TelnyxWhatsappTemplateSyncService._live_index(items)
        if row_ids:
            rows = [db.get(TelnyxWhatsappTemplate, int(rid)) for rid in row_ids]
            rows = [r for r in rows if r is not None]
        else:
            rows = list(db.execute(select(TelnyxWhatsappTemplate)).scalars().all())
            if code != SERVICE_CUSTOMER_FEEDBACK:
                rows = [row for row in rows if is_survey_platform_row(db, row)]

        from app.services.wa_template_profile_status_service import WaTemplateProfileStatusService
        from app.services.wa_template_profile_push_service import WaTemplateProfilePushService

        is_primary = WaTemplateProfilePushService.is_primary_profile(
            db, connection_profile_id, service_code=code
        )

        updated = 0
        synced_rows: list[TelnyxWhatsappTemplate] = []
        for row in rows:
            live = None
            entry = (
                WaTemplateProfilePushService.get_ledger_entry(db, int(row.id), connection_profile_id)
                if connection_profile_id
                else None
            )
            if entry is not None and WaTemplateProfilePushService._ledger_has_remote(entry):
                rid = str(entry.remote_record_id or "").strip()
                if rid and rid in by_record:
                    live = by_record[rid]
            if live is None:
                live = TelnyxWhatsappTemplateSyncService._match_live_item(
                    row, by_record=by_record, by_name_lang=by_name_lang
                )
            if live is None:
                continue
            if is_primary or not connection_profile_id:
                _apply_live_meta_to_row(db, row, live, mirror_remote_body=mirror_remote_body)
                synced_rows.append(row)
            else:
                WaTemplateProfileStatusService.record_from_live_item(
                    db,
                    int(row.id),
                    live,
                    connection_profile_id=connection_profile_id,
                    commit=False,
                )
            updated += 1
        if synced_rows:
            WaTemplateProfileStatusService.record_many(
                db, synced_rows, connection_profile_id=connection_profile_id, commit=False
            )
        db.commit()
        return {
            "ok": True,
            "updated": updated,
            "message": f"Refreshed status/category for {updated} template(s) from live WhatsApp provider",
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
        from app.services.wa_template_product_scope import is_survey_platform_row

        for row in rows:
            if int(row.id) in seen:
                continue
            if not is_survey_platform_row(db, row):
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
        connection_profile_id: str | None = None,
        service_code: str | None = "survey",
    ) -> dict[str, Any]:
        from app.services.wa_template_push_batch_service import run_batched_push

        pre_skipped: list[dict[str, Any]] = []
        prefetched: list[dict[str, Any]] | None = None

        if force_push and industry_id:
            work, pre_skipped = WaTemplateSyncService._collect_all_industry_templates(db, industry_id)
            prefetched = _prefetch_remote_templates_for_push(
                db, connection_profile_id=connection_profile_id, service_code=service_code
            )
        elif force_push:
            from app.services.wa_template_product_scope import is_survey_platform_row

            work = [
                row
                for row in db.execute(select(TelnyxWhatsappTemplate)).scalars().all()
                if _effective_components(row) and is_survey_platform_row(db, row)
            ]
            work.sort(key=lambda item: str(item.name or item.id))
            prefetched = _prefetch_remote_templates_for_push(
                db, connection_profile_id=connection_profile_id, service_code=service_code
            )
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
                    connection_profile_id=connection_profile_id,
                    service_code=service_code,
                )
            return SurveyWhatsappTemplateService.push_to_telnyx(
                db,
                row,
                connection_profile_id=connection_profile_id,
                service_code=service_code,
            )

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
        force_push: bool = False,
        force_utility_category: bool = False,
        connection_profile_id: str | None = None,
        service_code: str | None = "survey",
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
            return WaTemplateSyncService.pull_statuses(
                db,
                row_ids=row_ids or None,
                connection_profile_id=connection_profile_id,
                service_code=service_code,
            )

        if phase == "push":
            return WaTemplateSyncService.push_changed_batch(
                db,
                industry_id=industry_id,
                offset=offset,
                limit=limit,
                force_push=force_push,
                force_utility_category=force_utility_category,
                connection_profile_id=connection_profile_id,
                service_code=service_code,
            )

        push = WaTemplateSyncService.push_changed_batch(
            db,
            industry_id=industry_id,
            offset=offset,
            limit=limit,
            force_push=force_push,
            force_utility_category=force_utility_category,
            connection_profile_id=connection_profile_id,
            service_code=service_code,
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
            return WaTemplateSyncService.pull_from_meta(db, status_only=True)
        if phase == "push":
            return WaTemplateSyncService.push_changed_batch(db, offset=offset, limit=limit)
        pull = WaTemplateSyncService.pull_from_meta(db, status_only=True)
        push = WaTemplateSyncService.push_changed_batch(db, offset=offset, limit=limit)
        status = pull.get("status_pull") or {}
        return {
            "ok": all(x.get("ok", True) for x in (status, push)),
            "status_pull": status,
            "push": push,
            "has_more": bool(push.get("has_more")),
            "next_offset": push.get("next_offset", offset),
            "message": (
                f"Pull: refreshed status for {status.get('updated', 0)} row(s). "
                f"Push: {push.get('pushed', 0)} changed template(s)."
            ),
        }

    @staticmethod
    def collect_survey_mirror_templates(db: Session) -> list[TelnyxWhatsappTemplate]:
        from app.services.wa_template_product_scope import is_survey_platform_row

        rows = list(db.execute(select(TelnyxWhatsappTemplate)).scalars().all())
        work = [row for row in rows if _effective_components(row) and is_survey_platform_row(db, row)]
        work.sort(key=lambda item: str(item.name or item.id))
        return work

    @staticmethod
    def _live_was_name_lang_keys(
        db: Session,
        connection_profile_id: str,
        *,
        service_code: str = "survey",
    ) -> set[tuple[str, str]]:
        from seed_data.wa_survey_template_naming import is_was_survey_name

        remote = TelnyxWhatsappTemplateSyncService.fetch_remote_templates(
            db,
            connection_profile_id=connection_profile_id,
            service_code=service_code,
            allow_account_waba_fallback=False,
        )
        keys: set[tuple[str, str]] = set()
        for item in remote:
            name = str(item.get("name") or "").strip().lower()
            if not is_was_survey_name(name):
                continue
            lang = str(item.get("language") or item.get("language_code") or "en_GB").strip().lower()
            keys.add((name, lang))
        return keys

    @staticmethod
    def collect_survey_mirror_gap_templates(
        db: Session,
        *,
        primary_profile_id: str | None = None,
        backup_profile_id: str | None = None,
        service_code: str | None = "survey",
    ) -> list[tuple[TelnyxWhatsappTemplate, str]]:
        """Local survey rows for Meta live was_* names missing on backup (row, meta_live_name)."""
        from app.services.wa_template_profile_push_service import WaTemplateProfilePushService

        code = service_code or "survey"
        primary_id = str(primary_profile_id or "").strip() or WaTemplateProfilePushService.resolve_primary_connection_profile_id(
            db, service_code=code
        )
        backup_id = str(backup_profile_id or "").strip() or WaTemplateProfilePushService.resolve_backup_connection_profile_id(
            db, service_code=code
        )
        if not primary_id or not backup_id:
            return []

        meta_keys = WaTemplateSyncService._live_was_name_lang_keys(db, primary_id, service_code=code)
        backup_keys = WaTemplateSyncService._live_was_name_lang_keys(db, backup_id, service_code=code)
        missing = meta_keys - backup_keys
        if not missing:
            return []

        rows = WaTemplateSyncService.collect_survey_mirror_templates(db)
        work: list[tuple[TelnyxWhatsappTemplate, str]] = []
        for name, lang in sorted(missing):
            row = WaTemplateSyncService._find_local_row_for_meta_live_name(rows, name, lang)
            if row is not None and _effective_components(row):
                work.append((row, name))
        return work

    @staticmethod
    def _find_local_row_for_meta_live_name(
        rows: list[TelnyxWhatsappTemplate],
        meta_name: str,
        lang: str,
    ) -> TelnyxWhatsappTemplate | None:
        """Match a Meta live template name to a local row (exact or renamed suffix clone)."""
        target_name = str(meta_name or "").strip().lower()
        target_lang = str(lang or "en_gb").strip().lower()
        if not target_name:
            return None

        by_key = {
            (str(row.name or "").strip().lower(), str(row.language or "en_GB").strip().lower()): row
            for row in rows
        }
        direct = by_key.get((target_name, target_lang)) or by_key.get((target_name, "en_gb"))
        if direct is not None:
            return direct

        prefix = f"{target_name}_"
        for row in rows:
            row_name = str(row.name or "").strip().lower()
            row_lang = str(row.language or "en_GB").strip().lower()
            if not row_name.startswith(prefix):
                continue
            if row_lang == target_lang or row_lang.startswith(target_lang[:2]):
                return row
        return None

    @staticmethod
    def mirror_meta_gap_to_backup(
        db: Session,
        *,
        offset: int = 0,
        limit: int | None = 10,
        connection_profile_id: str | None = None,
        service_code: str | None = "survey",
    ) -> dict[str, Any]:
        """Push survey templates that exist on Meta primary live but not on backup live."""
        from app.services.wa_template_profile_push_service import WaTemplateProfilePushService
        from app.services.wa_template_push_batch_service import run_batched_push

        backup_id = str(connection_profile_id or "").strip() or WaTemplateProfilePushService.resolve_backup_connection_profile_id(
            db, service_code=service_code or "survey"
        )
        if not backup_id:
            return {"ok": False, "error": "No backup Telnyx WhatsApp profile is configured."}

        work = WaTemplateSyncService.collect_survey_mirror_gap_templates(
            db,
            backup_profile_id=backup_id,
            service_code=service_code,
        )
        prefetched = _prefetch_remote_templates_for_push(
            db, connection_profile_id=backup_id, service_code=service_code
        )

        def push_one(item: tuple[TelnyxWhatsappTemplate, str]) -> dict[str, Any]:
            row, meta_live_name = item
            return SurveyWhatsappTemplateService.push_to_telnyx(
                db,
                row,
                force_approved_update=True,
                remote_items=prefetched,
                connection_profile_id=backup_id,
                service_code=service_code,
                template_name_override=meta_live_name,
            )

        batch = run_batched_push(
            work,
            offset=offset,
            limit=limit,
            push_one=push_one,
            item_label=lambda item: str(item[1] or item[0].name or item[0].id),
        )

        normalized_results: list[dict[str, Any]] = []
        row_by_label = {str(meta_name or row.name or row.id): row for row, meta_name in work}
        content_updated = 0
        for raw in batch.get("results") or []:
            label = str(raw.get("label") or raw.get("template_name") or "")
            row = row_by_label.get(label)
            if row is None:
                continue
            normalized_results.append(_normalize_batch_result(row, raw))
            if _classify_push_outcome(raw) == "content_updated":
                content_updated += 1

        normalized_errors: list[dict[str, Any]] = []
        for err in batch.get("errors") or []:
            label = str(err.get("label") or "")
            row = row_by_label.get(label)
            normalized_errors.append(
                _normalize_batch_error(row, label, str(err.get("error") or "Mirror gap push failed"))
            )

        return {
            "ok": batch.get("ok", True),
            "mirror_profile_id": backup_id,
            "gap_total": len(work),
            "pushed": content_updated,
            "content_updated": content_updated,
            "error_count": batch.get("error_count", 0),
            "errors": normalized_errors,
            "results": normalized_results,
            "offset": batch.get("offset", offset),
            "next_offset": batch.get("next_offset", offset),
            "has_more": bool(batch.get("has_more")),
            "message": batch.get("message")
            or f"Mirrored {content_updated} Meta-gap template(s) to backup ({len(work)} missing on backup live)",
        }

    @staticmethod
    def mirror_to_backup_profile(
        db: Session,
        *,
        offset: int = 0,
        limit: int | None = 10,
        connection_profile_id: str | None = None,
        service_code: str | None = "survey",
    ) -> dict[str, Any]:
        from app.services.wa_template_profile_push_service import WaTemplateProfilePushService

        backup_id = str(connection_profile_id or "").strip() or None
        if not backup_id:
            backup_id = WaTemplateProfilePushService.resolve_backup_connection_profile_id(
                db, service_code=service_code or "survey"
            )
        if not backup_id:
            return {"ok": False, "error": "No backup Telnyx WhatsApp profile is configured."}

        work = WaTemplateSyncService.collect_survey_mirror_templates(db)
        prefetched = _prefetch_remote_templates_for_push(
            db, connection_profile_id=backup_id, service_code=service_code
        )
        from app.services.wa_template_push_batch_service import run_batched_push

        def push_one(row: TelnyxWhatsappTemplate) -> dict[str, Any]:
            return SurveyWhatsappTemplateService.push_to_telnyx(
                db,
                row,
                force_approved_update=True,
                remote_items=prefetched,
                connection_profile_id=backup_id,
                service_code=service_code,
            )

        batch = run_batched_push(
            work,
            offset=offset,
            limit=limit,
            push_one=push_one,
            item_label=lambda row: str(row.name or row.id),
        )

        normalized_results: list[dict[str, Any]] = []
        row_by_label = {str(row.name or row.id): row for row in work}
        content_updated = 0
        for raw in batch.get("results") or []:
            label = str(raw.get("label") or raw.get("template_name") or "")
            row = row_by_label.get(label)
            if row is None:
                continue
            normalized_results.append(_normalize_batch_result(row, raw))
            if _classify_push_outcome(raw) == "content_updated":
                content_updated += 1

        normalized_errors: list[dict[str, Any]] = []
        for err in batch.get("errors") or []:
            label = str(err.get("label") or "")
            row = row_by_label.get(label)
            normalized_errors.append(
                _normalize_batch_error(row, label, str(err.get("error") or "Mirror push failed"))
            )

        return {
            "ok": batch.get("ok", True),
            "mirror_profile_id": backup_id,
            "pushed": content_updated,
            "content_updated": content_updated,
            "error_count": batch.get("error_count", 0),
            "errors": normalized_errors,
            "results": normalized_results,
            "offset": batch.get("offset", offset),
            "next_offset": batch.get("next_offset", offset),
            "has_more": bool(batch.get("has_more")),
            "total": len(work),
            "message": batch.get("message")
            or f"Mirrored {content_updated} of {len(work)} survey template(s) to backup profile",
        }

    @staticmethod
    def push_all_system_templates(
        db: Session,
        *,
        connection_profile_id: str | None = None,
        offset: int = 0,
        limit: int | None = 10,
        service_code: str | None = "survey",
    ) -> dict[str, Any]:
        from app.services.survey_system_template_service import SurveySystemTemplateService

        grouped = SurveySystemTemplateService.list_grouped_admin(db)
        work: list[TelnyxWhatsappTemplate] = []
        seen: set[int] = set()
        for kind in grouped.get("kinds") or []:
            for tpl in kind.get("templates") or []:
                tid = tpl.get("id")
                if not str(tid or "").isdigit():
                    continue
                row = db.get(TelnyxWhatsappTemplate, int(tid))
                if row is None or int(row.id) in seen:
                    continue
                if not _effective_components(row):
                    continue
                seen.add(int(row.id))
                work.append(row)
        work.sort(key=lambda item: str(item.name or item.id))

        prefetched = _prefetch_remote_templates_for_push(
            db, connection_profile_id=connection_profile_id, service_code=service_code
        )
        from app.services.wa_template_push_batch_service import run_batched_push

        def push_one(row: TelnyxWhatsappTemplate) -> dict[str, Any]:
            return SurveyWhatsappTemplateService.push_to_telnyx(
                db,
                row,
                force_approved_update=True,
                remote_items=prefetched,
                connection_profile_id=connection_profile_id,
                service_code=service_code,
            )

        batch = run_batched_push(
            work,
            offset=offset,
            limit=limit,
            push_one=push_one,
            item_label=lambda row: str(row.name or row.id),
        )
        normalized_results: list[dict[str, Any]] = []
        row_by_label = {str(row.name or row.id): row for row in work}
        content_updated = 0
        for raw in batch.get("results") or []:
            label = str(raw.get("label") or raw.get("template_name") or "")
            row = row_by_label.get(label)
            if row is None:
                continue
            normalized_results.append(_normalize_batch_result(row, raw))
            if _classify_push_outcome(raw) == "content_updated":
                content_updated += 1
        normalized_errors: list[dict[str, Any]] = []
        for err in batch.get("errors") or []:
            label = str(err.get("label") or "")
            row = row_by_label.get(label)
            normalized_errors.append(
                _normalize_batch_error(row, label, str(err.get("error") or "Push failed"))
            )
        return {
            "ok": batch.get("ok", True),
            "pushed": content_updated,
            "content_updated": content_updated,
            "error_count": batch.get("error_count", 0),
            "errors": normalized_errors,
            "results": normalized_results,
            "offset": batch.get("offset", offset),
            "next_offset": batch.get("next_offset", offset),
            "has_more": bool(batch.get("has_more")),
            "total": len(work),
            "connection_profile_id": connection_profile_id,
            "message": batch.get("message")
            or f"Pushed {content_updated} of {len(work)} system template(s)",
        }
