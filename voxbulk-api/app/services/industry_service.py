"""Industry CRUD and seed data for WA Survey."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.industry import Industry

DEFAULT_INDUSTRIES: list[dict[str, Any]] = [
    {"slug": "healthcare", "name": "Healthcare", "description": "Clinics, dental, hospitals, care providers.", "sort_order": 10},
    {"slug": "ecommerce", "name": "E-commerce", "description": "Online retail and delivery feedback.", "sort_order": 20},
    {"slug": "finance", "name": "Finance", "description": "Banking, insurance, and financial services.", "sort_order": 30},
    {"slug": "hospitality", "name": "Hospitality", "description": "Hotels, restaurants, venues.", "sort_order": 40},
    {"slug": "education", "name": "Education", "description": "Schools, training, and ed-tech.", "sort_order": 50},
    {"slug": "saas", "name": "SaaS / Technology", "description": "Software and digital product feedback.", "sort_order": 60},
    {"slug": "general", "name": "General / Other", "description": "Cross-industry or unspecified vertical.", "sort_order": 90},
]


def industry_to_dict(row: Industry) -> dict[str, Any]:
    return {
        "id": row.id,
        "slug": row.slug,
        "name": row.name,
        "description": row.description,
        "is_active": bool(row.is_active),
        "sort_order": int(row.sort_order or 100),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


class IndustryService:
    @staticmethod
    def ensure_defaults(db: Session) -> None:
        now = datetime.utcnow()
        for item in DEFAULT_INDUSTRIES:
            existing = db.execute(select(Industry).where(Industry.slug == item["slug"])).scalar_one_or_none()
            if existing is not None:
                continue
            db.add(
                Industry(
                    id=str(uuid.uuid4()),
                    slug=item["slug"],
                    name=item["name"],
                    description=item.get("description"),
                    is_active=True,
                    sort_order=int(item.get("sort_order") or 100),
                    created_at=now,
                    updated_at=now,
                )
            )
        db.commit()

    @staticmethod
    def list_industries(db: Session, *, active_only: bool = True) -> list[dict[str, Any]]:
        IndustryService.ensure_defaults(db)
        stmt = select(Industry).order_by(Industry.sort_order.asc(), Industry.name.asc())
        if active_only:
            stmt = stmt.where(Industry.is_active.is_(True))
        rows = list(db.execute(stmt).scalars())
        return [industry_to_dict(r) for r in rows]

    @staticmethod
    def get_industry(db: Session, industry_id: str) -> Industry | None:
        tid = str(industry_id or "").strip()
        if not tid:
            return None
        return db.get(Industry, tid)

    @staticmethod
    def get_by_slug(db: Session, slug: str) -> Industry | None:
        key = str(slug or "").strip().lower()
        if not key:
            return None
        IndustryService.ensure_defaults(db)
        return db.execute(select(Industry).where(Industry.slug == key)).scalar_one_or_none()

    @staticmethod
    def require_industry_id(db: Session, industry_id: str) -> Industry:
        row = IndustryService.get_industry(db, industry_id)
        if row is None or not row.is_active:
            raise ValueError("A valid industry is required")
        return row

    @staticmethod
    def default_industry(db: Session) -> Industry:
        IndustryService.ensure_defaults(db)
        row = IndustryService.get_by_slug(db, "general")
        if row is None:
            row = db.execute(select(Industry).order_by(Industry.sort_order.asc()).limit(1)).scalar_one()
        return row
