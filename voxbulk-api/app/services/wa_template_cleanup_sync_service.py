"""Survey + Customer Feedback WA template cleanup and selective Meta sync.

Never touches AI Interview or Sales templates.
Writes a JSON deletion-proof report under seed-data/wa-survey/migration-reports/.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.customer_feedback import FeedbackIndustry, FeedbackSurveyType, FeedbackWaTemplate
from app.models.survey_type import SurveyType
from app.models.survey_type_template import SurveyTypeTemplate
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate

logger = logging.getLogger(__name__)

REPORT_DIR = Path(__file__).resolve().parents[2] / "seed-data" / "wa-survey" / "migration-reports"

SURVEY_META_PREFIXES = ("voxbulk_survey_",)
CF_META_PREFIXES = ("voxbulk_cf_",)
PROTECTED_PREFIXES = (
    "voxbulk_interview_",
    "interview_",
    "voxbulk_sales_",
)
PROTECTED_SALES_KEYS = frozenset(
    {
        "sales_opt_in",
        "sales_offer",
        "sales_offer_followup",
        "sales_offer_keyword_confirm",
    }
)
INTERVIEW_KEY_PREFIXES = ("interview_",)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _name_lower(row: TelnyxWhatsappTemplate | None) -> str:
    return str(getattr(row, "name", None) or "").strip().lower()


def _key_lower(row: TelnyxWhatsappTemplate | None) -> str:
    return str(getattr(row, "sales_template_key", None) or "").strip().lower()


def is_protected_template(row: TelnyxWhatsappTemplate) -> bool:
    """Interview or sales — never delete or auto-push in this job."""
    key = _key_lower(row)
    name = _name_lower(row)
    if key in PROTECTED_SALES_KEYS or key.startswith("sales_"):
        return True
    if any(key.startswith(p) for p in INTERVIEW_KEY_PREFIXES):
        return True
    if any(name.startswith(p) for p in PROTECTED_PREFIXES):
        return True
    return False


def is_survey_product_row(row: TelnyxWhatsappTemplate) -> bool:
    if is_protected_template(row):
        return False
    name = _name_lower(row)
    if name.startswith("was_"):
        return True
    if name.startswith("voxbulk_survey_"):
        return True
    if row.survey_type_id:
        return True
    return False


def is_cf_catalog_row(row: TelnyxWhatsappTemplate) -> bool:
    if is_protected_template(row):
        return False
    return _name_lower(row).startswith("voxbulk_cf_")


def is_survey_or_cf_scope(row: TelnyxWhatsappTemplate) -> bool:
    return is_survey_product_row(row) or is_cf_catalog_row(row)


def _remote_name_is_survey_or_cf(name: str) -> bool:
    n = str(name or "").strip().lower()
    return n.startswith(SURVEY_META_PREFIXES) or n.startswith(CF_META_PREFIXES)


def _remote_name_is_protected(name: str) -> bool:
    n = str(name or "").strip().lower()
    return any(n.startswith(p) for p in PROTECTED_PREFIXES)


class WaTemplateCleanupSyncService:
    """Clean unused survey/CF templates and push buttoned keepers to Meta."""

    @staticmethod
    def _mapped_template_ids(db: Session) -> set[int]:
        rows = db.execute(select(SurveyTypeTemplate.template_id)).scalars().all()
        return {int(tid) for tid in rows if tid is not None}

    @staticmethod
    def _system_survey_type_ids(db: Session) -> set[str]:
        rows = list(
            db.execute(
                select(SurveyType.id).where(
                    SurveyType.system_template_kind.is_not(None),
                    SurveyType.system_template_kind != "",
                )
            ).scalars()
        )
        return {str(r) for r in rows}

    @staticmethod
    def build_keeper_inventory(db: Session) -> dict[str, Any]:
        mapped_ids = WaTemplateCleanupSyncService._mapped_template_ids(db)
        system_type_ids = WaTemplateCleanupSyncService._system_survey_type_ids(db)

        survey_keepers: list[TelnyxWhatsappTemplate] = []
        survey_unused: list[TelnyxWhatsappTemplate] = []
        cf_catalog_unused: list[TelnyxWhatsappTemplate] = []
        protected: list[dict[str, Any]] = []

        all_rows = list(db.execute(select(TelnyxWhatsappTemplate)).scalars())
        for row in all_rows:
            if is_protected_template(row):
                protected.append(
                    {
                        "id": row.id,
                        "name": row.name,
                        "sales_template_key": row.sales_template_key,
                        "reason": "protected_interview_or_sales",
                    }
                )
                continue

            if is_cf_catalog_row(row):
                # CF live rows live in feedback_wa_templates; catalog copies of non-keepers are unused.
                # Keep catalog row only if its Meta name matches an active feedback keeper name.
                cf_catalog_unused.append(row)
                continue

            in_mapping = int(row.id) in mapped_ids
            if not is_survey_product_row(row) and not in_mapping:
                continue

            st_id = str(row.survey_type_id or "").strip()
            linked = bool(st_id) or in_mapping or st_id in system_type_ids
            if linked:
                survey_keepers.append(row)
            else:
                survey_unused.append(row)

        # Feedback keepers: active + linked to a survey type that still exists.
        feedback_types = {
            str(t.id): t
            for t in db.execute(select(FeedbackSurveyType)).scalars().all()
        }
        feedback_keepers: list[FeedbackWaTemplate] = []
        feedback_unused: list[FeedbackWaTemplate] = []
        for ft in db.execute(select(FeedbackWaTemplate)).scalars().all():
            st = feedback_types.get(str(ft.survey_type_id or ""))
            if ft.is_active and st is not None:
                feedback_keepers.append(ft)
            else:
                feedback_unused.append(ft)

        keeper_meta_names: set[str] = set()
        for row in survey_keepers:
            name = str(row.name or "").strip().lower()
            if name:
                keeper_meta_names.add(name)

        from app.services.customer_feedback.feedback_telnyx_push_service import (
            english_anchor_template,
            feedback_meta_template_name,
        )

        industries = {
            str(i.id): i for i in db.execute(select(FeedbackIndustry)).scalars().all()
        }
        for ft in feedback_keepers:
            try:
                anchor = english_anchor_template(db, ft)
                st = feedback_types.get(str(ft.survey_type_id or ""))
                ind = industries.get(str(ft.industry_id or (st.industry_id if st else "")))
                meta_name = feedback_meta_template_name(
                    ft,
                    industry_slug=str(ind.slug or "") if ind else None,
                    survey_type_slug=str(st.slug or "") if st else None,
                    name_anchor_id=anchor.id,
                )
                if meta_name:
                    keeper_meta_names.add(meta_name.lower())
            except Exception as exc:  # noqa: BLE001
                logger.warning("feedback_meta_name_failed id=%s err=%s", ft.id, exc)

        # CF catalog rows whose name is a keeper meta name are keepers (synced status mirrors).
        cf_catalog_keepers: list[TelnyxWhatsappTemplate] = []
        still_unused_cf: list[TelnyxWhatsappTemplate] = []
        for row in cf_catalog_unused:
            if _name_lower(row) in keeper_meta_names:
                cf_catalog_keepers.append(row)
            else:
                still_unused_cf.append(row)

        return {
            "survey_keepers": survey_keepers,
            "survey_unused": survey_unused,
            "feedback_keepers": feedback_keepers,
            "feedback_unused": feedback_unused,
            "cf_catalog_keepers": cf_catalog_keepers,
            "cf_catalog_unused": still_unused_cf,
            "keeper_meta_names": keeper_meta_names,
            "protected": protected,
        }

    @staticmethod
    def _write_report(payload: dict[str, Any]) -> str:
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        stamp = _now_utc().strftime("%Y%m%dT%H%M%SZ")
        path = REPORT_DIR / f"cleanup-{stamp}.json"
        path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        return str(path)

    @staticmethod
    def meta_cleanup(db: Session, *, dry_run: bool = False) -> dict[str, Any]:
        from app.services.meta_whatsapp_template_service import MetaWhatsappTemplateService
        from app.services.telnyx_whatsapp_template_sync_service import TelnyxWhatsappTemplateSyncService

        inv = WaTemplateCleanupSyncService.build_keeper_inventory(db)
        keeper_names: set[str] = set(inv["keeper_meta_names"])

        try:
            remote = TelnyxWhatsappTemplateSyncService.fetch_remote_templates(db)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)[:400], "deleted_meta": [], "skipped_protected": []}

        deleted_meta: list[dict[str, Any]] = []
        skipped_protected: list[dict[str, Any]] = []
        warnings: list[str] = []

        seen_names: set[str] = set()
        for item in remote or []:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            name_l = name.lower()
            if name_l in seen_names:
                continue
            seen_names.add(name_l)

            if _remote_name_is_protected(name):
                skipped_protected.append({"name": name, "reason": "protected_interview_or_sales"})
                continue
            if not _remote_name_is_survey_or_cf(name):
                continue
            if name_l in keeper_names:
                continue

            record_id = str(item.get("id") or "").strip() or None
            entry = {
                "name": name,
                "record_id": record_id,
                "status": item.get("status"),
                "reason": "meta_orphan_not_in_keepers",
            }
            if dry_run:
                deleted_meta.append(entry)
                continue
            try:
                MetaWhatsappTemplateService.delete_message_template(db, name=name)
                deleted_meta.append(entry)
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"{name}: {exc}")

        return {
            "ok": True,
            "dry_run": dry_run,
            "deleted_meta": deleted_meta,
            "deleted_meta_count": len(deleted_meta),
            "skipped_protected": skipped_protected,
            "warnings": warnings,
            "keepers_count": len(inv["survey_keepers"]) + len(inv["feedback_keepers"]),
        }

    @staticmethod
    def local_cleanup(db: Session, *, dry_run: bool = False) -> dict[str, Any]:
        from app.services.customer_feedback.feedback_telnyx_push_service import (
            english_anchor_template,
            feedback_meta_template_name,
        )
        from app.services.meta_whatsapp_template_service import MetaWhatsappTemplateService
        from app.services.survey_whatsapp_template_service import SurveyWhatsappTemplateService

        inv = WaTemplateCleanupSyncService.build_keeper_inventory(db)
        deleted_local: list[dict[str, Any]] = []
        deleted_meta: list[dict[str, Any]] = []
        warnings: list[str] = []

        # Survey unused rows
        for row in inv["survey_unused"]:
            entry = {
                "id": row.id,
                "name": row.name,
                "language": row.language,
                "reason": "unlinked_or_inactive_survey",
                "source": "telnyx_whatsapp_templates",
            }
            if dry_run:
                deleted_local.append(entry)
                continue
            try:
                result = SurveyWhatsappTemplateService.delete_template(db, row)
                deleted_local.append(entry)
                if result.get("meta_deleted"):
                    deleted_meta.append(
                        {"name": entry["name"], "record_id": None, "reason": "deleted_with_local_survey"}
                    )
            except Exception as exc:  # noqa: BLE001
                try:
                    SurveyWhatsappTemplateService.delete_template_local(db, row)
                    deleted_local.append({**entry, "meta_skipped": True})
                    warnings.append(f"survey id={row.id}: meta delete failed, local removed ({exc})")
                except Exception as exc2:  # noqa: BLE001
                    warnings.append(f"survey id={row.id}: {exc2}")

        # CF catalog unused (telnyx table copies)
        for row in inv["cf_catalog_unused"]:
            entry = {
                "id": row.id,
                "name": row.name,
                "language": row.language,
                "reason": "cf_catalog_orphan",
                "source": "telnyx_whatsapp_templates",
            }
            if dry_run:
                deleted_local.append(entry)
                continue
            try:
                result = SurveyWhatsappTemplateService.delete_template(db, row)
                deleted_local.append(entry)
                if result.get("meta_deleted"):
                    deleted_meta.append(
                        {"name": entry["name"], "record_id": None, "reason": "deleted_with_local_cf_catalog"}
                    )
            except Exception as exc:  # noqa: BLE001
                try:
                    SurveyWhatsappTemplateService.delete_template_local(db, row)
                    deleted_local.append({**entry, "meta_skipped": True})
                    warnings.append(f"cf catalog id={row.id}: local only ({exc})")
                except Exception as exc2:  # noqa: BLE001
                    warnings.append(f"cf catalog id={row.id}: {exc2}")

        # Feedback unused rows
        industries = {
            str(i.id): i for i in db.execute(select(FeedbackIndustry)).scalars().all()
        }
        types = {
            str(t.id): t for t in db.execute(select(FeedbackSurveyType)).scalars().all()
        }
        for ft in inv["feedback_unused"]:
            entry = {
                "id": ft.id,
                "name": ft.template_key,
                "language": ft.language,
                "reason": "inactive_or_unlinked_feedback",
                "source": "feedback_wa_templates",
            }
            meta_name = None
            try:
                anchor = english_anchor_template(db, ft)
                st = types.get(str(ft.survey_type_id or ""))
                ind = industries.get(str(ft.industry_id or (st.industry_id if st else "")))
                meta_name = feedback_meta_template_name(
                    ft,
                    industry_slug=str(ind.slug or "") if ind else None,
                    survey_type_slug=str(st.slug or "") if st else None,
                    name_anchor_id=anchor.id,
                )
            except Exception:
                meta_name = None

            if dry_run:
                deleted_local.append(entry)
                continue
            if meta_name:
                try:
                    MetaWhatsappTemplateService.delete_message_template(db, name=meta_name)
                    deleted_meta.append(
                        {"name": meta_name, "record_id": None, "reason": "deleted_with_local_feedback"}
                    )
                except Exception as exc:  # noqa: BLE001
                    warnings.append(f"feedback meta {meta_name}: {exc}")
            db.delete(ft)
            deleted_local.append(entry)

        if not dry_run and deleted_local:
            db.commit()

        return {
            "ok": True,
            "dry_run": dry_run,
            "deleted_local": deleted_local,
            "deleted_local_count": len(deleted_local),
            "deleted_meta": deleted_meta,
            "deleted_meta_count": len(deleted_meta),
            "warnings": warnings,
            "keepers_count": len(inv["survey_keepers"]) + len(inv["feedback_keepers"]),
        }

    @staticmethod
    def push_buttoned(
        db: Session,
        *,
        dry_run: bool = False,
        offset: int = 0,
        limit: int = 10,
    ) -> dict[str, Any]:
        """Push buttoned keepers to Meta in small batches (avoids nginx 300s 504)."""
        from app.services.customer_feedback.feedback_telnyx_push_service import (
            FeedbackTelnyxPushError,
            parse_feedback_buttons,
            push_feedback_template_to_telnyx,
        )
        from app.services.survey_whatsapp_template_service import (
            SurveyWhatsappTemplateError,
            SurveyWhatsappTemplateService,
            template_row_has_buttons,
        )

        inv = WaTemplateCleanupSyncService.build_keeper_inventory(db)
        skipped_buttonless: list[dict[str, Any]] = []
        work: list[tuple[str, Any, dict[str, Any]]] = []

        for row in inv["survey_keepers"]:
            if is_protected_template(row):
                continue
            entry = {
                "id": row.id,
                "name": row.name,
                "language": row.language,
                "product": "survey",
            }
            if not template_row_has_buttons(row):
                skipped_buttonless.append(entry)
                continue
            work.append(("survey", row, entry))

        for ft in inv["feedback_keepers"]:
            entry = {
                "id": ft.id,
                "name": ft.template_key,
                "language": ft.language,
                "product": "feedback",
            }
            if not parse_feedback_buttons(ft.buttons_json):
                skipped_buttonless.append(entry)
                continue
            work.append(("feedback", ft, entry))

        total = len(work)
        start = max(0, int(offset or 0))
        # Cap batch size so each request stays under nginx proxy_read_timeout (300s).
        batch = max(1, min(int(limit or 10), 20))
        chunk = work[start : start + batch]

        pushed_buttoned: list[dict[str, Any]] = []
        failed: list[dict[str, Any]] = []

        for kind, obj, entry in chunk:
            if dry_run:
                pushed_buttoned.append(entry)
                continue
            try:
                if kind == "survey":
                    SurveyWhatsappTemplateService.push_to_telnyx(db, obj, force_approved_update=True)
                else:
                    push_feedback_template_to_telnyx(db, obj)
                pushed_buttoned.append(entry)
            except (SurveyWhatsappTemplateError, FeedbackTelnyxPushError) as exc:
                from app.services.wa_template_meta_sync import format_template_push_error

                failed.append({**entry, "error": format_template_push_error(exc)})
            except Exception as exc:  # noqa: BLE001
                failed.append({**entry, "error": str(exc)[:500]})

        next_offset = start + len(chunk)
        has_more = next_offset < total
        # Only return full buttonless list on first batch (avoid huge duplicate payloads).
        skipped_out = skipped_buttonless if start == 0 else []

        return {
            "ok": True,
            "dry_run": dry_run,
            "pushed_buttoned": pushed_buttoned,
            "pushed_buttoned_count": len(pushed_buttoned),
            "skipped_buttonless": skipped_out,
            "skipped_buttonless_count": len(skipped_buttonless) if start == 0 else 0,
            "skipped_buttonless_total": len(skipped_buttonless),
            "failed": failed,
            "failed_count": len(failed),
            "keepers_count": len(inv["survey_keepers"]) + len(inv["feedback_keepers"]),
            "buttoned_total": total,
            "offset": start,
            "limit": batch,
            "next_offset": next_offset,
            "has_more": has_more,
            "message": (
                f"Pushed batch {start + 1}–{next_offset} of {total} buttoned"
                + (" (more remaining)" if has_more else " (complete)")
            ),
        }

    @staticmethod
    def _count_button_split(db: Session, inv: dict[str, Any]) -> dict[str, Any]:
        from app.services.customer_feedback.feedback_telnyx_push_service import parse_feedback_buttons
        from app.services.survey_whatsapp_template_service import template_row_has_buttons

        buttoned: list[dict[str, Any]] = []
        buttonless: list[dict[str, Any]] = []
        for row in inv.get("survey_keepers") or []:
            entry = {
                "id": row.id,
                "name": row.name,
                "language": row.language,
                "product": "survey",
            }
            if template_row_has_buttons(row):
                buttoned.append(entry)
            else:
                buttonless.append(entry)
        for ft in inv.get("feedback_keepers") or []:
            entry = {
                "id": ft.id,
                "name": ft.template_key,
                "language": ft.language,
                "product": "feedback",
            }
            if parse_feedback_buttons(ft.buttons_json):
                buttoned.append(entry)
            else:
                buttonless.append(entry)
        return {"buttoned": buttoned, "buttonless": buttonless}

    @staticmethod
    def _meta_reconcile(db: Session, inv: dict[str, Any]) -> dict[str, Any]:
        """Compare live Meta survey/CF names to local keepers (local = source of truth)."""
        from app.services.telnyx_whatsapp_template_sync_service import TelnyxWhatsappTemplateSyncService

        keeper_names: set[str] = set(inv.get("keeper_meta_names") or set())
        try:
            remote = TelnyxWhatsappTemplateSyncService.fetch_remote_templates(db)
        except Exception as exc:  # noqa: BLE001
            return {
                "ok": False,
                "error": str(exc)[:400],
                "meta_orphans_remaining": [],
                "protected_on_meta": [],
                "meta_survey_cf_count": 0,
                "meta_waba_total": 0,
                "protected_on_meta_count": 0,
            }

        orphans: list[dict[str, Any]] = []
        protected: list[dict[str, Any]] = []
        meta_survey_cf = 0
        meta_waba_total = 0
        seen_orphan_names: set[str] = set()

        for item in remote or []:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            status = str(item.get("status") or "").strip().upper()
            if status in {"DELETED", "DISABLED", "PENDING_DELETION"}:
                continue
            meta_waba_total += 1
            name_l = name.lower()
            if _remote_name_is_protected(name):
                protected.append(
                    {
                        "name": name,
                        "language": item.get("language"),
                        "status": status,
                        "reason": "protected_interview_or_sales",
                    }
                )
                continue
            if not _remote_name_is_survey_or_cf(name):
                continue
            meta_survey_cf += 1
            if name_l not in keeper_names and name_l not in seen_orphan_names:
                seen_orphan_names.add(name_l)
                orphans.append(
                    {
                        "name": name,
                        "language": item.get("language"),
                        "status": status,
                        "reason": "on_meta_not_in_local_keepers",
                    }
                )

        return {
            "ok": True,
            "meta_orphans_remaining": orphans,
            "protected_on_meta": protected,
            "meta_survey_cf_count": meta_survey_cf,
            "meta_waba_total": meta_waba_total,
            "protected_on_meta_count": len(protected),
        }

    @staticmethod
    def finalize(
        db: Session,
        *,
        dry_run: bool = False,
        meta: dict[str, Any] | None = None,
        local: dict[str, Any] | None = None,
        push: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build UI tables + proof JSON. Local keepers are source of truth."""
        meta = meta if isinstance(meta, dict) else {}
        local = local if isinstance(local, dict) else {}
        push = push if isinstance(push, dict) else {}

        inv = WaTemplateCleanupSyncService.build_keeper_inventory(db)
        split = WaTemplateCleanupSyncService._count_button_split(db, inv)
        reconcile = WaTemplateCleanupSyncService._meta_reconcile(db, inv)

        deleted_meta = list(meta.get("deleted_meta") or []) + list(local.get("deleted_meta") or [])
        deleted_local = list(local.get("deleted_local") or [])
        pushed = list(push.get("pushed_buttoned") or [])
        skipped_buttonless = list(push.get("skipped_buttonless") or split["buttonless"])
        push_failed = list(push.get("failed") or [])
        warnings = list(meta.get("warnings") or []) + list(local.get("warnings") or [])

        keepers_count = len(inv["survey_keepers"]) + len(inv["feedback_keepers"])
        buttonless_count = len(split["buttonless"])
        buttoned_count = len(split["buttoned"])
        local_total = keepers_count
        meta_survey_cf = int(reconcile.get("meta_survey_cf_count") or 0)
        # Local should be >= Meta survey/CF when buttonless stay local-only.
        local_ge_meta = local_total >= meta_survey_cf

        summary_rows = [
            {"metric": "Local keepers (source of truth)", "count": keepers_count},
            {"metric": "Survey keepers", "count": len(inv["survey_keepers"])},
            {"metric": "Feedback keepers", "count": len(inv["feedback_keepers"])},
            {"metric": "Buttonless local (not on Meta)", "count": buttonless_count},
            {"metric": "Buttoned (should be on Meta)", "count": buttoned_count},
            {"metric": "Pushed / submitted to Meta", "count": len(pushed)},
            {"metric": "Deleted from local", "count": len(deleted_local)},
            {"metric": "Deleted from Meta", "count": len(deleted_meta)},
            {
                "metric": "Still on Meta, not in local (orphans)",
                "count": len(reconcile.get("meta_orphans_remaining") or []),
            },
            {
                "metric": "Protected on Meta (interview/sales)",
                "count": int(reconcile.get("protected_on_meta_count") or 0),
            },
            {"metric": "Meta survey+CF language rows", "count": meta_survey_cf},
            {"metric": "Meta WABA total (all products)", "count": int(reconcile.get("meta_waba_total") or 0)},
            {"metric": "Push failures", "count": len(push_failed)},
        ]

        report = {
            "ok": True,
            "dry_run": dry_run,
            "ran_at": _now_utc().isoformat(),
            "local_is_source_of_truth": True,
            "keepers_count": keepers_count,
            "survey_keepers": len(inv["survey_keepers"]),
            "feedback_keepers": len(inv["feedback_keepers"]),
            "buttonless_count": buttonless_count,
            "buttoned_count": buttoned_count,
            "local_total": local_total,
            "meta_survey_cf_count": meta_survey_cf,
            "meta_waba_total": int(reconcile.get("meta_waba_total") or 0),
            "local_ge_meta_survey_cf": local_ge_meta,
            "pushed_buttoned": len(pushed),
            "pushed_buttoned_items": pushed,
            "skipped_buttonless": buttonless_count,
            "skipped_buttonless_items": skipped_buttonless,
            "deleted_local": deleted_local,
            "deleted_local_count": len(deleted_local),
            "deleted_meta": deleted_meta,
            "deleted_meta_count": len(deleted_meta),
            "meta_orphans_remaining": reconcile.get("meta_orphans_remaining") or [],
            "protected_on_meta": reconcile.get("protected_on_meta") or [],
            "protected_on_meta_count": int(reconcile.get("protected_on_meta_count") or 0),
            "push_failed": push_failed,
            "warnings": warnings,
            "summary_rows": summary_rows,
            "tables": {
                "deleted_local": deleted_local,
                "deleted_meta": deleted_meta,
                "pushed": pushed,
                "skipped_buttonless": skipped_buttonless,
                "meta_orphans_remaining": reconcile.get("meta_orphans_remaining") or [],
                "push_failed": push_failed,
                "warnings": [{"message": w} for w in warnings],
            },
        }
        report_path = WaTemplateCleanupSyncService._write_report(report)
        report["report_path"] = report_path
        report["message"] = (
            f"{'Dry-run: ' if dry_run else ''}"
            f"local_keepers={keepers_count} (source of truth), "
            f"buttonless={buttonless_count}, "
            f"deleted_local={len(deleted_local)}, "
            f"deleted_meta={len(deleted_meta)}, "
            f"pushed={len(pushed)}, "
            f"meta_orphans={len(reconcile.get('meta_orphans_remaining') or [])}, "
            f"meta_waba={reconcile.get('meta_waba_total') or 0}"
        )
        report["step"] = "finalize"
        report["step_index"] = 4
        report["step_total"] = 4
        return report

    @staticmethod
    def run_step(
        db: Session,
        step: str,
        *,
        dry_run: bool = False,
        meta: dict[str, Any] | None = None,
        local: dict[str, Any] | None = None,
        push: dict[str, Any] | None = None,
        offset: int = 0,
        limit: int = 10,
    ) -> dict[str, Any]:
        key = str(step or "").strip().lower()
        steps = ("meta_cleanup", "local_cleanup", "push_buttoned", "finalize")
        if key not in steps:
            return {"ok": False, "error": f"Unknown step. Use one of: {', '.join(steps)}"}

        if key == "meta_cleanup":
            result = WaTemplateCleanupSyncService.meta_cleanup(db, dry_run=dry_run)
        elif key == "local_cleanup":
            result = WaTemplateCleanupSyncService.local_cleanup(db, dry_run=dry_run)
        elif key == "push_buttoned":
            result = WaTemplateCleanupSyncService.push_buttoned(
                db, dry_run=dry_run, offset=offset, limit=limit
            )
        else:
            result = WaTemplateCleanupSyncService.finalize(
                db, dry_run=dry_run, meta=meta, local=local, push=push
            )

        result["step"] = key
        result["step_index"] = steps.index(key) + 1
        result["step_total"] = len(steps)
        return result

    @staticmethod
    def run_full(db: Session, *, dry_run: bool = False) -> dict[str, Any]:
        meta = WaTemplateCleanupSyncService.meta_cleanup(db, dry_run=dry_run)
        local = WaTemplateCleanupSyncService.local_cleanup(db, dry_run=dry_run)
        # Batch push for run_full as well (CLI / single-shot callers).
        push_acc: dict[str, Any] = {
            "ok": True,
            "dry_run": dry_run,
            "pushed_buttoned": [],
            "failed": [],
            "skipped_buttonless": [],
            "skipped_buttonless_total": 0,
            "keepers_count": 0,
            "buttoned_total": 0,
        }
        offset = 0
        while True:
            batch = WaTemplateCleanupSyncService.push_buttoned(
                db, dry_run=dry_run, offset=offset, limit=10
            )
            push_acc["pushed_buttoned"].extend(batch.get("pushed_buttoned") or [])
            push_acc["failed"].extend(batch.get("failed") or [])
            if offset == 0:
                push_acc["skipped_buttonless"] = list(batch.get("skipped_buttonless") or [])
                push_acc["skipped_buttonless_total"] = int(batch.get("skipped_buttonless_total") or 0)
                push_acc["keepers_count"] = int(batch.get("keepers_count") or 0)
                push_acc["buttoned_total"] = int(batch.get("buttoned_total") or 0)
            if not batch.get("has_more"):
                break
            offset = int(batch.get("next_offset") or (offset + 10))
        push_acc["pushed_buttoned_count"] = len(push_acc["pushed_buttoned"])
        push_acc["failed_count"] = len(push_acc["failed"])
        push_acc["skipped_buttonless_count"] = len(push_acc["skipped_buttonless"])
        push = push_acc
        report = WaTemplateCleanupSyncService.finalize(
            db, dry_run=dry_run, meta=meta, local=local, push=push
        )
        report["ok"] = bool(meta.get("ok") and local.get("ok") and push.get("ok") and report.get("ok"))
        return report

    @staticmethod
    def ensure_sales_templates(db: Session) -> dict[str, Any]:
        """Seed the four lead-sales templates locally if missing (no Meta push)."""
        from app.data.system_whatsapp_defaults import SYSTEM_WHATSAPP_DEFAULTS
        from app.services.sales_whatsapp_telnyx_service import (
            TELNYX_SALES_TEMPLATE_LANGUAGE,
            TELNYX_SALES_TEMPLATE_NAMES,
        )
        from app.services.telnyx_whatsapp_template_sync_service import TelnyxWhatsappTemplateSyncService

        created: list[str] = []
        existing: list[str] = []
        now = datetime.utcnow()
        sales_keys = (
            "sales_opt_in",
            "sales_offer",
            "sales_offer_followup",
            "sales_offer_keyword_confirm",
        )
        for key in sales_keys:
            row = TelnyxWhatsappTemplateSyncService.get_for_sales_key(db, key)
            if row is not None:
                existing.append(key)
                continue
            meta_name = TELNYX_SALES_TEMPLATE_NAMES.get(key) or f"voxbulk_{key}"
            defaults = SYSTEM_WHATSAPP_DEFAULTS.get(key) or {}
            body = str(defaults.get("body") or f"VoxBulk {key.replace('_', ' ')}").strip()
            display = str(defaults.get("name") or key.replace("_", " ").title())
            components = [
                {"type": "BODY", "text": body},
                {"type": "FOOTER", "text": "Reply STOP to opt out"},
            ]
            # Offer templates typically have a URL button — mark as needing Meta later.
            if key != "sales_opt_in":
                components.append(
                    {
                        "type": "BUTTONS",
                        "buttons": [
                            {
                                "type": "URL",
                                "text": "Get started",
                                "url": "https://voxbulk.com/signin?{{1}}",
                            }
                        ],
                    }
                )
            local_id = f"local-{uuid.uuid4().hex}"
            row = TelnyxWhatsappTemplate(
                telnyx_record_id=local_id,
                template_id=local_id,
                name=meta_name,
                display_name=display,
                language=TELNYX_SALES_TEMPLATE_LANGUAGE,
                category="MARKETING",
                status="LOCAL_DRAFT",
                sales_template_key=key,
                body_preview=body[:500],
                draft_components_json=json.dumps(components, ensure_ascii=False),
                local_sync_status="draft",
                active_for_survey=False,
                active_for_interview=False,
                active_for_appointment=False,
                created_at=now,
                updated_at=now,
                synced_at=now,
            )
            db.add(row)
            created.append(key)
        if created:
            db.commit()
        return {"ok": True, "created": created, "existing": existing, "total": len(sales_keys)}
