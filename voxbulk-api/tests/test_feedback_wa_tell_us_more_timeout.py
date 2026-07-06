"""Customer Feedback tell-us-more idle timeout (mirrors survey WA pattern)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import select

from app.core.database import Base, get_engine, get_sessionmaker
from app.core.security import hash_password
from app.models.customer_feedback import FeedbackIndustry, FeedbackLocation, FeedbackSession, FeedbackSurveyType
from app.models.organisation import Organisation
from app.models.membership import OrganisationMembership
from app.models.user import User
from app.services.customer_feedback.feedback_wa_idle_timeout_service import (
    process_feedback_tell_us_more_timeouts,
    process_feedback_web_tell_us_more_timeouts,
)
from app.services.customer_feedback.feedback_wa_session_state import set_tell_us_more_pending
from app.services.customer_feedback.seed_service import FeedbackSeedService
from app.services.platform_catalog_service import PlatformCatalogService


@pytest.fixture()
def db():
    import app.models  # noqa: F401

    engine = get_engine()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    SessionLocal = get_sessionmaker()
    session = SessionLocal()
    try:
        PlatformCatalogService.ensure_defaults(session)
        FeedbackSeedService.ensure_seeded(session)
        yield session
    finally:
        session.close()


def _seed_session(db, *, visitor_phone: str = "+447700900111") -> FeedbackSession:
    email = f"fb-{uuid.uuid4().hex[:8]}@example.com"
    org = Organisation(
        name="Feedback Org",
        contact_email=email,
        allowed_services_json='{"customer_feedback": true}',
    )
    db.add(org)
    db.flush()
    user = User(email=email, password_hash=hash_password("pass123"), is_active=True)
    db.add(user)
    db.flush()
    db.add(OrganisationMembership(org_id=org.id, user_id=user.id))
    industry = db.execute(select(FeedbackIndustry).where(FeedbackIndustry.slug == "restaurant")).scalar_one()
    survey_type = db.execute(
        select(FeedbackSurveyType)
        .where(FeedbackSurveyType.industry_id == industry.id)
        .order_by(FeedbackSurveyType.sort_order)
        .limit(1)
    ).scalar_one()
    now = datetime.utcnow()
    location = FeedbackLocation(
        id=str(uuid.uuid4()),
        org_id=org.id,
        industry_id=industry.id,
        survey_type_id=survey_type.id,
        name="Main",
        qr_token=f"test-{uuid.uuid4().hex[:12]}",
        wa_sender_country="gb",
        status="active",
        created_at=now,
        updated_at=now,
    )
    db.add(location)
    session = FeedbackSession(
        id=str(uuid.uuid4()),
        org_id=org.id,
        location_id=location.id,
        visitor_phone=visitor_phone,
        status="active",
        current_step=0,
        detected_language="en",
        started_at=now,
    )
    db.add(session)
    db.commit()
    return session


def test_feedback_wa_tell_us_more_timeout_advances_step(db):
    session = _seed_session(db)
    state = {}
    set_tell_us_more_pending(state, step_index=0, topic_key="service", survey_type_id="st1")
    past = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat().replace("+00:00", "Z")
    state["tell_us_more_deadline"] = past
    session.session_state_json = json.dumps(state)
    db.add(session)
    db.commit()

    with patch(
        "app.services.customer_feedback.feedback_wa_idle_timeout_service.FeedbackWhatsappService._continue_after_step"
    ) as continue_after:
        advanced = process_feedback_tell_us_more_timeouts(db, limit=10)

    assert advanced == 1
    db.refresh(session)
    assert session.current_step == 1
    assert session.session_state_json is None
    continue_after.assert_called_once()


def test_feedback_web_tell_us_more_timeout_advances_step(db):
    session = _seed_session(db, visitor_phone="web:token-abc")
    state = {}
    set_tell_us_more_pending(state, step_index=1, topic_key="cleanliness", survey_type_id="st1")
    past = (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat().replace("+00:00", "Z")
    state["tell_us_more_deadline"] = past
    session.session_state_json = json.dumps(state)
    session.current_step = 1
    db.add(session)
    db.commit()

    advanced = process_feedback_web_tell_us_more_timeouts(db, limit=10)
    assert advanced == 1
    db.refresh(session)
    assert session.current_step == 2
