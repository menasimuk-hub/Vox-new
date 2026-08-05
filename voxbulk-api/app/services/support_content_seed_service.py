"""Insert-missing-only curated support content tied to platform product groups."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data.support_content_defaults import (
    CANNED_CATEGORIES,
    DASHBOARD_FAQ_CATEGORIES,
    HELP_LINKS,
    KB_CATEGORIES,
    OPTIONAL_PRODUCT_KEYS,
)
from app.models.faq import FAQCategory, FAQItem
from app.models.support_kb import SupportHelpLink, SupportKbArticle, SupportKbCategory
from app.models.support_ticket import CannedReply, CannedReplyCategory
from app.services.platform_product_visibility_service import PlatformProductVisibilityService


def _norm_svc(raw: str | None) -> str | None:
    s = (raw or "").strip().lower().replace("-", "_")
    return s or None


def is_support_content_visible(db: Session, linked_service: str | None) -> bool:
    """Hide product-tied support content when the platform group is disabled; keep rows."""
    svc = _norm_svc(linked_service)
    if not svc:
        return True
    return PlatformProductVisibilityService.is_faq_visible(db, linked_service=svc)


class SupportContentSeedService:
    @staticmethod
    def existing_product_keys(db: Session) -> set[str]:
        PlatformProductVisibilityService.ensure_defaults(db)
        return {r.key for r in PlatformProductVisibilityService.list_groups(db)}

    @staticmethod
    def _should_seed(spec: dict[str, Any], existing_keys: set[str]) -> bool:
        svc = _norm_svc(spec.get("linked_service"))
        optional = bool(spec.get("optional")) or (svc in OPTIONAL_PRODUCT_KEYS if svc else False)
        if optional:
            return bool(svc and svc in existing_keys)
        return True

    @staticmethod
    def ensure_defaults(db: Session) -> dict[str, int]:
        """Insert missing dashboard FAQ, canned replies, KB articles and help links only."""
        existing_keys = SupportContentSeedService.existing_product_keys(db)
        counts = {
            "faq_categories": 0,
            "faq_items": 0,
            "canned_categories": 0,
            "canned_replies": 0,
            "kb_categories": 0,
            "kb_articles": 0,
            "help_links": 0,
        }
        counts["faq_categories"], counts["faq_items"] = SupportContentSeedService._seed_dashboard_faq(
            db, existing_keys
        )
        counts["canned_categories"], counts["canned_replies"] = SupportContentSeedService._seed_canned(
            db, existing_keys
        )
        counts["kb_categories"], counts["kb_articles"] = SupportContentSeedService._seed_kb(
            db, existing_keys
        )
        counts["help_links"] = SupportContentSeedService._seed_help_links(db, existing_keys)
        db.commit()
        return counts

    @staticmethod
    def _seed_dashboard_faq(db: Session, existing_keys: set[str]) -> tuple[int, int]:
        now = datetime.utcnow()
        cats_created = 0
        items_created = 0
        for spec in DASHBOARD_FAQ_CATEGORIES:
            if not SupportContentSeedService._should_seed(spec, existing_keys):
                continue
            slug = str(spec["slug"])
            svc = _norm_svc(spec.get("linked_service"))
            cat = db.execute(select(FAQCategory).where(FAQCategory.slug == slug)).scalar_one_or_none()
            if cat is None:
                cat = FAQCategory(
                    name=str(spec["name"]),
                    slug=slug,
                    sort_order=int(spec.get("sort_order") or 0),
                    surface="dashboard",
                    created_at=now,
                )
                db.add(cat)
                db.flush()
                cats_created += 1
            for item in spec.get("items") or []:
                item_slug = str(item["slug"])
                row = db.execute(select(FAQItem).where(FAQItem.slug == item_slug)).scalar_one_or_none()
                if row is not None:
                    # Insert-missing only — never overwrite Admin Q&A.
                    if not getattr(row, "linked_service", None) and svc:
                        row.linked_service = svc
                        db.add(row)
                    continue
                row = FAQItem(
                    category_id=cat.id,
                    question=str(item["question"]),
                    answer=str(item["answer"]),
                    slug=item_slug,
                    surface="dashboard",
                    is_featured=False,
                    is_published=True,
                    sort_order=int(item.get("sort_order") or 0),
                    linked_service=svc,
                    robots="noindex,follow",
                    meta_title="",
                    meta_description="",
                    created_at=now,
                    updated_at=now,
                    published_at=now,
                )
                db.add(row)
                items_created += 1
        return cats_created, items_created

    @staticmethod
    def _seed_canned(db: Session, existing_keys: set[str]) -> tuple[int, int]:
        now = datetime.utcnow()
        cats_created = 0
        replies_created = 0
        for spec in CANNED_CATEGORIES:
            if not SupportContentSeedService._should_seed(spec, existing_keys):
                continue
            slug = str(spec["slug"])
            svc = _norm_svc(spec.get("linked_service"))
            cat = db.execute(
                select(CannedReplyCategory).where(CannedReplyCategory.slug == slug)
            ).scalar_one_or_none()
            if cat is None:
                cat = db.execute(
                    select(CannedReplyCategory).where(CannedReplyCategory.name == str(spec["name"]))
                ).scalar_one_or_none()
            if cat is None:
                cat = CannedReplyCategory(
                    name=str(spec["name"]),
                    slug=slug,
                    description=str(spec.get("description") or ""),
                    linked_service=svc,
                    created_at=now,
                    updated_at=now,
                )
                db.add(cat)
                db.flush()
                cats_created += 1
            else:
                dirty = False
                if not getattr(cat, "slug", None):
                    cat.slug = slug
                    dirty = True
                if svc and not getattr(cat, "linked_service", None):
                    cat.linked_service = svc
                    dirty = True
                if dirty:
                    cat.updated_at = now
                    db.add(cat)
            for reply in spec.get("replies") or []:
                seed_key = str(reply["seed_key"])
                row = db.execute(
                    select(CannedReply).where(CannedReply.seed_key == seed_key)
                ).scalar_one_or_none()
                if row is not None:
                    if svc and not getattr(row, "linked_service", None):
                        row.linked_service = svc
                        db.add(row)
                    continue
                row = CannedReply(
                    category_id=cat.id,
                    title=str(reply["title"]),
                    question=str(reply["question"]),
                    answer=str(reply["answer"]),
                    seed_key=seed_key,
                    linked_service=svc,
                    is_active=True,
                    created_at=now,
                    updated_at=now,
                )
                db.add(row)
                replies_created += 1
        return cats_created, replies_created

    @staticmethod
    def _seed_kb(db: Session, existing_keys: set[str]) -> tuple[int, int]:
        now = datetime.utcnow()
        cats_created = 0
        articles_created = 0
        for spec in KB_CATEGORIES:
            if not SupportContentSeedService._should_seed(spec, existing_keys):
                continue
            slug = str(spec["slug"])
            svc = _norm_svc(spec.get("linked_service"))
            cat = db.execute(
                select(SupportKbCategory).where(SupportKbCategory.slug == slug)
            ).scalar_one_or_none()
            if cat is None:
                cat = SupportKbCategory(
                    kind="article",
                    name=str(spec["name"]),
                    slug=slug,
                    description=str(spec.get("description") or ""),
                    linked_service=svc,
                    sort_order=int(spec.get("sort_order") or 0),
                    created_at=now,
                    updated_at=now,
                )
                db.add(cat)
                db.flush()
                cats_created += 1
            else:
                dirty = False
                if svc and not getattr(cat, "linked_service", None):
                    cat.linked_service = svc
                    dirty = True
                if dirty:
                    cat.updated_at = now
                    db.add(cat)
            for article in spec.get("articles") or []:
                art_slug = str(article["slug"])
                row = db.execute(
                    select(SupportKbArticle).where(SupportKbArticle.slug == art_slug)
                ).scalar_one_or_none()
                if row is not None:
                    if svc and not getattr(row, "linked_service", None):
                        row.linked_service = svc
                        db.add(row)
                    continue
                row = SupportKbArticle(
                    category_id=cat.id,
                    kind="article",
                    title=str(article["title"]),
                    slug=art_slug,
                    body=str(article["body"]),
                    state="published",
                    author="VoxBulk",
                    version=1,
                    views=0,
                    linked_service=svc,
                    created_at=now,
                    updated_at=now,
                )
                db.add(row)
                articles_created += 1
        return cats_created, articles_created

    @staticmethod
    def _seed_help_links(db: Session, existing_keys: set[str]) -> int:
        now = datetime.utcnow()
        created = 0
        for spec in HELP_LINKS:
            if not SupportContentSeedService._should_seed(spec, existing_keys):
                continue
            seed_key = str(spec["seed_key"])
            svc = _norm_svc(spec.get("linked_service"))
            row = db.execute(
                select(SupportHelpLink).where(SupportHelpLink.seed_key == seed_key)
            ).scalar_one_or_none()
            if row is not None:
                if svc and not getattr(row, "linked_service", None):
                    row.linked_service = svc
                    db.add(row)
                continue
            row = SupportHelpLink(
                title=str(spec["title"]),
                url=str(spec["url"]),
                category=str(spec.get("category") or ""),
                description=str(spec.get("description") or ""),
                seed_key=seed_key,
                linked_service=svc,
                is_active=True,
                sort_order=int(spec.get("sort_order") or 0),
                created_at=now,
                updated_at=now,
            )
            db.add(row)
            created += 1
        return created
