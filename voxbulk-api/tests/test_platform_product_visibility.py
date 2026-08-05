"""Platform product visibility registry — catalogue gating (not org grants)."""

from __future__ import annotations

from app.core.database import get_sessionmaker
from app.services.platform_product_visibility_service import (
    PlatformProductVisibilityError,
    PlatformProductVisibilityService,
)
from app.services.site_seo_service import STATIC_SITEMAP_PATHS, build_sitemap_entries


def test_ensure_defaults_backfills_enabled_groups():
    db = get_sessionmaker()()
    try:
        groups = PlatformProductVisibilityService.ensure_defaults(db)
        keys = {g.key for g in groups}
        assert {
            "interview",
            "survey",
            "customer_feedback",
            "expo",
            "smart_card",
            "campaigns",
            "shared",
        }.issubset(keys)
        assert all(g.enabled or g.always_visible for g in groups)
        shared = next(g for g in groups if g.key == "shared")
        assert shared.always_visible is True
    finally:
        db.close()


def test_disable_product_hides_route_and_faq_keeps_shared():
    db = get_sessionmaker()()
    try:
        PlatformProductVisibilityService.ensure_defaults(db)
        expo = PlatformProductVisibilityService.get_by_key(db, "expo")
        assert expo is not None
        PlatformProductVisibilityService.set_enabled(db, expo.id, False)

        assert PlatformProductVisibilityService.is_route_enabled(db, "/expo") is False
        assert PlatformProductVisibilityService.is_route_enabled(db, "/recruitment") is True
        assert PlatformProductVisibilityService.is_faq_visible(db, category_slug="expo") is False
        assert PlatformProductVisibilityService.is_faq_visible(db, category_slug="billing") is True
        assert PlatformProductVisibilityService.is_faq_visible(db, linked_service="shared") is True
        assert "/expo" in PlatformProductVisibilityService.disabled_routes(db)

        payload = PlatformProductVisibilityService.public_payload(db)
        assert "expo" not in payload["enabled_keys"]
        assert "/expo" in payload["disabled_routes"]
    finally:
        db.close()


def test_core_pricing_visible_until_both_interview_and_survey_disabled():
    db = get_sessionmaker()()
    try:
        PlatformProductVisibilityService.ensure_defaults(db)
        interview = PlatformProductVisibilityService.get_by_key(db, "interview")
        survey = PlatformProductVisibilityService.get_by_key(db, "survey")
        assert interview and survey

        PlatformProductVisibilityService.set_enabled(db, interview.id, False)
        assert PlatformProductVisibilityService.is_pricing_kind_enabled(db, "core") is True
        assert PlatformProductVisibilityService.is_route_enabled(db, "/recruitment") is False
        assert PlatformProductVisibilityService.is_route_enabled(db, "/surveys") is True

        PlatformProductVisibilityService.set_enabled(db, survey.id, False)
        assert PlatformProductVisibilityService.is_pricing_kind_enabled(db, "core") is False
    finally:
        db.close()


def test_shared_group_cannot_be_disabled():
    db = get_sessionmaker()()
    try:
        PlatformProductVisibilityService.ensure_defaults(db)
        shared = PlatformProductVisibilityService.get_by_key(db, "shared")
        assert shared is not None
        try:
            PlatformProductVisibilityService.set_enabled(db, shared.id, False)
            assert False, "expected PlatformProductVisibilityError"
        except PlatformProductVisibilityError as exc:
            assert "cannot be disabled" in str(exc).lower()
    finally:
        db.close()


def test_create_group_requires_bindings_and_defaults_enabled():
    db = get_sessionmaker()()
    try:
        PlatformProductVisibilityService.ensure_defaults(db)
        try:
            PlatformProductVisibilityService.create_group(
                db, key="empty_demo", name="Empty Demo", routes=[], faq_category_slugs=[], pricing_kinds=[]
            )
            assert False, "expected validation error"
        except PlatformProductVisibilityError:
            pass

        row = PlatformProductVisibilityService.create_group(
            db,
            key="appointments_demo",
            name="Appointments Demo",
            routes=["/appointments"],
            faq_category_slugs=["appointments"],
            pricing_kinds=[],
        )
        assert row.enabled is True
        assert PlatformProductVisibilityService.is_route_enabled(db, "/appointments") is True
    finally:
        db.close()


def test_sitemap_omits_disabled_product_routes(app_client):
    db = get_sessionmaker()()
    try:
        PlatformProductVisibilityService.ensure_defaults(db)
        fb = PlatformProductVisibilityService.get_by_key(db, "customer_feedback")
        assert fb is not None
        PlatformProductVisibilityService.set_enabled(db, fb.id, False)

        filtered = PlatformProductVisibilityService.filter_static_sitemap_paths(db, list(STATIC_SITEMAP_PATHS))
        assert "/feedback" not in filtered
        assert "/recruitment" in filtered

        entries = build_sitemap_entries(db)
        paths = {e["path"] for e in entries}
        assert "/feedback" not in paths
        assert "/recruitment" in paths
        PlatformProductVisibilityService.set_enabled(db, fb.id, True)
    finally:
        db.close()


def test_public_product_visibility_endpoint(app_client):
    res = app_client.get("/frontpage/product-visibility")
    assert res.status_code == 200
    body = res.json()
    assert "enabled_keys" in body
    assert "enabled_routes" in body
    assert "enabled_pricing_kinds" in body
    assert "interview" in body["enabled_keys"]
    assert "shared" in body["enabled_keys"]
    assert "core" in body["enabled_pricing_kinds"]
