from __future__ import annotations

import pytest

from app.core.database import get_sessionmaker
from app.services.platform_catalog_service import PlatformCatalogService


@pytest.fixture()
def db():
    with get_sessionmaker()() as session:
        PlatformCatalogService.ensure_defaults(session)
        yield session


def test_resolve_survey_channel_ai_call(db):
    assert PlatformCatalogService.resolve_survey_channel({"survey_channel": "ai_call"}) == "ai_call"
    assert PlatformCatalogService.resolve_survey_channel({"delivery": "call"}) == "ai_call"
    assert PlatformCatalogService.resolve_survey_channel({"contact_method": "AI phone call"}) == "ai_call"


def test_resolve_survey_channel_whatsapp(db):
    assert PlatformCatalogService.resolve_survey_channel({"survey_channel": "whatsapp"}) == "whatsapp"
    assert PlatformCatalogService.resolve_survey_channel({"contact_method": "WhatsApp"}) == "whatsapp"


def test_resolve_survey_channel_rejects_both(db):
    with pytest.raises(ValueError, match="Mixed survey channels"):
        PlatformCatalogService.resolve_survey_channel({"contact_method": "Both"})
    with pytest.raises(ValueError, match="Mixed survey channels"):
        PlatformCatalogService.resolve_survey_channel({"channels": ["whatsapp", "ai_call"]})


def test_interview_delivery_options_without_zoom(db):
    options = PlatformCatalogService.interview_delivery_options(db)
    assert options == ["ai_call"]
    caps = PlatformCatalogService.interview_platform_capabilities(db)
    assert caps["interview_zoom_enabled"] is False
    assert caps["interview_delivery_options"] == ["ai_call"]
    with pytest.raises(ValueError, match="Zoom interviews are not available"):
        PlatformCatalogService.normalize_interview_delivery(db, "zoom")


def test_interview_delivery_options_with_zoom_enabled(db):
    from app.core.encryption import get_encryptor
    from app.models.provider_config import ProviderConfig

    enc = get_encryptor()
    payload = enc.encrypt_str(
        '{"account_id":"acct","client_id":"cid","client_secret":"secret","base_url":"https://api.zoom.us/v2"}'
    )
    db.add(
        ProviderConfig(
            scope="platform",
            org_id=None,
            provider="zoom",
            is_enabled=True,
            encrypted_json=payload,
        )
    )
    db.commit()

    options = PlatformCatalogService.interview_delivery_options(db)
    assert options == ["ai_call", "zoom"]
    assert PlatformCatalogService.normalize_interview_delivery(db, "zoom") == "zoom"


def test_survey_quote_ai_call_only(db):
    quote = PlatformCatalogService.calculate_quote(
        db,
        service_code="survey",
        recipient_count=100,
        options={"survey_channel": "ai_call"},
    )
    assert quote["survey_channel"] == "ai_call"
    channels = {line.get("channel") for line in quote["lines"]}
    assert "whatsapp" not in channels
    assert quote["total_pence"] > 0
    assert any(line.get("kind") == "bundle" for line in quote["lines"])


def test_survey_quote_whatsapp_only(db):
    quote = PlatformCatalogService.calculate_quote(
        db,
        service_code="survey",
        recipient_count=100,
        options={"survey_channel": "whatsapp"},
    )
    assert quote["survey_channel"] == "whatsapp"
    channels = {line.get("channel") for line in quote["lines"]}
    assert "ai_call" not in channels
    assert "whatsapp" in channels or any("WhatsApp" in (line.get("label") or "") for line in quote["lines"])


def test_survey_quote_overage_when_contacts_exceed_bundle(db):
    svc = PlatformCatalogService.get_service_by_code(db, "survey")
    assert svc is not None
    rules = PlatformCatalogService.list_rules_for_service(db, svc.id)
    hundred = next(
        r for r in rules if r.channel == "ai_call" and r.rule_type == "bundle" and int(r.bundle_size or 0) == 100
    )
    quote = PlatformCatalogService.calculate_quote(
        db,
        service_code="survey",
        recipient_count=150,
        options={"survey_channel": "ai_call", "package_id": hundred.id},
    )
    overage_lines = [line for line in quote["lines"] if line.get("kind") == "overage"]
    assert overage_lines, "Expected overage line when contacts exceed selected bundle"
    assert overage_lines[0]["extra_contacts"] == 50


def test_survey_packages_catalog_shape(db):
    svc = PlatformCatalogService.get_service_by_code(db, "survey")
    assert svc is not None
    catalog = PlatformCatalogService.survey_packages_for_service(db, svc, active_only=True)
    assert "packages" in catalog
    assert len(catalog["packages"]["ai_call"]) >= 1
    assert len(catalog["packages"]["whatsapp"]) >= 1
    pkg = catalog["packages"]["ai_call"][0]
    assert "bundle_size" in pkg
    assert "bundle_price_pence" in pkg
    assert "overage_unit_price_pence" in pkg
