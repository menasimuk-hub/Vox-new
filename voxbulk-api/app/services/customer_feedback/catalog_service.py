"""Customer Feedback catalog — industries, survey types, packages."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models.customer_feedback import (
    FEEDBACK_SERVICE_CODE,
    FeedbackIndustry,
    FeedbackIndustryOrganisation,
    FeedbackLocation,
    FeedbackPackage,
    FeedbackSurveyType,
    FeedbackWaTemplate,
)
from app.models.plan import Plan
from app.services.customer_feedback.seed_service import FeedbackSeedService
from app.services.customer_feedback.survey_config_service import ENGLISH_TEMPLATE_LANGUAGES
from app.services.market_zone import country_to_zone, normalize_zone
from app.services.plan_price_service import PlanPriceService


def _slugify(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", str(name or "").lower()).strip("-")
    return base[:60] or "item"


def industry_to_dict(row: FeedbackIndustry, *, org_ids: list[str] | None = None) -> dict[str, Any]:
    payload = {
        "id": row.id,
        "slug": row.slug,
        "name": row.name,
        "description": row.description,
        "is_active": row.is_active,
        "visibility_mode": str(getattr(row, "visibility_mode", None) or "all"),
        "sort_order": row.sort_order,
    }
    if org_ids is not None:
        payload["org_ids"] = org_ids
    return payload


def survey_type_to_dict(row: FeedbackSurveyType) -> dict[str, Any]:
    return {
        "id": row.id,
        "industry_id": row.industry_id,
        "slug": row.slug,
        "name": row.name,
        "description": row.description,
        "is_active": row.is_active,
        "archived_at": row.archived_at.isoformat() if row.archived_at else None,
        "sort_order": row.sort_order,
    }


def package_to_dict(db: Session, row: FeedbackPackage) -> dict[str, Any]:
    plan = db.get(Plan, row.plan_id)
    prices = PlanPriceService.list_for_plan(db, row.plan_id) if plan else []
    features: list[str] = []
    if plan and plan.features_json:
        try:
            parsed = json.loads(plan.features_json)
            if isinstance(parsed, list):
                features = [str(item) for item in parsed]
        except json.JSONDecodeError:
            features = []
    return {
        "id": row.id,
        "plan_id": row.plan_id,
        "plan_code": plan.code if plan else None,
        "plan_name": plan.name if plan else None,
        "market_zone": row.market_zone,
        "max_locations": row.max_locations,
        "wa_units_included": row.wa_units_included,
        "web_units_included": row.web_units_included,
        "promo_message_cost_minor": row.promo_message_cost_minor,
        "admin_notes": row.admin_notes,
        "is_active": row.is_active,
        "is_featured": bool(plan.is_featured) if plan else False,
        "display_order": row.display_order,
        "features": features,
        "prices": [
            {
                "currency": p.currency,
                "monthly_price_minor": p.monthly_price_minor,
                "yearly_price_minor": p.yearly_price_minor,
            }
            for p in prices
        ],
    }


class FeedbackCatalogService:
    @staticmethod
    def ensure_ready(db: Session) -> None:
        FeedbackSeedService.ensure_seeded(db)

    @staticmethod
    def industry_org_ids(db: Session, industry_id: str) -> list[str]:
        return list(
            db.execute(
                select(FeedbackIndustryOrganisation.org_id)
                .where(FeedbackIndustryOrganisation.industry_id == industry_id)
                .order_by(FeedbackIndustryOrganisation.created_at.asc())
            ).scalars()
        )

    @staticmethod
    def set_industry_orgs(db: Session, industry_id: str, org_ids: list[str]) -> list[str]:
        cleaned: list[str] = []
        seen: set[str] = set()
        for raw in org_ids or []:
            oid = str(raw or "").strip()
            if not oid or oid in seen:
                continue
            seen.add(oid)
            cleaned.append(oid)
        db.execute(delete(FeedbackIndustryOrganisation).where(FeedbackIndustryOrganisation.industry_id == industry_id))
        now = datetime.utcnow()
        for oid in cleaned:
            db.add(
                FeedbackIndustryOrganisation(
                    id=str(uuid.uuid4()),
                    industry_id=industry_id,
                    org_id=oid,
                    created_at=now,
                )
            )
        db.commit()
        return cleaned

    @staticmethod
    def _industry_visible_to_org(db: Session, row: FeedbackIndustry, org_id: str | None) -> bool:
        if not row.is_active:
            return False
        mode = str(getattr(row, "visibility_mode", None) or "all").strip().lower()
        if mode != "restricted":
            return True
        if not org_id:
            return False
        linked = db.execute(
            select(FeedbackIndustryOrganisation.id).where(
                FeedbackIndustryOrganisation.industry_id == row.id,
                FeedbackIndustryOrganisation.org_id == org_id,
            )
        ).scalar_one_or_none()
        return linked is not None

    @staticmethod
    def list_industries(
        db: Session,
        *,
        include_inactive: bool = False,
        org_id: str | None = None,
        include_org_ids: bool = False,
    ) -> list[dict[str, Any]]:
        FeedbackCatalogService.ensure_ready(db)
        q = select(FeedbackIndustry).order_by(FeedbackIndustry.sort_order, FeedbackIndustry.name)
        if not include_inactive:
            q = q.where(FeedbackIndustry.is_active.is_(True))
        rows = list(db.execute(q).scalars().all())
        if org_id is not None:
            rows = [r for r in rows if FeedbackCatalogService._industry_visible_to_org(db, r, org_id)]
        return [
            FeedbackCatalogService.industry_with_stats(db, r, include_org_ids=include_org_ids)
            for r in rows
        ]

    @staticmethod
    def industry_with_stats(
        db: Session,
        row: FeedbackIndustry,
        *,
        include_org_ids: bool = False,
    ) -> dict[str, Any]:
        org_ids = FeedbackCatalogService.industry_org_ids(db, row.id) if include_org_ids else None
        base = industry_to_dict(row, org_ids=org_ids)
        survey_type_count = int(
            db.execute(
                select(func.count())
                .select_from(FeedbackSurveyType)
                .where(
                    FeedbackSurveyType.industry_id == row.id,
                    FeedbackSurveyType.archived_at.is_(None),
                    FeedbackSurveyType.is_active.is_(True),
                )
            ).scalar_one()
            or 0
        )
        # Every language row (en + ar) — matches hub list.
        hub = FeedbackCatalogService.list_industry_hub_templates(db, row.id)
        templates = list(hub.get("templates") or [])
        approved = sum(
            1
            for t in templates
            if str(t.get("status") or t.get("telnyx_sync_status") or "").lower()
            in {"approved", "synced", "live"}
        )
        rejected = sum(
            1
            for t in templates
            if str(t.get("status") or t.get("telnyx_sync_status") or "").lower() == "rejected"
        )
        pending = sum(
            1
            for t in templates
            if str(t.get("status") or t.get("telnyx_sync_status") or "").lower()
            in {"draft", "pending", "submitted", "local", "local_draft"}
        )
        total = len(templates)
        if total <= 0:
            health = "empty"
        elif rejected > 0:
            health = "rejected"
        elif approved >= total:
            health = "approved"
        else:
            health = "pending"
        base.update(
            {
                "survey_type_count": survey_type_count,
                "template_count": total,
                "approved_count": approved,
                "approved_template_count": approved,
                "pending_count": pending,
                "pending_template_count": pending,
                "rejected_template_count": rejected,
                "approval_health": health,
            }
        )
        return base

    @staticmethod
    def _pick_primary_template(rows: list[FeedbackWaTemplate]) -> FeedbackWaTemplate | None:
        if not rows:
            return None
        active = [r for r in rows if r.is_active]
        pool = active or rows
        for lang in ENGLISH_TEMPLATE_LANGUAGES:
            for row in pool:
                if str(row.language or "").strip() == lang:
                    return row
        for row in pool:
            if str(row.language or "").strip().lower().startswith("en"):
                return row
        return pool[0]

    @staticmethod
    def list_industry_hub_templates(db: Session, industry_id: str) -> dict[str, Any]:
        """One row per language template (en + ar both listed) for the admin hub."""
        industry = db.get(FeedbackIndustry, industry_id)
        if industry is None:
            raise ValueError("Industry not found")
        types = list(
            db.execute(
                select(FeedbackSurveyType)
                .where(
                    FeedbackSurveyType.industry_id == industry_id,
                    FeedbackSurveyType.archived_at.is_(None),
                    FeedbackSurveyType.is_active.is_(True),
                )
                .order_by(FeedbackSurveyType.sort_order, FeedbackSurveyType.name)
            ).scalars().all()
        )
        from app.services.customer_feedback.feedback_telnyx_push_service import (
            english_anchor_template,
            feedback_meta_template_name,
        )

        templates_out: list[dict[str, Any]] = []
        unlinked_types: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        industry_slug = str(industry.slug or "")
        for st in types:
            tpl_rows = list(
                db.execute(
                    select(FeedbackWaTemplate)
                    .where(FeedbackWaTemplate.survey_type_id == st.id)
                    .order_by(
                        FeedbackWaTemplate.language,
                        FeedbackWaTemplate.step_order,
                        FeedbackWaTemplate.template_key,
                    )
                ).scalars().all()
            )
            if not tpl_rows:
                unlinked_types.append({"id": st.id, "slug": st.slug, "name": st.name})
                continue
            for tpl in tpl_rows:
                if tpl.id in seen_ids:
                    continue
                seen_ids.add(tpl.id)
                item = FeedbackCatalogService.template_to_dict(tpl)
                item["survey_type_name"] = st.name
                item["survey_type_slug"] = st.slug
                item["name"] = st.name
                item["display_name"] = st.name
                item["language_count"] = 1
                item["languages"] = [str(tpl.language or "en_GB")]
                try:
                    anchor = english_anchor_template(db, tpl)
                    meta_name = feedback_meta_template_name(
                        tpl,
                        industry_slug=industry_slug,
                        survey_type_slug=str(st.slug or ""),
                        name_anchor_id=anchor.id,
                    )
                except Exception:  # noqa: BLE001
                    meta_name = ""
                item["meta_name"] = meta_name
                item["telnyx_name"] = meta_name
                templates_out.append(item)
        return {"templates": templates_out, "unlinked_types": unlinked_types}

    @staticmethod
    def get_industry_detail(db: Session, industry_id: str) -> dict[str, Any]:
        row = db.get(FeedbackIndustry, industry_id)
        if row is None:
            raise ValueError("Industry not found")
        detail = FeedbackCatalogService.industry_with_stats(db, row, include_org_ids=True)
        types = FeedbackCatalogService.list_survey_types(db, industry_id=industry_id, include_archived=False)
        enriched_types = []
        for item in types:
            tpl_rows = list(
                db.execute(
                    select(FeedbackWaTemplate).where(FeedbackWaTemplate.survey_type_id == item["id"])
                ).scalars().all()
            )
            primary = FeedbackCatalogService._pick_primary_template(tpl_rows)
            primary_status = str(primary.telnyx_sync_status or "").lower() if primary else ""
            approved = 1 if primary_status in {"approved", "synced", "live"} else 0
            enriched_types.append(
                {
                    **item,
                    "template_count": 1 if primary else 0,
                    "approved_count": approved,
                    "pending_count": 0 if approved or not primary else 1,
                    "synced": approved > 0,
                    "status": "live" if approved > 0 else "draft",
                }
            )
        detail["survey_types"] = enriched_types
        return detail

    @staticmethod
    def get_survey_type_detail(db: Session, survey_type_id: str) -> dict[str, Any]:
        row = db.get(FeedbackSurveyType, survey_type_id)
        if row is None:
            raise ValueError("Survey type not found")
        industry = db.get(FeedbackIndustry, row.industry_id)
        detail = survey_type_to_dict(row)
        detail["industry_name"] = industry.name if industry else None
        tpl_rows = list(
            db.execute(
                select(FeedbackWaTemplate)
                .where(FeedbackWaTemplate.survey_type_id == row.id)
                .order_by(FeedbackWaTemplate.step_order, FeedbackWaTemplate.template_key)
            ).scalars().all()
        )
        detail["templates"] = [FeedbackCatalogService.template_to_dict(t) for t in tpl_rows]
        approved = sum(1 for t in tpl_rows if str(t.telnyx_sync_status or "").lower() in {"approved", "synced", "live"})
        detail["template_count"] = len(tpl_rows)
        detail["approved_count"] = approved
        detail["pending_count"] = max(0, len(tpl_rows) - approved)
        detail["status"] = "live" if approved > 0 else "draft"
        return detail

    @staticmethod
    def template_to_dict(row: FeedbackWaTemplate) -> dict[str, Any]:
        buttons: list[dict[str, str]] = []
        if row.buttons_json:
            try:
                parsed = json.loads(row.buttons_json)
                if isinstance(parsed, list):
                    buttons = parsed
            except json.JSONDecodeError:
                buttons = []
        key = str(row.template_key or "").strip()
        key_labels = {
            "thank_you": "Thank you",
            "tell_us_more": "Tell us more",
            "marketing_opt_in": "Opt in",
            "open_question": "Share your feedback",
        }
        label = key_labels.get(key) or key.replace("_", " ").title() or "Template"
        # Normalize buttons for admin UI (always list of {text}).
        norm_buttons: list[dict[str, str]] = []
        for b in buttons:
            if isinstance(b, str) and b.strip():
                norm_buttons.append({"type": "QUICK_REPLY", "text": b.strip()[:25]})
            elif isinstance(b, dict):
                text = str(b.get("text") or b.get("title") or "").strip()
                if text:
                    norm_buttons.append({"type": "QUICK_REPLY", "text": text[:25]})
        return {
            "id": row.id,
            "industry_id": row.industry_id,
            "survey_type_id": row.survey_type_id,
            "step_order": row.step_order,
            "template_key": row.template_key,
            "name": label,
            "display_name": label,
            "body_text": row.body_text,
            "body_preview": row.body_text,
            "body": row.body_text,
            "step_role": row.step_role,
            "language": row.language,
            "buttons": norm_buttons,
            "meta_category": row.meta_category,
            "telnyx_sync_status": row.telnyx_sync_status,
            "status": row.telnyx_sync_status,
            "approval_status": str(row.telnyx_sync_status or "").upper(),
            "is_active": row.is_active,
        }

    @staticmethod
    def list_survey_types(
        db: Session,
        *,
        industry_id: str | None = None,
        include_archived: bool = False,
        exclude_disabled: bool = False,
    ) -> list[dict[str, Any]]:
        FeedbackCatalogService.ensure_ready(db)
        q = select(FeedbackSurveyType).order_by(FeedbackSurveyType.sort_order, FeedbackSurveyType.name)
        if industry_id:
            q = q.where(FeedbackSurveyType.industry_id == industry_id)
        if not include_archived:
            q = q.where(FeedbackSurveyType.archived_at.is_(None), FeedbackSurveyType.is_active.is_(True))
        rows = list(db.execute(q).scalars().all())
        if exclude_disabled:
            from app.services.disabled_wa_template_service import DisabledWaTemplateService

            hidden = DisabledWaTemplateService.hidden_feedback_survey_type_ids(db)
            if hidden:
                rows = [r for r in rows if r.id not in hidden]
        return [survey_type_to_dict(r) for r in rows]

    @staticmethod
    def upsert_industry(db: Session, payload: dict[str, Any]) -> dict[str, Any]:
        now = datetime.utcnow()
        row_id = str(payload.get("id") or "").strip()
        desired_slug = _slugify(payload.get("slug") or payload.get("name") or "")
        if row_id:
            row = db.get(FeedbackIndustry, row_id)
            if row is None:
                raise ValueError("Industry not found")
        else:
            existing = None
            if desired_slug:
                existing = db.execute(
                    select(FeedbackIndustry).where(FeedbackIndustry.slug == desired_slug).limit(1)
                ).scalar_one_or_none()
            if existing is not None:
                if existing.is_active:
                    raise ValueError(f"An industry with slug “{desired_slug}” already exists")
                # Inactive leftover — reactivate instead of duplicate insert.
                row = existing
            else:
                row = FeedbackIndustry(
                    id=str(uuid.uuid4()),
                    slug=desired_slug or _slugify(payload.get("name") or "industry"),
                    created_at=now,
                )
                db.add(row)
        row.name = str(payload.get("name") or row.name).strip()
        if payload.get("slug") or desired_slug:
            new_slug = _slugify(payload.get("slug") or desired_slug or row.slug)
            clash = db.execute(
                select(FeedbackIndustry).where(
                    FeedbackIndustry.slug == new_slug,
                    FeedbackIndustry.id != row.id,
                ).limit(1)
            ).scalar_one_or_none()
            if clash is not None:
                raise ValueError(f"An industry with slug “{new_slug}” already exists")
            row.slug = new_slug
        if "description" in payload:
            row.description = payload.get("description")
        row.is_active = bool(payload.get("is_active", True))
        row.sort_order = int(payload.get("sort_order", row.sort_order or 100))
        visibility_mode = str(payload.get("visibility_mode") or getattr(row, "visibility_mode", None) or "all").strip().lower()
        if visibility_mode not in {"all", "restricted"}:
            visibility_mode = "restricted" if payload.get("org_ids") else "all"
        if "visibility_mode" in payload or "org_ids" in payload or not row_id:
            if "visibility_mode" not in payload and payload.get("org_ids"):
                visibility_mode = "restricted"
            row.visibility_mode = visibility_mode
        row.updated_at = now
        db.commit()
        db.refresh(row)
        if "org_ids" in payload or (not row_id and visibility_mode == "restricted"):
            org_ids = list(payload.get("org_ids") or []) if visibility_mode == "restricted" else []
            FeedbackCatalogService.set_industry_orgs(db, row.id, org_ids)
        org_ids = FeedbackCatalogService.industry_org_ids(db, row.id)
        return industry_to_dict(row, org_ids=org_ids)

    @staticmethod
    def delete_industry(db: Session, industry_id: str) -> dict[str, Any]:
        """Hard-delete an industry, its survey types, templates, and org links."""
        from app.services.customer_feedback.feedback_telnyx_push_service import (
            english_anchor_template,
            feedback_meta_template_name,
        )
        from app.services.meta_whatsapp_template_service import MetaWhatsappTemplateService

        row = db.get(FeedbackIndustry, industry_id)
        if row is None:
            raise ValueError("Industry not found")
        in_use = int(
            db.execute(
                select(func.count()).select_from(FeedbackLocation).where(FeedbackLocation.industry_id == industry_id)
            ).scalar_one()
            or 0
        )
        if in_use > 0:
            raise ValueError("Industry has active locations and cannot be deleted.")

        industry_slug = str(row.slug or "")
        types = list(
            db.execute(select(FeedbackSurveyType).where(FeedbackSurveyType.industry_id == industry_id)).scalars().all()
        )
        type_ids = [t.id for t in types]
        type_slug_by_id = {t.id: t.slug for t in types}

        by_id: dict[str, FeedbackWaTemplate] = {}
        for tpl in db.execute(
            select(FeedbackWaTemplate).where(FeedbackWaTemplate.industry_id == industry_id)
        ).scalars().all():
            by_id[tpl.id] = tpl
        if type_ids:
            for tpl in db.execute(
                select(FeedbackWaTemplate).where(FeedbackWaTemplate.survey_type_id.in_(type_ids))
            ).scalars().all():
                by_id[tpl.id] = tpl
        templates = list(by_id.values())
        # Prefer unique Meta names (shared across languages via English anchor).
        meta_names: set[str] = set()
        warnings: list[str] = []
        for tpl in templates:
            try:
                anchor = english_anchor_template(db, tpl)
                survey_slug = type_slug_by_id.get(str(tpl.survey_type_id or ""))
                meta_names.add(
                    feedback_meta_template_name(
                        tpl,
                        industry_slug=industry_slug,
                        survey_type_slug=survey_slug,
                        name_anchor_id=anchor.id,
                    )
                )
            except Exception as exc:  # noqa: BLE001 — best-effort Meta cleanup
                warnings.append(f"{tpl.template_key}: could not resolve Meta name ({exc})")

        for name in sorted(meta_names):
            try:
                MetaWhatsappTemplateService.delete_message_template(db, name=name)
            except Exception as exc:  # noqa: BLE001 — remove locally even if Meta fails
                warnings.append(f"{name}: Meta delete failed; removed locally ({exc})")

        deleted_templates = 0
        for tpl in templates:
            db.delete(tpl)
            deleted_templates += 1
        db.flush()

        deleted_types = 0
        for st in types:
            fresh = db.get(FeedbackSurveyType, st.id)
            if fresh is not None:
                db.delete(fresh)
                deleted_types += 1
        db.flush()

        db.execute(delete(FeedbackIndustryOrganisation).where(FeedbackIndustryOrganisation.industry_id == industry_id))
        db.delete(row)
        db.commit()

        result: dict[str, Any] = {
            "ok": True,
            "deleted_industry_id": industry_id,
            "deleted_industry_slug": industry_slug,
            "deleted_survey_types": deleted_types,
            "deleted_templates": deleted_templates,
        }
        if warnings:
            result["warnings"] = warnings
        return result

    @staticmethod
    def upsert_survey_type(db: Session, payload: dict[str, Any]) -> dict[str, Any]:
        now = datetime.utcnow()
        industry_id = str(payload.get("industry_id") or "").strip()
        if not industry_id:
            raise ValueError("industry_id required")
        row_id = str(payload.get("id") or "").strip()
        if row_id:
            row = db.get(FeedbackSurveyType, row_id)
            if row is None:
                raise ValueError("Survey type not found")
        else:
            row = FeedbackSurveyType(
                id=str(uuid.uuid4()),
                industry_id=industry_id,
                slug=_slugify(payload.get("slug") or payload.get("name")),
                created_at=now,
            )
            db.add(row)
        row.industry_id = industry_id
        row.name = str(payload.get("name") or row.name).strip()
        if payload.get("slug"):
            row.slug = _slugify(payload["slug"])
        row.description = payload.get("description")
        if "is_active" in payload:
            row.is_active = bool(payload["is_active"])
        if payload.get("archive"):
            row.archived_at = now
            row.is_active = False
        row.sort_order = int(payload.get("sort_order", row.sort_order or 100))
        row.updated_at = now
        db.commit()
        db.refresh(row)
        return survey_type_to_dict(row)

    @staticmethod
    def list_packages(db: Session, *, market_zone: str | None = None, active_only: bool = True) -> list[dict[str, Any]]:
        FeedbackCatalogService.ensure_ready(db)
        q = (
            select(FeedbackPackage, Plan)
            .join(Plan, Plan.id == FeedbackPackage.plan_id)
            .where(Plan.service_kind == FEEDBACK_SERVICE_CODE)
            .order_by(FeedbackPackage.display_order, Plan.name)
        )
        zone = normalize_zone(market_zone)
        if zone:
            q = q.where(FeedbackPackage.market_zone == zone)
        if active_only:
            q = q.where(FeedbackPackage.is_active.is_(True), Plan.is_active.is_(True))
        rows = list(db.execute(q).all())
        return [package_to_dict(db, pkg) for pkg, _plan in rows]

    @staticmethod
    def resolve_market_zone(db: Session, org) -> str:
        return normalize_zone(getattr(org, "market_zone", None)) or country_to_zone(getattr(org, "country", None))

    @staticmethod
    def list_feedback_plans(db: Session, *, market_zone: str | None = None) -> list[dict[str, Any]]:
        FeedbackCatalogService.ensure_ready(db)
        q = (
            select(Plan, FeedbackPackage)
            .join(FeedbackPackage, FeedbackPackage.plan_id == Plan.id)
            .where(Plan.service_kind == FEEDBACK_SERVICE_CODE)
            .order_by(FeedbackPackage.display_order, Plan.name)
        )
        zone = normalize_zone(market_zone)
        if zone:
            q = q.where(FeedbackPackage.market_zone == zone)
        rows = list(db.execute(q).all())
        return [
            {
                "id": plan.id,
                "code": plan.code,
                "name": plan.name,
                "market_zone": pkg.market_zone,
                "max_locations": pkg.max_locations,
                "wa_units_included": pkg.wa_units_included,
            }
            for plan, pkg in rows
        ]

    @staticmethod
    def upsert_package(db: Session, payload: dict[str, Any]) -> dict[str, Any]:
        now = datetime.utcnow()
        plan_id = str(payload.get("plan_id") or "").strip()
        plan_code = str(payload.get("plan_code") or "").strip().lower()
        plan = db.get(Plan, plan_id) if plan_id else None
        if plan is None and plan_code:
            plan = db.execute(select(Plan).where(Plan.code == plan_code)).scalar_one_or_none()
        if plan is None:
            raise ValueError("plan_id or plan_code required")
        if str(plan.service_kind or "") != FEEDBACK_SERVICE_CODE:
            plan.service_kind = FEEDBACK_SERVICE_CODE
        row = db.execute(select(FeedbackPackage).where(FeedbackPackage.plan_id == plan.id)).scalar_one_or_none()
        if row is None:
            row = FeedbackPackage(id=str(uuid.uuid4()), plan_id=plan.id, created_at=now)
            db.add(row)
        row.market_zone = normalize_zone(payload.get("market_zone")) or row.market_zone or "gb"
        row.max_locations = int(payload.get("max_locations", row.max_locations or 1))
        row.wa_units_included = int(payload.get("wa_units_included", row.wa_units_included or 100))
        if "web_units_included" in payload:
            row.web_units_included = int(payload.get("web_units_included", row.web_units_included or 0))
        row.promo_message_cost_minor = int(payload.get("promo_message_cost_minor", row.promo_message_cost_minor or 5))
        row.admin_notes = payload.get("admin_notes")
        row.is_active = bool(payload.get("is_active", row.is_active))
        row.display_order = int(payload.get("display_order", row.display_order or 100))
        row.updated_at = now
        db.commit()
        db.refresh(row)
        return package_to_dict(db, row)
