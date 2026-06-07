"""Survey package selection must tolerate stale package_id from another channel."""

from __future__ import annotations

import pytest

from app.services.platform_catalog_service import PlatformCatalogService


def test_pick_survey_bundle_ignores_wrong_channel_package(db):
    from app.models.platform_service import PlatformService, ServicePricingRule

    PlatformCatalogService.ensure_defaults(db)
    svc = PlatformCatalogService.get_service_by_code(db, "survey")
    assert svc is not None

    ai_rule = ServicePricingRule(
        service_id=svc.id,
        channel="ai_call",
        rule_type="bundle",
        label="AI call 50",
        bundle_size=50,
        bundle_price_pence=5000,
        is_active=True,
    )
    wa_rule = ServicePricingRule(
        service_id=svc.id,
        channel="whatsapp",
        rule_type="bundle",
        label="WhatsApp 50",
        bundle_size=50,
        bundle_price_pence=4000,
        is_active=True,
    )
    db.add(ai_rule)
    db.add(wa_rule)
    db.commit()
    db.refresh(ai_rule)
    db.refresh(wa_rule)

    rules = PlatformCatalogService.list_rules_for_service(db, svc.id)
    picked = PlatformCatalogService._pick_survey_bundle_rule(
        rules,
        channel="whatsapp",
        recipient_count=2,
        selected_rule_id=str(ai_rule.id),
    )
    assert str(picked.id) != str(ai_rule.id)
    assert PlatformCatalogService.normalize_survey_channel(picked.channel) == "whatsapp"


def test_calculate_quote_whatsapp_with_stale_ai_package_id(db):
    from app.models.platform_service import PlatformService, ServicePricingRule

    PlatformCatalogService.ensure_defaults(db)
    svc = PlatformCatalogService.get_service_by_code(db, "survey")
    assert svc is not None

    ai_rule = ServicePricingRule(
        service_id=svc.id,
        channel="ai_call",
        rule_type="bundle",
        label="AI call 50",
        bundle_size=50,
        bundle_price_pence=5000,
        is_active=True,
    )
    wa_rule = ServicePricingRule(
        service_id=svc.id,
        channel="whatsapp",
        rule_type="bundle",
        label="WhatsApp 50",
        bundle_size=50,
        bundle_price_pence=4000,
        is_active=True,
    )
    db.add(ai_rule)
    db.add(wa_rule)
    db.commit()

    quote = PlatformCatalogService.calculate_quote(
        db,
        service_code="survey",
        recipient_count=2,
        options={"delivery": "whatsapp", "package_id": str(ai_rule.id)},
    )
    assert quote["survey_channel"] == "whatsapp"
    assert str(quote["selected_package_id"]) != str(ai_rule.id)


@pytest.fixture()
def db():
    from app.core.database import Base, get_engine, get_sessionmaker
    import app.models  # noqa: F401

    engine = get_engine()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    SessionLocal = get_sessionmaker()
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
