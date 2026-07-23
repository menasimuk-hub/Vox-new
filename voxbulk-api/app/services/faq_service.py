from __future__ import annotations

import re
from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.data.marketing_faqs import DEMO_SUPPORT_FAQ_QUESTIONS, MARKETING_FAQ_GROUPS
from app.models.faq import FAQCategory, FAQItem


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (value or "").strip().lower()).strip("-")
    return slug or "faq"


class FAQService:
    @staticmethod
    def ensure_marketing_faqs(db: Session) -> dict[str, int]:
        """Remove demo support FAQs from public SEO and insert missing marketing FAQs only."""
        now = datetime.utcnow()
        removed = 0
        demo_rows = db.execute(select(FAQItem)).scalars().all()
        for row in demo_rows:
            if str(row.question or "").strip() in DEMO_SUPPORT_FAQ_QUESTIONS:
                db.delete(row)
                removed += 1

        # Drop empty demo categories if nothing left in them.
        for slug in ("getting-started", "billing", "technical"):
            cat = db.execute(select(FAQCategory).where(FAQCategory.slug == slug)).scalar_one_or_none()
            if cat is None:
                continue
            remaining = db.execute(
                select(FAQItem.id).where(FAQItem.category_id == cat.id).limit(1)
            ).scalar_one_or_none()
            if remaining is None:
                db.delete(cat)

        created = 0
        for (cat_name, cat_slug, cat_order), faqs in MARKETING_FAQ_GROUPS:
            product = db.execute(select(FAQCategory).where(FAQCategory.slug == cat_slug)).scalar_one_or_none()
            if product is None:
                product = FAQCategory(name=cat_name, slug=cat_slug, sort_order=cat_order, created_at=now)
                db.add(product)
                db.flush()
            else:
                dirty_cat = False
                if product.name != cat_name:
                    product.name = cat_name
                    dirty_cat = True
                if int(product.sort_order or 0) != int(cat_order):
                    product.sort_order = int(cat_order)
                    dirty_cat = True
                if dirty_cat:
                    db.add(product)

            for question, answer, slug, sort_order, featured in faqs:
                row = db.execute(select(FAQItem).where(FAQItem.slug == slug)).scalar_one_or_none()
                if row is None:
                    row = db.execute(select(FAQItem).where(FAQItem.question == question)).scalar_one_or_none()
                if row is None:
                    row = FAQItem(
                        category_id=product.id,
                        question=question,
                        answer=answer,
                        slug=slug,
                        is_featured=bool(featured),
                        is_published=True,
                        sort_order=int(sort_order),
                        robots="index,follow",
                        meta_title=f"{question} | VoxBulk Help",
                        meta_description=answer[:155].rstrip() + ("…" if len(answer) > 155 else ""),
                        focus_keyword="voxbulk help",
                        index_status="pending",
                        created_at=now,
                        updated_at=now,
                        published_at=now,
                    )
                    db.add(row)
                    created += 1
                    continue
                # Existing row: keep Admin-edited Q&A; only repair public SEO visibility.
                dirty = False
                if not str(row.slug or "").strip():
                    row.slug = slug
                    dirty = True
                if row.category_id is None:
                    row.category_id = product.id
                    dirty = True
                if not row.is_published:
                    row.is_published = True
                    dirty = True
                if "noindex" in str(row.robots or "").lower():
                    row.robots = "index,follow"
                    dirty = True
                if not str(row.meta_title or "").strip():
                    row.meta_title = f"{row.question} | VoxBulk Help"
                    dirty = True
                if not str(row.meta_description or "").strip():
                    row.meta_description = (row.answer or "")[:155]
                    dirty = True
                if dirty:
                    row.updated_at = now
                    db.add(row)

        db.commit()
        return {"removed_demo": removed, "created": created}

    @staticmethod
    def seed_defaults(db: Session) -> None:
        """Ensure public marketing FAQs exist (replaces legacy demo support seeds)."""
        FAQService.ensure_marketing_faqs(db)

    @staticmethod
    def list_categories(db: Session) -> list[FAQCategory]:
        FAQService.seed_defaults(db)
        return list(db.execute(select(FAQCategory).order_by(FAQCategory.sort_order.asc(), FAQCategory.name.asc())).scalars())

    @staticmethod
    def upsert_category(db: Session, *, category_id: int | None, name: str, slug: str | None, sort_order: int) -> FAQCategory:
        now = datetime.utcnow()
        row = db.get(FAQCategory, category_id) if category_id else None
        if row is None:
            row = FAQCategory(created_at=now)
        row.name = name.strip()
        row.slug = slugify(slug or name)
        row.sort_order = int(sort_order or 0)
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def delete_category(db: Session, category_id: int) -> None:
        db.query(FAQItem).filter(FAQItem.category_id == category_id).update({"category_id": None})
        row = db.get(FAQCategory, category_id)
        if row is not None:
            db.delete(row)
        db.commit()

    @staticmethod
    def list_items(
        db: Session,
        *,
        search: str | None = None,
        category_id: int | None = None,
        published_only: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[FAQItem]:
        FAQService.seed_defaults(db)
        stmt = select(FAQItem)
        if published_only:
            stmt = stmt.where(FAQItem.is_published == True)  # noqa: E712
        if category_id:
            stmt = stmt.where(FAQItem.category_id == category_id)
        if search:
            q = f"%{search.strip()}%"
            stmt = stmt.where(or_(FAQItem.question.ilike(q), FAQItem.answer.ilike(q)))
        return list(
            db.execute(
                stmt.order_by(FAQItem.is_featured.desc(), FAQItem.sort_order.asc(), FAQItem.updated_at.desc())
                .limit(min(max(limit, 1), 200))
                .offset(max(offset, 0))
            ).scalars()
        )

    @staticmethod
    def upsert_item(db: Session, *, item_id: int | None, category_id: int | None, question: str, answer: str, is_featured: bool, is_published: bool, sort_order: int) -> FAQItem:
        now = datetime.utcnow()
        row = db.get(FAQItem, item_id) if item_id else None
        if row is None:
            row = FAQItem(created_at=now, published_at=now)
        if category_id and db.get(FAQCategory, category_id) is None:
            raise ValueError("FAQ category not found")
        row.category_id = category_id
        row.question = question.strip()
        row.answer = answer.strip()
        row.is_featured = bool(is_featured)
        row.is_published = bool(is_published)
        row.sort_order = int(sort_order or 0)
        row.updated_at = now
        if not (row.slug or "").strip():
            base = slugify(row.question)
            candidate = base
            n = 2
            while True:
                q = select(FAQItem.id).where(FAQItem.slug == candidate)
                if row.id is not None:
                    q = q.where(FAQItem.id != row.id)
                if db.execute(q).scalar_one_or_none() is None:
                    break
                candidate = f"{base}-{n}"[:180]
                n += 1
            row.slug = candidate
        if row.is_published and "noindex" not in (row.robots or "").lower():
            if row.index_status == "excluded":
                row.index_status = "pending"
        elif not row.is_published or "noindex" in (row.robots or "").lower():
            row.index_status = "excluded"
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def delete_item(db: Session, item_id: int) -> None:
        row = db.get(FAQItem, item_id)
        if row is not None:
            db.delete(row)
        db.commit()


def category_to_dict(c: FAQCategory) -> dict:
    return {"id": c.id, "name": c.name, "slug": c.slug, "sort_order": c.sort_order, "created_at": c.created_at}


def item_to_dict(db: Session, item: FAQItem) -> dict:
    cat_name = db.execute(select(FAQCategory.name).where(FAQCategory.id == item.category_id)).scalar_one_or_none() if item.category_id else None
    return {
        "id": item.id,
        "category_id": item.category_id,
        "category_name": cat_name,
        "question": item.question,
        "answer": item.answer,
        "is_featured": bool(item.is_featured),
        "is_published": bool(item.is_published),
        "sort_order": item.sort_order,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }

