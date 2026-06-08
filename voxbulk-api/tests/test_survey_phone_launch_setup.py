from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta

import pytest

from app.models.agent import AgentDefinition
from app.models.organisation import Organisation
from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.models.user import User
from app.services.platform_catalog_service import PlatformCatalogService
from app.services.survey_launch_eligibility_service import SurveyLaunchEligibilityService


@pytest.fixture()
def db():
    from app.core.database import Base, get_engine, get_sessionmaker
    import app.models  # noqa: F401

    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    with get_sessionmaker()() as session:
        PlatformCatalogService.ensure_defaults(session)
        yield session


def _phone_order(db, *, config: dict | None = None) -> tuple[Organisation, ServiceOrder]:
    org = Organisation(name="Acme Clinic")
    user = User(email=f"phone-survey-{uuid.uuid4().hex[:8]}@test.com", password_hash="x", is_active=True)
    db.add(org)
    db.add(user)
    db.flush()
    cfg = {
        "survey_channel": "ai_call",
        "delivery": "ai_call",
        "script_approved": True,
        "approved_script": "INTRO\nHi\n\nQUESTIONS\n1. How was your visit?\n\nCLOSING\nThanks",
        "agent_id": "",
    }
    if config:
        cfg.update(config)
    start = datetime.utcnow()
    order = ServiceOrder(
        org_id=org.id,
        user_id=user.id,
        service_code="survey",
        title="Phone survey",
        status="draft",
        config_json=json.dumps(cfg),
        scheduled_start_at=start,
        scheduled_end_at=start + timedelta(hours=4),
        recipient_count=1,
    )
    db.add(order)
    db.flush()
    db.add(
        ServiceOrderRecipient(
            order_id=order.id,
            row_number=1,
            name="Jane",
            phone="+447700900123",
            status="pending",
        )
    )
    db.commit()
    return org, order


def test_phone_survey_setup_error_requires_script_approval(db):
    org, order = _phone_order(db, config={"script_approved": False, "approved_script": ""})
    error = SurveyLaunchEligibilityService._phone_survey_setup_error(db, order, json.loads(order.config_json))
    assert error == "Approve your survey script before launch."


def test_phone_survey_setup_error_requires_agent(db):
    from sqlalchemy import delete

    org, order = _phone_order(db)
    db.execute(delete(AgentDefinition))
    db.commit()
    error = SurveyLaunchEligibilityService._phone_survey_setup_error(db, order, json.loads(order.config_json))
    assert error == "Select a survey voice agent with a Telnyx assistant configured."


def test_phone_survey_setup_ok_with_agent(db):
    org, order = _phone_order(db)
    agent = AgentDefinition(
        name="survey_GB-Amelia",
        slug=f"survey-test-{uuid.uuid4().hex[:6]}",
        system_prompt="Survey caller",
        telnyx_assistant_id="assistant-test-123",
        supports_survey=True,
        is_active=True,
    )
    db.add(agent)
    db.flush()
    cfg = json.loads(order.config_json)
    cfg["agent_id"] = agent.id
    order.config_json = json.dumps(cfg)
    db.commit()
    error = SurveyLaunchEligibilityService._phone_survey_setup_error(db, order, cfg)
    assert error is None
