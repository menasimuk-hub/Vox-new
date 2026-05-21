from __future__ import annotations

import json
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.legal_page import LegalPage

_DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "legal_default_bodies.json"


DEFAULT_LEGAL_PAGES: list[dict[str, str | int | bool]] = [
    {"slug": "terms", "title": "Terms & Conditions", "public_path": "/legal-policies", "sort_order": 1},
    {"slug": "privacy", "title": "Privacy Policy", "public_path": "/legal-policies", "sort_order": 2},
    {"slug": "cookies", "title": "Cookie Policy", "public_path": "/legal-policies", "sort_order": 3},
    {"slug": "gdpr", "title": "GDPR", "public_path": "/legal-policies", "sort_order": 4},
    {"slug": "legal", "title": "Legal", "public_path": "/legal-policies", "sort_order": 5},
]


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def legal_page_to_dict(row: LegalPage, *, include_body: bool = True) -> dict:
    body = effective_body(row) if include_body else ""
    out = {
        "slug": row.slug,
        "title": row.title,
        "public_path": row.public_path,
        "meta_description": row.meta_description,
        "body": body,
        "is_published": bool(row.is_published),
        "sort_order": int(row.sort_order or 0),
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
    }
    return out


@lru_cache(maxsize=1)
def load_default_bodies() -> dict[str, str]:
    if not _DATA_PATH.exists():
        return {}
    try:
        data = json.loads(_DATA_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v) for k, v in data.items() if v}


def effective_body(row: LegalPage) -> str:
    stored = str(row.body or "").strip()
    if stored:
        return row.body or ""
    return load_default_bodies().get(row.slug, "")


class LegalPageService:
    @staticmethod
    def seed_empty_bodies(db: Session) -> None:
        bodies = load_default_bodies()
        if not bodies:
            return
        rows = list(db.execute(select(LegalPage)).scalars().all())
        changed = False
        for row in rows:
            if str(row.body or "").strip():
                continue
            default = bodies.get(row.slug, "")
            if not default:
                continue
            row.body = default
            row.public_path = "/legal-policies"
            row.updated_at = datetime.utcnow()
            db.add(row)
            changed = True
        if changed:
            db.commit()

    @staticmethod
    def ensure_defaults(db: Session) -> None:
        existing = set(db.execute(select(LegalPage.slug)).scalars().all())
        bodies = load_default_bodies()
        changed = False
        for item in DEFAULT_LEGAL_PAGES:
            slug = str(item["slug"])
            if slug in existing:
                continue
            db.add(
                LegalPage(
                    slug=slug,
                    title=str(item["title"]),
                    public_path=str(item["public_path"]),
                    body=bodies.get(slug, ""),
                    is_published=True,
                    sort_order=int(item["sort_order"]),
                )
            )
            changed = True
        if changed:
            db.commit()
        LegalPageService.seed_empty_bodies(db)

    @staticmethod
    def list_pages(db: Session) -> list[LegalPage]:
        LegalPageService.ensure_defaults(db)
        return list(db.execute(select(LegalPage).order_by(LegalPage.sort_order.asc(), LegalPage.slug.asc())).scalars().all())

    @staticmethod
    def get_page(db: Session, slug: str) -> LegalPage | None:
        LegalPageService.ensure_defaults(db)
        clean = str(slug or "").strip().lower()
        if not clean:
            return None
        return db.execute(select(LegalPage).where(LegalPage.slug == clean)).scalar_one_or_none()

    @staticmethod
    def get_public_page(db: Session, slug: str) -> LegalPage | None:
        row = LegalPageService.get_page(db, slug)
        if row is None or not row.is_published:
            return None
        return row

    @staticmethod
    def list_public_pages(db: Session) -> list[LegalPage]:
        LegalPageService.ensure_defaults(db)
        rows = list(
            db.execute(
                select(LegalPage)
                .where(LegalPage.is_published.is_(True))
                .order_by(LegalPage.sort_order.asc(), LegalPage.slug.asc())
            ).scalars().all()
        )
        return rows

    @staticmethod
    def update_page(db: Session, slug: str, *, title: str, meta_description: str | None, body: str, is_published: bool) -> LegalPage:
        row = LegalPageService.get_page(db, slug)
        if row is None:
            raise ValueError(f"Unknown legal page slug: {slug}")
        row.title = str(title or "").strip() or row.title
        row.meta_description = str(meta_description or "").strip() or None
        row.body = str(body or "")
        row.is_published = bool(is_published)
        row.updated_at = datetime.utcnow()
        db.add(row)
        db.commit()
        db.refresh(row)
        return row
