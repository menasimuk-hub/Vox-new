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
    if "interview" in name and name.startswith("voxbulk_"):
        return True
    return False


def is_survey_product_row(row: TelnyxWhatsappTemplate) -> bool:
    if is_protected_template(row):
        return False
    name = _name_lower(row)
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
    def push_buttoned(db: Session, *, dry_run: bool = False) -> dict[str, Any]:
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
        pushed_buttoned: list[dict[str, Any]] = []
        skipped_buttonless: list[dict[str, Any]] = []
        failed: list[dict[str, Any]] = []

        for row in inv["survey_keepers"]:
            if is_protected_template(row):
                continue
            if not template_row_has_buttons(row):
                skipped_buttonless.append(
                    {
                        "id": row.id,
                        "name": row.name,
                        "language": row.language,
                        "product": "survey",
                    }
                )
                continue
            entry = {
                "id": row.id,
                "name": row.name,
                "language": row.language,
                "product": "survey",
            }
            if dry_run:
                pushed_buttoned.append(entry)
                continue
            try:
                SurveyWhatsappTemplateService.push_to_telnyx(db, row, force_approved_update=True)
                pushed_buttoned.append(entry)
            except SurveyWhatsappTemplateError as exc:
                failed.append({**entry, "error": str(exc)[:300]})
            except Exception as exc:  # noqa: BLE001
                failed.append({**entry, "error": str(exc)[:300]})

        for ft in inv["feedback_keepers"]:
            buttons = parse_feedback_buttons(ft.buttons_json)
            entry = {
                "id": ft.id,
                "name": ft.template_key,
                "language": ft.language,
                "product": "feedback",
            }
            if not buttons:
                skipped_buttonless.append(entry)
                continue
            if dry_run:
                pushed_buttoned.append(entry)
                continue
            try:
                push_feedback_template_to_telnyx(db, ft)
                pushed_buttoned.append(entry)
            except FeedbackTelnyxPushError as exc:
                failed.append({**entry, "error": str(exc)[:300]})
            except Exception as exc:  # noqa: BLE001
                failed.append({**entry, "error": str(exc)[:300]})

        return {
            "ok": True,
            "dry_run": dry_run,
            "pushed_buttoned": pushed_buttoned,
            "pushed_buttoned_count": len(pushed_buttoned),
            "skipped_buttonless": skipped_buttonless,
            "skipped_buttonless_count": len(skipped_buttonless),
            "failed": failed,
            "failed_count": len(failed),
            "keepers_count": len(inv["survey_keepers"]) + len(inv["feedback_keepers"]),
        }

    @staticmethod
    def run_step(db: Session, step: str, *, dry_run: bool = False) -> dict[str, Any]:
        key = str(step or "").strip().lower()
        steps = ("meta_cleanup", "local_cleanup", "push_buttoned")
        if key not in steps:
            return {"ok": False, "error": f"Unknown step. Use one of: {', '.join(steps)}"}

        if key == "meta_cleanup":
            result = WaTemplateCleanupSyncService.meta_cleanup(db, dry_run=dry_run)
        elif key == "local_cleanup":
            result = WaTemplateCleanupSyncService.local_cleanup(db, dry_run=dry_run)
        else:
            result = WaTemplateCleanupSyncService.push_buttoned(db, dry_run=dry_run)

        result["step"] = key
        result["step_index"] = steps.index(key) + 1
        result["step_total"] = len(steps)
        return result

    @staticmethod
    def run_full(db: Session, *, dry_run: bool = False) -> dict[str, Any]:
        inv = WaTemplateCleanupSyncService.build_keeper_inventory(db)
        meta = WaTemplateCleanupSyncService.meta_cleanup(db, dry_run=dry_run)
        local = WaTemplateCleanupSyncService.local_cleanup(db, dry_run=dry_run)
        push = WaTemplateCleanupSyncService.push_buttoned(db, dry_run=dry_run)

        deleted_meta = list(meta.get("deleted_meta") or []) + list(local.get("deleted_meta") or [])
        deleted_local = list(local.get("deleted_local") or [])
        report = {
            "ok": bool(meta.get("ok") and local.get("ok") and push.get("ok")),
            "dry_run": dry_run,
            "ran_at": _now_utc().isoformat(),
            "keepers_count": len(inv["survey_keepers"]) + len(inv["feedback_keepers"]),
            "survey_keepers": len(inv["survey_keepers"]),
            "feedback_keepers": len(inv["feedback_keepers"]),
            "pushed_buttoned": push.get("pushed_buttoned_count") or 0,
            "pushed_buttoned_items": push.get("pushed_buttoned") or [],
            "skipped_buttonless": push.get("skipped_buttonless_count") or 0,
            "skipped_buttonless_items": push.get("skipped_buttonless") or [],
            "deleted_local": deleted_local,
            "deleted_local_count": len(deleted_local),
            "deleted_meta": deleted_meta,
            "deleted_meta_count": len(deleted_meta),
            "skipped_protected": meta.get("skipped_protected") or inv.get("protected") or [],
            "push_failed": push.get("failed") or [],
            "warnings": list(meta.get("warnings") or []) + list(local.get("warnings") or []),
        }
        report_path = WaTemplateCleanupSyncService._write_report(report)
        report["report_path"] = report_path
        report["message"] = (
            f"{'Dry-run: ' if dry_run else ''}"
            f"keepers={report['keepers_count']}, "
            f"deleted_local={report['deleted_local_count']}, "
            f"deleted_meta={report['deleted_meta_count']}, "
            f"pushed_buttoned={report['pushed_buttoned']}, "
            f"skipped_buttonless={report['skipped_buttonless']}"
        )
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
