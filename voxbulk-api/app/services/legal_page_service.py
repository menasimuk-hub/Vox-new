from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.legal_page import LegalPage


DEFAULT_LEGAL_PAGES: list[dict[str, str | int | bool]] = [
    {"slug": "terms", "title": "Terms & Conditions", "public_path": "/terms", "sort_order": 1},
    {"slug": "privacy", "title": "Privacy Policy", "public_path": "/privacy", "sort_order": 2},
    {"slug": "cookies", "title": "Cookie Policy", "public_path": "/cookies", "sort_order": 3},
    {"slug": "gdpr", "title": "GDPR", "public_path": "/gdpr", "sort_order": 4},
    {"slug": "legal", "title": "Legal", "public_path": "/legal", "sort_order": 5},
]


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def legal_page_to_dict(row: LegalPage, *, include_body: bool = True) -> dict:
    out = {
        "slug": row.slug,
        "title": row.title,
        "public_path": row.public_path,
        "meta_description": row.meta_description,
        "body": row.body if include_body else "",
        "is_published": bool(row.is_published),
        "sort_order": int(row.sort_order or 0),
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
    }
    return out


class LegalPageService:
    @staticmethod
    def ensure_defaults(db: Session) -> None:
        existing = set(db.execute(select(LegalPage.slug)).scalars().all())
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
                    body="",
                    is_published=True,
                    sort_order=int(item["sort_order"]),
                )
            )
            changed = True
        if changed:
            db.commit()

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
