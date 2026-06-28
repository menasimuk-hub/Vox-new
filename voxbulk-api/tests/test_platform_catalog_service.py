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


def test_interview_delivery_options(db):
    options = PlatformCatalogService.interview_delivery_options(db)
    assert options == ["ai_call", "ai_meeting"]
    caps = PlatformCatalogService.interview_platform_capabilities(db)
    assert caps["interview_meeting_enabled"] is True
    assert caps["interview_delivery_options"] == ["ai_call", "ai_meeting"]
    assert PlatformCatalogService.normalize_interview_delivery(db, "ai_meeting") == "ai_meeting"
