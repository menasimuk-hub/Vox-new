"""Customer Feedback catalog — industries, survey types, packages."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.customer_feedback import (
    FEEDBACK_SERVICE_CODE,
    FeedbackIndustry,
    FeedbackPackage,
    FeedbackSurveyType,
    FeedbackWaTemplate,
)
from app.models.plan import Plan
from app.services.customer_feedback.seed_service import FeedbackSeedService
from app.services.market_zone import country_to_zone, normalize_zone
from app.services.plan_price_service import PlanPriceService


def _slugify(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", str(name or "").lower()).strip("-")
    return base[:60] or "item"


def industry_to_dict(row: FeedbackIndustry) -> dict[str, Any]:
    return {
        "id": row.id,
        "slug": row.slug,
        "name": row.name,
        "description": row.description,
        "is_active": row.is_active,
        "sort_order": row.sort_order,
    }


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
    def list_industries(db: Session, *, include_inactive: bool = False) -> list[dict[str, Any]]:
        FeedbackCatalogService.ensure_ready(db)
        q = select(FeedbackIndustry).order_by(FeedbackIndustry.sort_order, FeedbackIndustry.name)
        if not include_inactive:
            q = q.where(FeedbackIndustry.is_active.is_(True))
        rows = list(db.execute(q).scalars().all())
        return [FeedbackCatalogService.industry_with_stats(db, r) for r in rows]

    @staticmethod
    def industry_with_stats(db: Session, row: FeedbackIndustry) -> dict[str, Any]:
        base = industry_to_dict(row)
        survey_type_count = int(
            db.execute(
                select(func.count())
                .select_from(FeedbackSurveyType)
                .where(FeedbackSurveyType.industry_id == row.id, FeedbackSurveyType.archived_at.is_(None))
            ).scalar_one()
            or 0
        )
        template_q = select(FeedbackWaTemplate).where(FeedbackWaTemplate.industry_id == row.id)
        templates = list(db.execute(template_q).scalars().all())
        approved = sum(1 for t in templates if str(t.telnyx_sync_status or "").lower() in {"approved", "synced", "live"})
        rejected = sum(1 for t in templates if str(t.telnyx_sync_status or "").lower() == "rejected")
        pending = sum(1 for t in templates if str(t.telnyx_sync_status or "").lower() in {"draft", "pending", "submitted"})
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
    def get_industry_detail(db: Session, industry_id: str) -> dict[str, Any]:
        row = db.get(FeedbackIndustry, industry_id)
        if row is None:
            raise ValueError("Industry not found")
        detail = FeedbackCatalogService.industry_with_stats(db, row)
        types = FeedbackCatalogService.list_survey_types(db, industry_id=industry_id, include_archived=True)
        enriched_types = []
        for item in types:
            tpl_rows = list(
                db.execute(
                    select(FeedbackWaTemplate).where(FeedbackWaTemplate.survey_type_id == item["id"])
                ).scalars().all()
            )
            approved = sum(1 for t in tpl_rows if str(t.telnyx_sync_status or "").lower() in {"approved", "synced", "live"})
            enriched_types.append(
                {
                    **item,
                    "template_count": len(tpl_rows),
                    "approved_count": approved,
                    "pending_count": max(0, len(tpl_rows) - approved),
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
            "step_role": row.step_role,
            "language": row.language,
            "buttons": buttons,
            "meta_category": row.meta_category,
            "telnyx_sync_status": row.telnyx_sync_status,
            "status": row.telnyx_sync_status,
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
        if row_id:
            row = db.get(FeedbackIndustry, row_id)
            if row is None:
                raise ValueError("Industry not found")
        else:
            row = FeedbackIndustry(id=str(uuid.uuid4()), slug=_slugify(payload.get("slug") or payload.get("name")), created_at=now)
            db.add(row)
        row.name = str(payload.get("name") or row.name).strip()
        if payload.get("slug"):
            row.slug = _slugify(payload["slug"])
        row.description = payload.get("description")
        row.is_active = bool(payload.get("is_active", row.is_active))
        row.sort_order = int(payload.get("sort_order", row.sort_order or 100))
        row.updated_at = now
        db.commit()
        db.refresh(row)
        return industry_to_dict(row)

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
