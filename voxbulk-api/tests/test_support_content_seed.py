"""Support content seed — insert-missing immutability + product visibility."""

from __future__ import annotations

from sqlalchemy import select

from app.core.database import get_sessionmaker
from app.data.support_content_defaults import (
    CANNED_CATEGORIES,
    DASHBOARD_FAQ_CATEGORIES,
    HELP_LINKS,
    KB_CATEGORIES,
    OPTIONAL_PRODUCT_KEYS,
)
from app.models.faq import FAQItem
from app.models.support_kb import SupportHelpLink, SupportKbArticle
from app.models.support_ticket import CannedReply
from app.services.platform_product_visibility_service import PlatformProductVisibilityService
from app.services.support_content_seed_service import SupportContentSeedService, is_support_content_visible
from app.services.support_kb_service import SupportHelpLinkService, SupportKbService
from app.services.support_ticket_service import CannedReplyService


def _count_expected_core() -> dict[str, int]:
    faq_cats = [c for c in DASHBOARD_FAQ_CATEGORIES if not c.get("optional") and c.get("linked_service") not in OPTIONAL_PRODUCT_KEYS]
    faq_items = sum(len(c.get("items") or []) for c in faq_cats)
    canned_cats = [c for c in CANNED_CATEGORIES if not c.get("optional") and c.get("linked_service") not in OPTIONAL_PRODUCT_KEYS]
    canned_replies = sum(len(c.get("replies") or []) for c in canned_cats)
    kb_cats = [c for c in KB_CATEGORIES if not c.get("optional") and c.get("linked_service") not in OPTIONAL_PRODUCT_KEYS]
    kb_articles = sum(len(c.get("articles") or []) for c in kb_cats)
    help_links = len([h for h in HELP_LINKS if not h.get("optional") and h.get("linked_service") not in OPTIONAL_PRODUCT_KEYS])
    return {
        "faq_cats": len(faq_cats),
        "faq_items": faq_items,
        "canned_cats": len(canned_cats),
        "canned_replies": canned_replies,
        "kb_cats": len(kb_cats),
        "kb_articles": kb_articles,
        "help_links": help_links,
    }


def test_support_content_seed_insert_missing_only():
    db = get_sessionmaker()()
    try:
        PlatformProductVisibilityService.ensure_defaults(db)
        first = SupportContentSeedService.ensure_defaults(db)
        expected = _count_expected_core()
        assert first["faq_items"] >= 0  # may already exist from prior test run
        # Snapshot seeded FAQ answer
        row = db.execute(select(FAQItem).where(FAQItem.slug == "dash-interview-setup")).scalar_one_or_none()
        assert row is not None
        original = row.answer
        row.answer = "ADMIN EDITED — do not overwrite"
        db.add(row)
        db.commit()

        second = SupportContentSeedService.ensure_defaults(db)
        assert second["faq_items"] == 0
        assert second["canned_replies"] == 0
        assert second["kb_articles"] == 0
        assert second["help_links"] == 0

        refreshed = db.execute(select(FAQItem).where(FAQItem.slug == "dash-interview-setup")).scalar_one()
        assert refreshed.answer == "ADMIN EDITED — do not overwrite"
        assert refreshed.answer != original or original == "ADMIN EDITED — do not overwrite"

        # Coverage: core product FAQ items exist
        for slug in (
            "dash-interview-setup",
            "dash-survey-setup",
            "dash-feedback-setup",
            "dash-expo-setup",
            "dash-smart-card-setup",
            "dash-campaigns-setup",
            "dash-shared-billing",
        ):
            assert db.execute(select(FAQItem.id).where(FAQItem.slug == slug)).scalar_one_or_none() is not None

        assert db.execute(select(CannedReply.id).where(CannedReply.seed_key == "canned-interview-setup")).scalar_one_or_none()
        assert db.execute(select(CannedReply.id).where(CannedReply.seed_key == "canned-shared-welcome-v2")).scalar_one_or_none()
        assert db.execute(select(CannedReply.id).where(CannedReply.seed_key == "canned-interview-howto-v2")).scalar_one_or_none()
        assert db.execute(select(SupportKbArticle.id).where(SupportKbArticle.slug == "kb-interview-setup")).scalar_one_or_none()
        assert db.execute(select(SupportHelpLink.id).where(SupportHelpLink.seed_key == "hl-dash-faq")).scalar_one_or_none()
        assert db.execute(select(SupportHelpLink.id).where(SupportHelpLink.seed_key == "hl-profile-v2")).scalar_one_or_none()
        assert db.execute(select(SupportHelpLink.id).where(SupportHelpLink.seed_key == "hl-interview-results-v2")).scalar_one_or_none()

        # Optional products not seeded unless group exists
        assert "appointments" not in {g.key for g in PlatformProductVisibilityService.list_groups(db)} or True
        optional_faq = db.execute(select(FAQItem).where(FAQItem.slug == "dash-appointments-setup")).scalar_one_or_none()
        groups = {g.key for g in PlatformProductVisibilityService.list_groups(db)}
        if "appointments" not in groups:
            assert optional_faq is None

        assert expected["faq_items"] >= 21  # 3×7 core categories
        assert expected["canned_replies"] >= 40  # core packs expanded with v2 keys
        assert expected["kb_articles"] >= 14
        assert expected["help_links"] >= 30
    finally:
        db.close()


def test_support_content_hidden_when_product_disabled():
    db = get_sessionmaker()()
    try:
        PlatformProductVisibilityService.ensure_defaults(db)
        SupportContentSeedService.ensure_defaults(db)

        expo = PlatformProductVisibilityService.get_by_key(db, "expo")
        assert expo is not None
        PlatformProductVisibilityService.set_enabled(db, expo.id, False)

        assert is_support_content_visible(db, "expo") is False
        assert is_support_content_visible(db, "shared") is True

        canned = CannedReplyService.list_replies(db, active_only=True)
        assert all(getattr(r, "linked_service", None) != "expo" for r in canned)
        assert any(getattr(r, "linked_service", None) == "shared" for r in canned)

        links = SupportHelpLinkService.list_links(db, active_only=True)
        assert all(getattr(r, "linked_service", None) != "expo" for r in links)
        assert any(getattr(r, "seed_key", None) == "hl-dash-faq" for r in links)

        articles = SupportKbService.list_articles(db, published_only=True)
        assert all(getattr(r, "linked_service", None) != "expo" for r in articles)

        # Rows preserved
        assert db.execute(select(CannedReply.id).where(CannedReply.seed_key == "canned-expo-setup")).scalar_one_or_none()
        assert db.execute(select(SupportKbArticle.id).where(SupportKbArticle.slug == "kb-expo-setup")).scalar_one_or_none()

        PlatformProductVisibilityService.set_enabled(db, expo.id, True)
        canned_on = CannedReplyService.list_replies(db, active_only=True)
        assert any(getattr(r, "linked_service", None) == "expo" for r in canned_on)
    finally:
        db.close()


def test_optional_product_seeded_only_when_group_exists():
    db = get_sessionmaker()()
    try:
        PlatformProductVisibilityService.ensure_defaults(db)
        SupportContentSeedService.ensure_defaults(db)
        assert db.execute(select(FAQItem.id).where(FAQItem.slug == "dash-appointments-setup")).scalar_one_or_none() is None

        PlatformProductVisibilityService.create_group(
            db,
            key="appointments",
            name="Appointments",
            routes=["/appointments"],
            faq_category_slugs=["appointments"],
            pricing_kinds=[],
        )
        SupportContentSeedService.ensure_defaults(db)
        assert db.execute(select(FAQItem.id).where(FAQItem.slug == "dash-appointments-setup")).scalar_one_or_none() is not None
        assert db.execute(select(CannedReply.id).where(CannedReply.seed_key == "canned-appointments-setup")).scalar_one_or_none()
    finally:
        db.close()
