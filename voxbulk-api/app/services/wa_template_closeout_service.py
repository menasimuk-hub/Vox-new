"""WA Templates close-out: force Utility rewrite, feedback buttons en/ar, push rejected."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.customer_feedback import FeedbackIndustry, FeedbackSurveyType, FeedbackWaTemplate
from app.models.industry import Industry
from app.models.survey_type import SurveyType
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.wa_template_utility_content import (
    NO_BUTTON_KINDS,
    build_utility_components,
    buttons_for_language,
    ensure_leading_emoji,
    extract_buttons_from_components,
    has_leading_emoji,
    is_promo_wording,
    meta_name_has_promo,
    parse_components_json,
    utility_body_ar_for_topic,
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


def _is_arabic_lang(lang: str | None) -> bool:
    return str(lang or "").strip().lower().startswith("ar")


def _is_our_product_template(row: TelnyxWhatsappTemplate) -> bool:
    name = str(row.name or "").lower()
    key = str(row.sales_template_key or "").lower()
    if key.startswith("sales_"):
        return False
    return (
        name.startswith("voxbulk_survey_")
        or name.startswith("voxbulk_cf_")
        or bool(row.survey_type_id)
        or key.startswith("interview_")
        or bool(row.active_for_interview)
    )


def _parse_feedback_buttons(row: FeedbackWaTemplate) -> list[str]:
    buttons: list[str] = []
    if not row.buttons_json:
        return buttons
    try:
        parsed = json.loads(row.buttons_json)
    except json.JSONDecodeError:
        return buttons
    if not isinstance(parsed, list):
        return buttons
    for item in parsed:
        if isinstance(item, str) and item.strip():
            buttons.append(item.strip()[:25])
        elif isinstance(item, dict):
            label = str(item.get("text") or item.get("title") or "").strip()
            if label:
                buttons.append(label[:25])
    return buttons


class WaTemplateCloseoutService:
    @staticmethod
    def repair_survey_template_content(db: Session, row: TelnyxWhatsappTemplate, *, force: bool = False) -> bool:
        """Ensure Utility category, leading emoji, buttons, and no marketing words."""
        if not _is_our_product_template(row) and not force:
            return False
        components = _loads(row.draft_components_json)
        body = _body_from_components(components) or str(row.body_preview or "").strip()
        buttons = extract_buttons_from_components(components)
        buttons = [re.sub(r"[^\w\s\-/'&]", "", b).strip()[:25] for b in buttons if b.strip()]
        buttons = [b for b in buttons if b and not is_promo_wording(b)]
        topic = None
        industry_slug = None
        industry_name = None
        system_kind = None
        st = db.get(SurveyType, row.survey_type_id) if row.survey_type_id else None
        if st is not None:
            topic = st.name
            system_kind = str(st.system_template_kind or "").strip().lower() or None
            if st.industry_id:
                ind = db.get(Industry, st.industry_id)
                if ind is not None:
                    industry_slug = ind.slug
                    industry_name = ind.name
        if not topic:
            topic = str(row.display_name or row.name or "your recent experience")

        status = str(row.status or "").upper()
        category = str(row.category or "").upper()
        allow_empty = system_kind in NO_BUTTON_KINDS or any(
            token in str(row.name or "").lower()
            for token in ("thank_you", "tell_us_more", "final_feedback")
        )
        employee_visit_bug = (
            "recent visit" in body.lower()
            and bool(industry_slug)
            and "employee" in str(industry_slug).lower()
        )
        needs = (
            force
            or status == "REJECTED"
            or (not buttons and not allow_empty)
            or not has_leading_emoji(body)
            or is_promo_wording(body)
            or is_promo_wording(row.name)
            or is_promo_wording(row.display_name)
            or (category == "MARKETING" and not str(row.sales_template_key or "").startswith("sales_"))
            or employee_visit_bug
        )
        if not needs:
            return False

        if _is_arabic_lang(row.language):
            body = utility_body_ar_for_topic(
                topic, industry_slug=industry_slug, industry_name=industry_name
            )
        else:
            body = utility_body_for_topic(
                topic, industry_slug=industry_slug, industry_name=industry_name
            )
        buttons = buttons_for_language(
            row.sales_template_key,
            name=row.name,
            language=row.language,
            system_kind=system_kind,
        )
        new_components = build_utility_components(
            body=body,
            buttons=buttons,
            language=row.language,
            industry_slug=industry_slug,
            industry_name=industry_name,
            allow_empty_buttons=allow_empty,
        )
        row.draft_components_json = _dumps(new_components)
        row.body_preview = body
        row.category = "UTILITY"
        row.local_sync_status = "needs_resubmit" if status in {"REJECTED", "APPROVED"} or is_promo_wording(row.name) else "draft"
        row.updated_at = datetime.utcnow()
        db.add(row)
        return True

    @staticmethod
    def repair_all_survey_content(db: Session, *, force_rejected: bool = True) -> dict[str, Any]:
        rows = list(
            db.execute(
                select(TelnyxWhatsappTemplate).where(
                    or_(
                        TelnyxWhatsappTemplate.name.ilike("voxbulk_survey_%"),
                        TelnyxWhatsappTemplate.survey_type_id.is_not(None),
                        func.upper(TelnyxWhatsappTemplate.status) == "REJECTED",
                    )
                )
            ).scalars()
        )
        changed = 0
        for row in rows:
            if str(row.sales_template_key or "").startswith("sales_"):
                continue
            force = force_rejected and str(row.status or "").upper() == "REJECTED"
            if WaTemplateCloseoutService.repair_survey_template_content(db, row, force=force):
                changed += 1
        if changed:
            db.commit()
        return {"ok": True, "repaired": changed, "scanned": len(rows)}

    @staticmethod
    def regenerate_all_feedback_templates(db: Session) -> dict[str, Any]:
        """Force every feedback template (en + ar) to Utility body + buttons + emoji (no marketing words)."""
        rows = list(db.execute(select(FeedbackWaTemplate)).scalars().all())
        changed = 0
        for row in rows:
            topic = None
            if row.survey_type_id:
                st = db.get(FeedbackSurveyType, row.survey_type_id)
                topic = st.name if st else None
            if not topic:
                topic = str(row.template_key or "your recent visit").replace("_", " ")
            if _is_arabic_lang(row.language):
                body = utility_body_ar_for_topic(topic)
            else:
                body = utility_body_for_topic(topic)
            buttons = buttons_for_language(row.template_key, name=row.template_key, language=row.language)
            row.body_text = body
            row.buttons_json = _dumps([{"type": "QUICK_REPLY", "text": b} for b in buttons])
            row.meta_category = "utility"
            if str(row.telnyx_sync_status or "").lower() in {
                "rejected",
                "approved",
                "synced",
                "live",
                "submitted",
                "marketing",
            }:
                row.telnyx_sync_status = "draft"
            row.is_active = True
            row.updated_at = datetime.utcnow()
            db.add(row)
            changed += 1

        en_rows = [
            r
            for r in rows
            if r.survey_type_id and not _is_arabic_lang(r.language) and r.industry_id is not None
        ]
        created_ar = 0
        now = datetime.utcnow()
        for en in en_rows:
            existing_ar = db.execute(
                select(FeedbackWaTemplate)
                .where(
                    FeedbackWaTemplate.survey_type_id == en.survey_type_id,
                    FeedbackWaTemplate.template_key == en.template_key,
                    FeedbackWaTemplate.language.in_(["ar", "ar_SA", "ar_EG"]),
                )
                .limit(1)
            ).scalar_one_or_none()
            if existing_ar is not None:
                continue
            st = db.get(FeedbackSurveyType, en.survey_type_id) if en.survey_type_id else None
            topic = st.name if st else str(en.template_key or "").replace("_", " ")
            buttons = buttons_for_language(en.template_key, name=en.template_key, language="ar")
            db.add(
                FeedbackWaTemplate(
                    id=str(__import__("uuid").uuid4()),
                    industry_id=en.industry_id,
                    survey_type_id=en.survey_type_id,
                    step_order=en.step_order or 1,
                    template_key=en.template_key,
                    body_text=utility_body_ar_for_topic(topic),
                    step_role=en.step_role,
                    language="ar",
                    buttons_json=_dumps([{"type": "QUICK_REPLY", "text": b} for b in buttons]),
                    meta_category="utility",
                    telnyx_sync_status="draft",
                    is_active=True,
                    created_at=now,
                    updated_at=now,
                )
            )
            created_ar += 1
        db.commit()
        return {"ok": True, "regenerated": changed, "arabic_created": created_ar}

    @staticmethod
    def repair_feedback_content(db: Session) -> dict[str, Any]:
        # Always force full regenerate so buttons/emoji are never skipped.
        return WaTemplateCloseoutService.regenerate_all_feedback_templates(db)

    @staticmethod
    def push_rejected_survey_templates(db: Session) -> dict[str, Any]:
        """Rewrite + rename + push every REJECTED survey template to Meta."""
        from app.services.survey_whatsapp_template_service import (
            SurveyWhatsappTemplateError,
            SurveyWhatsappTemplateService,
        )

        rows = list(
            db.execute(
                select(TelnyxWhatsappTemplate).where(func.upper(TelnyxWhatsappTemplate.status) == "REJECTED")
            ).scalars()
        )
        pushed = 0
        failed: list[dict[str, Any]] = []
        for row in rows:
            if str(row.sales_template_key or "").startswith("sales_"):
                continue
            try:
                WaTemplateCloseoutService.repair_survey_template_content(db, row, force=True)
                base = str(row.name or "voxbulk_survey_template").strip()
                # New Meta name so rejected content can be resubmitted.
                suffix = f"_r{datetime.utcnow().strftime('%H%M%S')}"
                new_name = (base[: 512 - len(suffix)] + suffix).lower()
                new_name = re.sub(r"[^a-z0-9_]", "_", new_name)
                try:
                    SurveyWhatsappTemplateService.rename_for_meta_sync(db, row, new_name)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("rename_rejected_failed id=%s err=%s", row.id, exc)
                result = SurveyWhatsappTemplateService.push_to_telnyx(db, row)
                if result.get("ok") is not False:
                    pushed += 1
            except SurveyWhatsappTemplateError as exc:
                failed.append({"id": row.id, "name": row.name, "error": str(exc)[:300]})
            except Exception as exc:  # noqa: BLE001
                failed.append({"id": row.id, "name": row.name, "error": str(exc)[:300]})
        return {"ok": True, "pushed": pushed, "failed": len(failed), "errors": failed[:40], "scanned": len(rows)}

    @staticmethod
    def push_local_and_needs_resubmit(db: Session) -> dict[str, Any]:
        from app.services.survey_whatsapp_template_service import (
            SurveyWhatsappTemplateError,
            SurveyWhatsappTemplateService,
        )

        # Always push rejected first.
        rejected_result = WaTemplateCloseoutService.push_rejected_survey_templates(db)

        rows = list(
            db.execute(
                select(TelnyxWhatsappTemplate).where(
                    or_(
                        TelnyxWhatsappTemplate.status.in_(["LOCAL_DRAFT", "DRAFT"]),
                        TelnyxWhatsappTemplate.local_sync_status.in_(["draft", "needs_resubmit"]),
                        TelnyxWhatsappTemplate.telnyx_record_id.like("local-%"),
                    )
                )
            ).scalars()
        )
        pushed = int(rejected_result.get("pushed") or 0)
        linked = 0
        failed: list[dict[str, Any]] = list(rejected_result.get("errors") or [])
        for row in rows:
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
                WaTemplateCloseoutService.repair_survey_template_content(db, row, force=False)
                result = SurveyWhatsappTemplateService.push_to_telnyx(db, row)
                if result.get("linked") or result.get("skipped_push"):
                    linked += 1
                else:
                    pushed += 1
            except SurveyWhatsappTemplateError as exc:
                try:
                    db.rollback()
                except Exception:
                    pass
                failed.append({"id": getattr(row, "id", None), "name": getattr(row, "name", None), "error": str(exc)[:300]})
            except Exception as exc:  # noqa: BLE001
                try:
                    db.rollback()
                except Exception:
                    pass
                failed.append({"id": getattr(row, "id", None), "name": getattr(row, "name", None), "error": str(exc)[:300]})
        return {
            "ok": True,
            "pushed": pushed,
            "linked": linked,
            "failed": len(failed),
            "errors": failed[:40],
            "scanned": len(rows) + int(rejected_result.get("scanned") or 0),
            "rejected": rejected_result,
        }

    @staticmethod
    def push_all_interview(db: Session) -> dict[str, Any]:
        from app.data.interview_whatsapp_template_catalog import interview_spec_components
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
            # Rebuild components from catalog; strip emoji from button labels for Meta.
            components = interview_spec_components(spec)
            for comp in components:
                if str(comp.get("type") or "").upper() != "BUTTONS":
                    continue
                for btn in comp.get("buttons") or []:
                    if isinstance(btn, dict) and btn.get("text"):
                        btn["text"] = re.sub(r"[^\w\s\-/'&]", "", str(btn["text"])).strip()[:25] or "OK"
            row.draft_components_json = _dumps(components)
            row.body_preview = _body_from_components(components)
            row.category = "UTILITY"
            row.local_sync_status = "draft"
            row.updated_at = datetime.utcnow()
            db.add(row)
            db.flush()
            try:
                if _is_local_row(row):
                    lang_code, _ = normalize_wa_template_language(row.language, db=db)
                    if _try_link_existing_remote_template(
                        db, row, language=lang_code or default_wa_template_language(db)
                    ):
                        linked += 1
                        continue
                # On prior Meta rejection / invalid parameter, rename and resubmit.
                if str(row.status or "").upper() == "REJECTED" or key == "interview_booking_confirm":
                    base = str(spec.get("telnyx_name") or row.name or "interview_confirm_book")
                    new_name = re.sub(r"[^a-z0-9_]", "_", f"{base}_v3".lower())
                    try:
                        from app.services.survey_whatsapp_template_service import SurveyWhatsappTemplateService

                        SurveyWhatsappTemplateService.rename_for_meta_sync(db, row, new_name)
                    except Exception:
                        pass
                result = InterviewWhatsappTemplateService.push_to_telnyx(db, row)
                if result.get("linked") or result.get("skipped_push"):
                    linked += 1
                else:
                    pushed += 1
            except InterviewWhatsappTemplateError as exc:
                failed.append({"key": key, "id": row.id, "error": str(exc)[:300]})
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

        WaTemplateCloseoutService.regenerate_all_feedback_templates(db)
        rows = list(db.execute(select(FeedbackWaTemplate).where(FeedbackWaTemplate.is_active.is_(True))).scalars())
        pushed = 0
        linked = 0
        failed: list[dict[str, Any]] = []
        for row in rows:
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
            "errors": failed[:40],
            "scanned": len(rows),
        }

    @staticmethod
    def clean_dead_orphan_rejected(db: Session, *, dry_run: bool = False) -> dict[str, Any]:
        """After successful resubmit, remove old rejected duplicates that still have no industry."""
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
                    TelnyxWhatsappTemplate.industry_id.is_(None),
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
    def link_missing_survey_types(db: Session) -> dict[str, Any]:
        """Create Utility draft + mapping for every active survey type with no template."""
        from app.services.survey_type_template_service import SurveyTypeTemplateService
        from app.services.survey_whatsapp_template_service import SurveyWhatsappTemplateService

        types = list(db.execute(select(SurveyType)).scalars().all())
        created = 0
        for st in types:
            if getattr(st, "system_template_kind", None):
                continue
            if not st.is_active:
                continue
            existing = db.execute(
                select(TelnyxWhatsappTemplate.id)
                .where(TelnyxWhatsappTemplate.survey_type_id == st.id)
                .limit(1)
            ).scalar_one_or_none()
            mappings = SurveyTypeTemplateService.list_for_survey_type(db, st.id)
            if existing or mappings:
                continue
            row = SurveyWhatsappTemplateService.create_standard_draft(
                db, survey_type=st, language="en_GB", category="UTILITY"
            )
            WaTemplateCloseoutService.repair_survey_template_content(db, row, force=True)
            created += 1
        if created:
            db.commit()
        return {"ok": True, "created": created}

    @staticmethod
    def link_missing_feedback_types(db: Session) -> dict[str, Any]:
        """Create en+ar Utility templates for every active feedback survey type missing them."""
        types = list(
            db.execute(
                select(FeedbackSurveyType).where(
                    FeedbackSurveyType.is_active.is_(True),
                    FeedbackSurveyType.archived_at.is_(None),
                )
            ).scalars().all()
        )
        created = 0
        now = datetime.utcnow()
        for st in types:
            existing = list(
                db.execute(
                    select(FeedbackWaTemplate).where(FeedbackWaTemplate.survey_type_id == st.id)
                ).scalars().all()
            )
            has_en = any(not _is_arabic_lang(r.language) for r in existing)
            has_ar = any(_is_arabic_lang(r.language) for r in existing)
            topic = st.name or st.slug
            key = str(st.slug or "topic").strip() or "topic"
            if not has_en:
                buttons = buttons_for_language(key, name=key, language="en_GB")
                db.add(
                    FeedbackWaTemplate(
                        id=str(__import__("uuid").uuid4()),
                        industry_id=st.industry_id,
                        survey_type_id=st.id,
                        step_order=1,
                        template_key=key,
                        body_text=utility_body_for_topic(topic),
                        language="en_GB",
                        buttons_json=_dumps([{"type": "QUICK_REPLY", "text": b} for b in buttons]),
                        meta_category="utility",
                        telnyx_sync_status="draft",
                        is_active=True,
                        created_at=now,
                        updated_at=now,
                    )
                )
                created += 1
            if not has_ar:
                buttons = buttons_for_language(key, name=key, language="ar")
                db.add(
                    FeedbackWaTemplate(
                        id=str(__import__("uuid").uuid4()),
                        industry_id=st.industry_id,
                        survey_type_id=st.id,
                        step_order=1,
                        template_key=key,
                        body_text=utility_body_ar_for_topic(topic),
                        language="ar",
                        buttons_json=_dumps([{"type": "QUICK_REPLY", "text": b} for b in buttons]),
                        meta_category="utility",
                        telnyx_sync_status="draft",
                        is_active=True,
                        created_at=now,
                        updated_at=now,
                    )
                )
                created += 1
        if created:
            db.commit()
        return {"ok": True, "created": created}

    @staticmethod
    def delete_meta_rejected_ours(db: Session) -> dict[str, Any]:
        """Delete rejected templates we own from Meta WABA (clears Meta Manager rejected count)."""
        from app.services.meta_whatsapp_template_service import MetaWhatsappTemplateService
        from app.services.telnyx_whatsapp_template_sync_service import TelnyxWhatsappTemplateSyncService

        try:
            remote = TelnyxWhatsappTemplateSyncService.fetch_remote_templates(db)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "deleted": 0, "error": str(exc)[:300]}

        deleted = 0
        failed: list[str] = []
        prefixes = (
            "voxbulk_survey_",
            "voxbulk_cf_",
            "voxbulk_interview_",
            "interview_",
        )
        for item in remote or []:
            if not isinstance(item, dict):
                continue
            status = str(item.get("status") or "").upper()
            name = str(item.get("name") or "").strip()
            if status != "REJECTED" or not name:
                continue
            if not any(name.lower().startswith(p) for p in prefixes):
                continue
            try:
                MetaWhatsappTemplateService.delete_message_template(db, name=name)
                deleted += 1
            except Exception as exc:  # noqa: BLE001
                failed.append(f"{name}: {exc}"[:200])
        return {"ok": True, "deleted": deleted, "failed": len(failed), "errors": failed[:30]}

    @staticmethod
    def rename_promo_meta_names(db: Session) -> dict[str, Any]:
        """Rename local rows whose Meta name contains marketing words so we can resubmit as Utility."""
        from app.services.survey_whatsapp_template_service import SurveyWhatsappTemplateService

        rows = list(
            db.execute(
                select(TelnyxWhatsappTemplate).where(
                    or_(
                        TelnyxWhatsappTemplate.name.ilike("%promotion%"),
                        TelnyxWhatsappTemplate.name.ilike("%discount%"),
                        TelnyxWhatsappTemplate.name.ilike("%loyalty%"),
                        TelnyxWhatsappTemplate.name.ilike("%offer%"),
                    )
                )
            ).scalars()
        )
        renamed = 0
        for row in rows:
            if not _is_our_product_template(row):
                continue
            if not meta_name_has_promo(row.name):
                continue
            base = re.sub(
                r"(promotion|promotions|discount|discounts|loyalty|offer|offers)",
                "service",
                str(row.name or "voxbulk_template"),
                flags=re.I,
            )
            new_name = re.sub(r"[^a-z0-9_]", "_", base.lower())
            new_name = re.sub(r"_+", "_", new_name).strip("_")[:500]
            if new_name == str(row.name or ""):
                new_name = f"{new_name}_util"
            try:
                WaTemplateCloseoutService.repair_survey_template_content(db, row, force=True)
                SurveyWhatsappTemplateService.rename_for_meta_sync(db, row, new_name)
                renamed += 1
            except Exception as exc:  # noqa: BLE001
                logger.warning("rename_promo_failed id=%s err=%s", row.id, exc)
        return {"ok": True, "renamed": renamed}

    @staticmethod
    def run_full_closeout(db: Session) -> dict[str, Any]:
        from app.services.survey_whatsapp_template_service import SurveyWhatsappTemplateService

        link_survey = WaTemplateCloseoutService.link_missing_survey_types(db)
        link_feedback = WaTemplateCloseoutService.link_missing_feedback_types(db)
        survey_repair = WaTemplateCloseoutService.repair_all_survey_content(db, force_rejected=True)
        # Force rewrite anything with marketing words.
        promo_rows = list(db.execute(select(TelnyxWhatsappTemplate)).scalars())
        promo_fixed = 0
        for row in promo_rows:
            if not _is_our_product_template(row):
                continue
            body = _body_from_components(_loads(row.draft_components_json)) or str(row.body_preview or "")
            if (
                is_promo_wording(body)
                or is_promo_wording(row.name)
                or str(row.category or "").upper() == "MARKETING"
            ):
                if WaTemplateCloseoutService.repair_survey_template_content(db, row, force=True):
                    promo_fixed += 1
        if promo_fixed:
            db.commit()
        rename_promo = WaTemplateCloseoutService.rename_promo_meta_names(db)
        feedback_repair = WaTemplateCloseoutService.regenerate_all_feedback_templates(db)
        relink = SurveyWhatsappTemplateService.relink_survey_templates(db)
        interview = WaTemplateCloseoutService.push_all_interview(db)
        survey_push = WaTemplateCloseoutService.push_local_and_needs_resubmit(db)
        feedback_push = WaTemplateCloseoutService.push_all_feedback(db)
        meta_rejected = WaTemplateCloseoutService.delete_meta_rejected_ours(db)
        clean = WaTemplateCloseoutService.clean_dead_orphan_rejected(db, dry_run=False)
        return {
            "ok": True,
            "link_survey": link_survey,
            "link_feedback": link_feedback,
            "survey_repair": survey_repair,
            "promo_fixed": promo_fixed,
            "rename_promo": rename_promo,
            "feedback_repair": feedback_repair,
            "relink": relink,
            "interview": interview,
            "survey_push": survey_push,
            "feedback_push": feedback_push,
            "meta_rejected_deleted": meta_rejected,
            "clean": clean,
        }
