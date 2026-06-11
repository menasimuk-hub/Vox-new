"""Customer Feedback catalog — industries, survey types, packages."""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.customer_feedback import (
    FEEDBACK_SERVICE_CODE,
    FeedbackIndustry,
    FeedbackPackage,
    FeedbackSurveyType,
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
    return {
        "id": row.id,
        "plan_id": row.plan_id,
        "plan_code": plan.code if plan else None,
        "plan_name": plan.name if plan else None,
        "market_zone": row.market_zone,
        "max_locations": row.max_locations,
        "wa_units_included": row.wa_units_included,
        "admin_notes": row.admin_notes,
        "is_active": row.is_active,
        "display_order": row.display_order,
        "prices": [
            {
                "currency": p.currency,
                "monthly_price_minor": p.monthly_price_minor,
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
        return [industry_to_dict(r) for r in rows]

    @staticmethod
    def list_survey_types(db: Session, *, industry_id: str | None = None, include_archived: bool = False) -> list[dict[str, Any]]:
        FeedbackCatalogService.ensure_ready(db)
        q = select(FeedbackSurveyType).order_by(FeedbackSurveyType.sort_order, FeedbackSurveyType.name)
        if industry_id:
            q = q.where(FeedbackSurveyType.industry_id == industry_id)
        if not include_archived:
            q = q.where(FeedbackSurveyType.archived_at.is_(None), FeedbackSurveyType.is_active.is_(True))
        rows = list(db.execute(q).scalars().all())
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
    def upsert_package(db: Session, payload: dict[str, Any]) -> dict[str, Any]:
        now = datetime.utcnow()
        plan_id = str(payload.get("plan_id") or "").strip()
        plan = db.get(Plan, plan_id) if plan_id else None
        if plan is None:
            raise ValueError("plan_id required")
        if str(plan.service_kind or "") != FEEDBACK_SERVICE_CODE:
            plan.service_kind = FEEDBACK_SERVICE_CODE
        row = db.execute(select(FeedbackPackage).where(FeedbackPackage.plan_id == plan.id)).scalar_one_or_none()
        if row is None:
            row = FeedbackPackage(id=str(uuid.uuid4()), plan_id=plan.id, created_at=now)
            db.add(row)
        row.market_zone = normalize_zone(payload.get("market_zone")) or row.market_zone or "gb"
        row.max_locations = int(payload.get("max_locations", row.max_locations or 1))
        row.wa_units_included = int(payload.get("wa_units_included", row.wa_units_included or 100))
        row.admin_notes = payload.get("admin_notes")
        row.is_active = bool(payload.get("is_active", row.is_active))
        row.display_order = int(payload.get("display_order", row.display_order or 100))
        row.updated_at = now
        db.commit()
        db.refresh(row)
        return package_to_dict(db, row)
