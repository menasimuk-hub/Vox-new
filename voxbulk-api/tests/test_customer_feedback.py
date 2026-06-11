"""Tests for Customer Feedback service."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.core.database import get_sessionmaker
from app.core.security import hash_password
from app.models.customer_feedback import FeedbackIndustry, FeedbackSurveyType
from app.models.membership import OrganisationMembership
from app.models.organisation import Organisation
from app.models.user import User
from app.services.customer_feedback.catalog_service import FeedbackCatalogService
from app.services.customer_feedback.location_service import FeedbackLocationService, TRIGGER_TEMPLATE
from app.services.customer_feedback.seed_service import FeedbackSeedService


@pytest.fixture(scope="module", autouse=True)
def _prepare_db():
    from app.core.database import Base, get_engine
    import app.models  # noqa: F401

    Base.metadata.create_all(bind=get_engine())


def _seed_org() -> tuple[str, str]:
    with get_sessionmaker()() as db:
        email = f"fb-{uuid.uuid4().hex[:8]}@example.com"
        org = Organisation(name="Feedback Org", contact_email=email, allowed_services_json='{"customer_feedback": true}')
        db.add(org)
        db.flush()
        user = User(email=email, password_hash=hash_password("pass123"), is_active=True)
        db.add(user)
        db.flush()
        db.add(OrganisationMembership(org_id=org.id, user_id=user.id))
        db.commit()
        return org.id, user.id


def test_seed_industries_and_survey_types():
    with get_sessionmaker()() as db:
        FeedbackSeedService.ensure_seeded(db)
        industries = FeedbackCatalogService.list_industries(db, include_inactive=True)
        assert len(industries) >= 5
        restaurant = db.execute(select(FeedbackIndustry).where(FeedbackIndustry.slug == "restaurant")).scalar_one()
        types = FeedbackCatalogService.list_survey_types(db, industry_id=restaurant.id)
        assert len(types) >= 15


def test_parse_trigger_ref():
    token = FeedbackLocationService.parse_trigger_ref('Hello [ref:abc123-token]')
    assert token == "abc123-token"


def test_trigger_template_format():
    text = TRIGGER_TEMPLATE.format(company="Acme Ltd", branch="Marylebone", token="tok1")
    assert "Acme Ltd" in text
    assert "[ref:tok1]" in text
