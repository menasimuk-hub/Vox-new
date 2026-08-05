from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.support_kb import SupportHelpLink, SupportKbArticle, SupportKbCategory, SupportSlaSettings

logger = logging.getLogger(__name__)

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(value: str) -> str:
    slug = _SLUG_RE.sub("-", (value or "").strip().lower()).strip("-")
    return slug or "article"


class SupportKbService:
    @staticmethod
    def list_categories(db: Session, *, kind: str | None = "article") -> list[SupportKbCategory]:
        from app.services.support_content_seed_service import SupportContentSeedService

        SupportContentSeedService.ensure_defaults(db)
        stmt = select(SupportKbCategory)
        if kind:
            stmt = stmt.where(SupportKbCategory.kind == kind)
        return list(db.execute(stmt.order_by(SupportKbCategory.sort_order.asc(), SupportKbCategory.name.asc())).scalars())

    @staticmethod
    def upsert_category(
        db: Session,
        *,
        category_id: int | None,
        name: str,
        description: str = "",
        colour: str = "#3b82f6",
        kind: str = "article",
        sort_order: int = 0,
    ) -> SupportKbCategory:
        now = datetime.utcnow()
        row = db.get(SupportKbCategory, category_id) if category_id else None
        if row is None:
            row = SupportKbCategory(created_at=now)
        row.name = (name or "").strip()
        row.description = description or ""
        row.colour = (colour or "#3b82f6").strip()
        row.kind = (kind or "article").strip() or "article"
        row.sort_order = int(sort_order or 0)
        row.updated_at = now
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def delete_category(db: Session, category_id: int) -> None:
        db.query(SupportKbArticle).filter(SupportKbArticle.category_id == category_id).update({"category_id": None})
        row = db.get(SupportKbCategory, category_id)
        if row is not None:
            db.delete(row)
        db.commit()

    @staticmethod
    def list_articles(db: Session, *, kind: str | None = "article", published_only: bool = False) -> list[SupportKbArticle]:
        from app.services.support_content_seed_service import SupportContentSeedService, is_support_content_visible

        SupportContentSeedService.ensure_defaults(db)
        stmt = select(SupportKbArticle)
        if kind:
            stmt = stmt.where(SupportKbArticle.kind == kind)
        if published_only:
            stmt = stmt.where(SupportKbArticle.state == "published")
        rows = list(db.execute(stmt.order_by(SupportKbArticle.updated_at.desc())).scalars())
        if published_only:
            rows = [r for r in rows if is_support_content_visible(db, getattr(r, "linked_service", None))]
        return rows

    @staticmethod
    def get_by_slug(db: Session, slug: str, *, published_only: bool = True) -> SupportKbArticle | None:
        from app.services.support_content_seed_service import is_support_content_visible

        stmt = select(SupportKbArticle).where(SupportKbArticle.slug == (slug or "").strip())
        if published_only:
            stmt = stmt.where(SupportKbArticle.state == "published")
        row = db.execute(stmt).scalar_one_or_none()
        if row is None:
            return None
        if published_only and not is_support_content_visible(db, getattr(row, "linked_service", None)):
            return None
        return row

    @staticmethod
    def upsert_article(
        db: Session,
        *,
        article_id: int | None,
        title: str,
        body: str = "",
        category_id: int | None = None,
        kind: str = "article",
        state: str = "draft",
        author: str = "",
        slug: str | None = None,
    ) -> SupportKbArticle:
        now = datetime.utcnow()
        row = db.get(SupportKbArticle, article_id) if article_id else None
        if row is None:
            row = SupportKbArticle(created_at=now, views=0, version=1)
        row.title = (title or "").strip()
        row.body = body or ""
        row.category_id = category_id
        row.kind = (kind or "article").strip() or "article"
        row.state = (state or "draft").strip() or "draft"
        row.author = (author or "").strip()
        base_slug = _slugify(slug or row.title)
        # Ensure unique slug
        candidate = base_slug
        n = 2
        while True:
            other = db.execute(
                select(SupportKbArticle.id).where(SupportKbArticle.slug == candidate, SupportKbArticle.id != (row.id or 0))
            ).scalar_one_or_none()
            if other is None:
                break
            candidate = f"{base_slug}-{n}"
            n += 1
        row.slug = candidate
        if article_id:
            row.version = int(row.version or 1) + 1
        row.updated_at = now
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def delete_article(db: Session, article_id: int) -> None:
        row = db.get(SupportKbArticle, article_id)
        if row is not None:
            db.delete(row)
            db.commit()

    @staticmethod
    def category_to_dict(c: SupportKbCategory) -> dict[str, Any]:
        return {
            "id": c.id,
            "kind": c.kind,
            "name": c.name,
            "slug": getattr(c, "slug", None),
            "description": c.description,
            "colour": c.colour,
            "linked_service": getattr(c, "linked_service", None),
            "sort_order": c.sort_order,
            "created_at": c.created_at,
            "updated_at": c.updated_at,
        }

    @staticmethod
    def article_to_dict(a: SupportKbArticle, *, public_base: str = "https://voxbulk.com") -> dict[str, Any]:
        base = (public_base or "https://voxbulk.com").rstrip("/")
        return {
            "id": a.id,
            "category_id": a.category_id,
            "kind": a.kind,
            "title": a.title,
            "slug": a.slug,
            "body": a.body,
            "state": a.state,
            "views": a.views,
            "author": a.author,
            "version": a.version,
            "linked_service": getattr(a, "linked_service", None),
            "url": f"{base}/help/articles/{a.slug}",
            "created_at": a.created_at,
            "updated_at": a.updated_at,
        }


class SupportHelpLinkService:
    @staticmethod
    def list_links(db: Session, *, active_only: bool = False) -> list[SupportHelpLink]:
        from app.services.support_content_seed_service import SupportContentSeedService, is_support_content_visible

        SupportContentSeedService.ensure_defaults(db)
        stmt = select(SupportHelpLink)
        if active_only:
            stmt = stmt.where(SupportHelpLink.is_active == True)  # noqa: E712
        rows = list(db.execute(stmt.order_by(SupportHelpLink.sort_order.asc(), SupportHelpLink.title.asc())).scalars())
        if active_only:
            rows = [r for r in rows if is_support_content_visible(db, getattr(r, "linked_service", None))]
        return rows

    @staticmethod
    def upsert(
        db: Session,
        *,
        link_id: int | None,
        title: str,
        url: str,
        category: str = "",
        description: str = "",
        is_active: bool = True,
        sort_order: int = 0,
    ) -> SupportHelpLink:
        now = datetime.utcnow()
        row = db.get(SupportHelpLink, link_id) if link_id else None
        if row is None:
            row = SupportHelpLink(created_at=now)
        row.title = (title or "").strip()
        row.url = (url or "").strip()
        row.category = (category or "").strip()
        row.description = description or ""
        row.is_active = bool(is_active)
        row.sort_order = int(sort_order or 0)
        row.updated_at = now
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def delete(db: Session, link_id: int) -> None:
        row = db.get(SupportHelpLink, link_id)
        if row is not None:
            db.delete(row)
            db.commit()

    @staticmethod
    def to_dict(row: SupportHelpLink) -> dict[str, Any]:
        return {
            "id": row.id,
            "title": row.title,
            "label": row.title,
            "url": row.url,
            "category": row.category,
            "description": row.description,
            "seed_key": getattr(row, "seed_key", None),
            "linked_service": getattr(row, "linked_service", None),
            "is_active": bool(row.is_active),
            "sort_order": row.sort_order,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }


class SupportSlaService:
    DEFAULT_POLICIES = [
        {"id": "first_response", "name": "First response", "first_reply_minutes": 240, "resolution_minutes": 0, "compliance": 0},
        {"id": "resolution", "name": "Full resolution", "first_reply_minutes": 0, "resolution_minutes": 2880, "compliance": 0},
        {"id": "waiting", "name": "Customer waiting", "first_reply_minutes": 1440, "resolution_minutes": 0, "compliance": 0},
    ]

    @staticmethod
    def get_row(db: Session) -> SupportSlaSettings:
        row = db.execute(select(SupportSlaSettings).limit(1)).scalar_one_or_none()
        if row is None:
            now = datetime.utcnow()
            row = SupportSlaSettings(first_response_hours=4, resolve_hours=48, waiting_hours=24, updated_at=now)
            db.add(row)
            db.commit()
            db.refresh(row)
        return row

    @staticmethod
    def get_settings(db: Session) -> dict[str, Any]:
        row = SupportSlaService.get_row(db)
        policies = [
            {
                "id": "first_response",
                "name": "First response",
                "first_reply_minutes": int(row.first_response_hours or 4) * 60,
                "resolution_minutes": 0,
                "compliance": 0,
            },
            {
                "id": "resolution",
                "name": "Full resolution",
                "first_reply_minutes": 0,
                "resolution_minutes": int(row.resolve_hours or 48) * 60,
                "compliance": 0,
            },
            {
                "id": "waiting",
                "name": "Customer waiting",
                "first_reply_minutes": int(row.waiting_hours or 24) * 60,
                "resolution_minutes": 0,
                "compliance": 0,
            },
        ]
        return {
            "first_response_hours": row.first_response_hours,
            "resolve_hours": row.resolve_hours,
            "waiting_hours": row.waiting_hours,
            "policies": policies,
            "updated_at": row.updated_at,
        }

    @staticmethod
    def save_settings(db: Session, payload: dict[str, Any]) -> dict[str, Any]:
        row = SupportSlaService.get_row(db)
        policies = payload.get("policies")
        if isinstance(policies, list) and policies:
            for p in policies:
                pid = str(p.get("id") or p.get("name") or "").lower()
                if "first" in pid or "first" in str(p.get("name") or "").lower():
                    mins = int(p.get("first_reply_minutes") or 0)
                    if mins > 0:
                        row.first_response_hours = max(1, mins // 60)
                elif "resol" in pid or "resol" in str(p.get("name") or "").lower():
                    mins = int(p.get("resolution_minutes") or 0)
                    if mins > 0:
                        row.resolve_hours = max(1, mins // 60)
                elif "wait" in pid or "wait" in str(p.get("name") or "").lower():
                    mins = int(p.get("first_reply_minutes") or p.get("resolution_minutes") or 0)
                    if mins > 0:
                        row.waiting_hours = max(1, mins // 60)
        if payload.get("first_response_hours") is not None:
            row.first_response_hours = max(1, int(payload["first_response_hours"]))
        if payload.get("resolve_hours") is not None:
            row.resolve_hours = max(1, int(payload["resolve_hours"]))
        if payload.get("waiting_hours") is not None:
            row.waiting_hours = max(1, int(payload["waiting_hours"]))
        row.updated_at = datetime.utcnow()
        db.add(row)
        db.commit()
        return SupportSlaService.get_settings(db)
