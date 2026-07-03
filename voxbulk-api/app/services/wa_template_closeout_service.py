"""WA Templates close-out: utility rewrite, push local drafts, clean orphans, interview push."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.customer_feedback import FeedbackIndustry, FeedbackSurveyType, FeedbackWaTemplate
from app.models.survey_type import SurveyType
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.wa_template_utility_content import (
    DEFAULT_EMOJI,
    build_utility_components,
    components_have_buttons,
    default_buttons_for_key,
    ensure_leading_emoji,
    extract_buttons_from_components,
    has_leading_emoji,
    is_promo_wording,
    parse_components_json,
    utility_body_for_topic,
)

logger = logging.getLogger(__name__)


def _loads(raw: str | None) -> list[dict[str, Any]]:
    return parse_components_json(raw)


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _body_from_components(components: list[dict[str, Any]]) -> str:
    for comp in components:
        if str(comp.get("type") or "").upper() == "BODY":
            return str(comp.get("text") or "").strip()
    return ""


def _is_local_row(row: TelnyxWhatsappTemplate) -> bool:
    rid = str(row.telnyx_record_id or "").strip()
    status = str(row.status or "").strip().upper()
    return (not rid) or rid.startswith("local-") or status in {"LOCAL_DRAFT", "DRAFT", ""}


class WaTemplateCloseoutService:
    @staticmethod
    def repair_survey_template_content(db: Session, row: TelnyxWhatsappTemplate) -> bool:
        """Ensure Utility category, leading emoji, and quick-reply buttons. Returns True if changed."""
        components = _loads(row.draft_components_json)
        body = _body_from_components(components) or str(row.body_preview or "").strip()
        buttons = extract_buttons_from_components(components)
        topic = None
        if row.survey_type_id:
            st = db.get(SurveyType, row.survey_type_id)
            topic = st.name if st else None
        if not topic:
            topic = str(row.display_name or row.name or "your recent visit")

        needs = False
        status = str(row.status or "").upper()
        category = str(row.category or "").upper()
        if category == "MARKETING" and "sales" not in str(row.name or "").lower() and not str(
            row.sales_template_key or ""
        ).startswith("sales_"):
            # Survey/feedback-style rows should be Utility (keep intentional sales marketing).
            if "voxbulk_survey_" in str(row.name or "").lower() or row.survey_type_id:
                row.category = "UTILITY"
                needs = True
        if status == "REJECTED" or is_promo_wording(body) or not buttons or not has_leading_emoji(body):
            needs = True

        if not needs and components_have_buttons(components) and has_leading_emoji(body):
            return False

        if status == "REJECTED" or is_promo_wording(body) or not body:
            body = utility_body_for_topic(topic)
        else:
            body = ensure_leading_emoji(body)
        if not buttons:
            buttons = default_buttons_for_key(row.sales_template_key, name=row.name)

        new_components = build_utility_components(body=body, buttons=buttons)
        row.draft_components_json = _dumps(new_components)
        row.body_preview = body
        row.category = "UTILITY"
        if status == "REJECTED":
            # Force a new Meta submission name on next push by clearing remote id only when local-safe.
            # Keep telnyx_record_id so we can delete old remote; regenerate uses rename path.
            row.local_sync_status = "needs_resubmit"
        else:
            row.local_sync_status = "draft"
        row.updated_at = datetime.utcnow()
        db.add(row)
        return True

    @staticmethod
    def repair_all_survey_content(db: Session) -> dict[str, Any]:
        rows = list(
            db.execute(
                select(TelnyxWhatsappTemplate).where(
                    or_(
                        TelnyxWhatsappTemplate.name.ilike("voxbulk_survey_%"),
                        TelnyxWhatsappTemplate.survey_type_id.is_not(None),
                    )
                )
            ).scalars()
        )
        changed = 0
        for row in rows:
            # Skip intentional sales/marketing offer templates.
            if str(row.sales_template_key or "").startswith("sales_"):
                continue
            if WaTemplateCloseoutService.repair_survey_template_content(db, row):
                changed += 1
        if changed:
            db.commit()
        return {"ok": True, "repaired": changed, "scanned": len(rows)}

    @staticmethod
    def repair_feedback_content(db: Session) -> dict[str, Any]:
        rows = list(db.execute(select(FeedbackWaTemplate)).scalars().all())
        changed = 0
        for row in rows:
            body = str(row.body_text or "").strip()
            buttons: list[str] = []
            if row.buttons_json:
                try:
                    parsed = json.loads(row.buttons_json)
                    if isinstance(parsed, list):
                        for item in parsed:
                            if isinstance(item, str) and item.strip():
                                buttons.append(item.strip()[:25])
                            elif isinstance(item, dict):
                                label = str(item.get("text") or item.get("title") or "").strip()
                                if label:
                                    buttons.append(label[:25])
                except json.JSONDecodeError:
                    buttons = []
            needs = (
                str(row.meta_category or "").lower() == "marketing"
                or str(row.telnyx_sync_status or "").lower() == "rejected"
                or not buttons
                or not has_leading_emoji(body)
                or is_promo_wording(body)
            )
            if not needs:
                continue
            topic = None
            if row.survey_type_id:
                st = db.get(FeedbackSurveyType, row.survey_type_id)
                topic = st.name if st else None
            if not topic:
                topic = str(row.template_key or "your recent visit").replace("_", " ")
            if (
                str(row.telnyx_sync_status or "").lower() == "rejected"
                or is_promo_wording(body)
                or not body
            ):
                body = utility_body_for_topic(topic)
            else:
                body = ensure_leading_emoji(body)
            if not buttons:
                buttons = default_buttons_for_key(row.template_key)
            row.body_text = body
            row.buttons_json = _dumps([{"type": "QUICK_REPLY", "text": b} for b in buttons])
            row.meta_category = "utility"
            if str(row.telnyx_sync_status or "").lower() == "rejected":
                row.telnyx_sync_status = "draft"
            row.updated_at = datetime.utcnow()
            db.add(row)
            changed += 1
        if changed:
            db.commit()
        return {"ok": True, "repaired": changed, "scanned": len(rows)}

    @staticmethod
    def push_local_and_needs_resubmit(db: Session) -> dict[str, Any]:
        """Push survey/interview/appointment local drafts and needs_resubmit rows to Meta."""
        from app.services.survey_whatsapp_template_service import (
            SurveyWhatsappTemplateError,
            SurveyWhatsappTemplateService,
        )

        rows = list(
            db.execute(
                select(TelnyxWhatsappTemplate).where(
                    or_(
                        TelnyxWhatsappTemplate.status.in_(["LOCAL_DRAFT", "DRAFT", "REJECTED"]),
                        TelnyxWhatsappTemplate.local_sync_status.in_(["draft", "needs_resubmit"]),
                        TelnyxWhatsappTemplate.telnyx_record_id.like("local-%"),
                    )
                )
            ).scalars()
        )
        pushed = 0
        linked = 0
        failed: list[dict[str, Any]] = []
        for row in rows:
            # Skip pure sales marketing catalog unless interview/appointment/survey.
            name = str(row.name or "").lower()
            key = str(row.sales_template_key or "").lower()
            is_product = (
                "survey" in name
                or "interview" in name
                or "appointment" in name
                or key.startswith("interview_")
                or key.startswith("appointment_")
                or bool(row.survey_type_id)
                or bool(row.active_for_interview)
                or bool(getattr(row, "active_for_appointment", False))
            )
            if not is_product:
                continue
            try:
                WaTemplateCloseoutService.repair_survey_template_content(db, row)
                # Rejected: rename slightly so Meta accepts a new submission.
                if str(row.status or "").upper() == "REJECTED":
                    base = str(row.name or "voxbulk_template").strip()
                    if not base.endswith("_v2"):
                        new_name = (base[:500] + "_v2") if len(base) < 500 else base
                        try:
                            SurveyWhatsappTemplateService.rename_for_meta_sync(db, row, new_name)
                        except Exception:
                            pass
                result = SurveyWhatsappTemplateService.push_to_telnyx(db, row)
                if result.get("linked") or result.get("skipped_push"):
                    linked += 1
                else:
                    pushed += 1
            except SurveyWhatsappTemplateError as exc:
                failed.append({"id": row.id, "name": row.name, "error": str(exc)})
            except Exception as exc:  # noqa: BLE001
                failed.append({"id": row.id, "name": row.name, "error": str(exc)[:300]})
        return {
            "ok": True,
            "pushed": pushed,
            "linked": linked,
            "failed": len(failed),
            "errors": failed[:30],
            "scanned": len(rows),
        }

    @staticmethod
    def push_all_interview(db: Session) -> dict[str, Any]:
        from app.services.interview_whatsapp_template_service import (
            INTERVIEW_WA_TEMPLATE_KEYS,
            InterviewWhatsappTemplateError,
            InterviewWhatsappTemplateService,
            interview_spec_by_key,
        )
        from app.services.survey_whatsapp_template_service import _try_link_existing_remote_template
        from app.services.wa_template_meta_sync import default_wa_template_language, normalize_wa_template_language

        InterviewWhatsappTemplateService.ensure_catalog_seeded(db)
        pushed = 0
        linked = 0
        failed: list[dict[str, Any]] = []
        for key in INTERVIEW_WA_TEMPLATE_KEYS:
            spec = interview_spec_by_key(key)
            if not spec:
                continue
            row = InterviewWhatsappTemplateService._find_row_for_spec(
                db, key, str(spec.get("telnyx_name") or "")
            )
            if row is None:
                failed.append({"key": key, "error": "missing row"})
                continue
            WaTemplateCloseoutService.repair_survey_template_content(db, row)
            try:
                if _is_local_row(row):
                    lang_code, _ = normalize_wa_template_language(row.language, db=db)
                    if _try_link_existing_remote_template(
                        db, row, language=lang_code or default_wa_template_language(db)
                    ):
                        linked += 1
                        continue
                result = InterviewWhatsappTemplateService.push_to_telnyx(db, row)
                if result.get("linked") or result.get("skipped_push"):
                    linked += 1
                else:
                    pushed += 1
            except InterviewWhatsappTemplateError as exc:
                failed.append({"key": key, "id": row.id, "error": str(exc)})
            except Exception as exc:  # noqa: BLE001
                failed.append({"key": key, "id": getattr(row, "id", None), "error": str(exc)[:300]})
        db.commit()
        return {"ok": True, "pushed": pushed, "linked": linked, "failed": len(failed), "errors": failed[:20]}

    @staticmethod
    def push_all_feedback(db: Session) -> dict[str, Any]:
        from app.services.customer_feedback.feedback_telnyx_push_service import (
            FeedbackTelnyxPushError,
            push_feedback_template_to_telnyx,
        )

        WaTemplateCloseoutService.repair_feedback_content(db)
        rows = list(
            db.execute(
                select(FeedbackWaTemplate).where(
                    or_(
                        FeedbackWaTemplate.telnyx_sync_status.in_(
                            ["draft", "rejected", "submitted", "pending", "local"]
                        ),
                        FeedbackWaTemplate.is_active.is_(True),
                    )
                )
            ).scalars()
        )
        # Prefer English first, then others — push all active.
        pushed = 0
        linked = 0
        failed: list[dict[str, Any]] = []
        for row in rows:
            if not row.is_active:
                continue
            try:
                result = push_feedback_template_to_telnyx(db, row)
                if result.get("linked") or result.get("skipped_push"):
                    linked += 1
                else:
                    pushed += 1
            except FeedbackTelnyxPushError as exc:
                failed.append({"id": row.id, "key": row.template_key, "error": str(exc)[:300]})
            except Exception as exc:  # noqa: BLE001
                failed.append({"id": row.id, "key": row.template_key, "error": str(exc)[:300]})
        return {
            "ok": True,
            "pushed": pushed,
            "linked": linked,
            "failed": len(failed),
            "errors": failed[:30],
            "scanned": len(rows),
        }

    @staticmethod
    def clean_dead_orphan_rejected(db: Session, *, dry_run: bool = False) -> dict[str, Any]:
        """Delete rejected orphan survey templates when an approved sibling exists for the same slug."""
        from app.services.survey_type_template_service import template_name_survey_slug
        from app.services.telnyx_whatsapp_template_sync_service import (
            TelnyxWhatsappTemplateSyncError,
            TelnyxWhatsappTemplateSyncService,
        )

        all_types = list(db.execute(select(SurveyType)).scalars().all())
        known_slugs = [str(st.slug or "") for st in all_types]
        rejected = list(
            db.execute(
                select(TelnyxWhatsappTemplate).where(
                    func.upper(TelnyxWhatsappTemplate.status) == "REJECTED",
                    TelnyxWhatsappTemplate.name.ilike("voxbulk_survey_%"),
                )
            ).scalars()
        )
        deleted = 0
        warnings: list[str] = []
        for row in rejected:
            slug = template_name_survey_slug(str(row.name or ""), known_slugs=known_slugs)
            if not slug:
                continue
            approved_exists = db.execute(
                select(TelnyxWhatsappTemplate.id)
                .where(
                    TelnyxWhatsappTemplate.name.ilike(f"voxbulk_survey_{slug}_%"),
                    func.upper(TelnyxWhatsappTemplate.status) == "APPROVED",
                )
                .limit(1)
            ).scalar_one_or_none()
            if approved_exists is None:
                continue
            # Dead duplicate rejected — remove local + Meta.
            if dry_run:
                deleted += 1
                continue
            record_id = str(row.telnyx_record_id or "").strip()
            name = str(row.name or "").strip()
            if record_id and not record_id.startswith("local-"):
                try:
                    TelnyxWhatsappTemplateSyncService.delete_remote_template(db, record_id)
                except TelnyxWhatsappTemplateSyncError as exc:
                    warnings.append(f"{name}: {exc}")
            elif name:
                try:
                    from app.services.meta_whatsapp_template_service import MetaWhatsappTemplateService

                    MetaWhatsappTemplateService.delete_message_template(db, name=name)
                except Exception as exc:  # noqa: BLE001
                    warnings.append(f"{name}: {exc}")
            db.delete(row)
            deleted += 1
        if deleted and not dry_run:
            db.commit()
        return {"ok": True, "deleted": deleted, "warnings": warnings, "dry_run": dry_run}

    @staticmethod
    def run_full_closeout(db: Session) -> dict[str, Any]:
        from app.services.survey_whatsapp_template_service import SurveyWhatsappTemplateService

        survey_repair = WaTemplateCloseoutService.repair_all_survey_content(db)
        feedback_repair = WaTemplateCloseoutService.repair_feedback_content(db)
        relink = SurveyWhatsappTemplateService.relink_survey_templates(db)
        interview = WaTemplateCloseoutService.push_all_interview(db)
        survey_push = WaTemplateCloseoutService.push_local_and_needs_resubmit(db)
        feedback_push = WaTemplateCloseoutService.push_all_feedback(db)
        clean = WaTemplateCloseoutService.clean_dead_orphan_rejected(db, dry_run=False)
        return {
            "ok": True,
            "survey_repair": survey_repair,
            "feedback_repair": feedback_repair,
            "relink": relink,
            "interview": interview,
            "survey_push": survey_push,
            "feedback_push": feedback_push,
            "clean": clean,
        }
