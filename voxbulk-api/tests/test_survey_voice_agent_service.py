from __future__ import annotations

import json
import uuid
from datetime import datetime

import pytest

from app.core.database import get_sessionmaker
from app.models.agent import AgentDefinition
from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.models.voice_agent_platform_settings import DEFAULT_OPENING_DISCLOSURE, VoiceAgentPlatformSettings
from app.services.platform_catalog_service import PlatformCatalogService
from app.services.survey_voice_agent_service import (
    build_opening_disclosure,
    clear_survey_generated_script_on_launch,
    detect_opt_out_text,
    mark_recipient_opted_out,
    resolve_survey_agent_for_order,
    schedule_recipient_retry,
    should_skip_recipient_for_opt_out,
    should_wait_for_retry,
)


@pytest.fixture()
def db():
    from app.core.database import Base, get_engine
    import app.models  # noqa: F401

    engine = get_engine()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with get_sessionmaker()() as session:
        PlatformCatalogService.ensure_defaults(session)
        yield session


def test_detect_opt_out_text():
    assert detect_opt_out_text("Please remove me from your list") is True
    assert detect_opt_out_text("stop calling me") is True
    assert detect_opt_out_text("Yes I am happy to answer") is False


def test_clear_survey_generated_script_on_launch():
    config = {
        "approved_script": "Hello survey",
        "generated_script_draft": "draft only",
        "generated_script_at": "2026-01-01T00:00:00",
    }
    cleaned = clear_survey_generated_script_on_launch(config)
    assert cleaned["approved_script"] == "Hello survey"
    assert "generated_script_draft" not in cleaned
    assert "generated_script_at" not in cleaned


def test_resolve_survey_agent_prefers_order_config(db):
    agent = AgentDefinition(
        name="Sophie",
        slug=f"sophie-{uuid.uuid4().hex[:8]}",
        system_prompt="test",
        is_active=True,
        supports_survey=True,
        telnyx_assistant_id="asst_sophie",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    other = AgentDefinition(
        name="James",
        slug=f"james-{uuid.uuid4().hex[:8]}",
        system_prompt="test",
        is_active=True,
        supports_survey=True,
        is_default_survey=True,
        telnyx_assistant_id="asst_james",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add_all([agent, other])
    db.commit()

    order = ServiceOrder(
        org_id="org-1",
        user_id="user-1",
        service_code="survey",
        title="Test",
        config_json="{}",
        status="scheduled",
        payment_status="approved",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(order)
    db.commit()

    resolved = resolve_survey_agent_for_order(db, order, {"agent_id": agent.id})
    assert resolved is not None
    assert resolved.id == agent.id


def test_build_opening_disclosure_uses_platform_template(db):
    existing = db.get(VoiceAgentPlatformSettings, "default")
    if existing is None:
        db.add(
            VoiceAgentPlatformSettings(
                id="default",
                opening_disclosure_template=DEFAULT_OPENING_DISCLOSURE,
                disclosure_mandatory=True,
                disclosure_for_survey=True,
                disclosure_for_interview=True,
                updated_at=datetime.utcnow(),
            )
        )
        db.commit()

    agent = AgentDefinition(
        name="Sophie Agent",
        slug=f"sophie-agent-{uuid.uuid4().hex[:8]}",
        system_prompt="test",
        voice_label="Sophie",
        is_active=True,
        supports_survey=True,
        disclosure_for_survey=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    text = build_opening_disclosure(
        db,
        agent=agent,
        config={"organisation_name": "Acme Clinic"},
        service_key="survey",
    )
    assert "Sophie" in text
    assert "AI assistant" not in text
    assert "Acme Clinic" in text
    assert "recorded" in text.lower()


def test_opt_out_and_retry_recipient(db):
    order = ServiceOrder(
        id=str(uuid.uuid4()),
        org_id="org-1",
        user_id="user-1",
        service_code="survey",
        title="Test",
        config_json="{}",
        status="running",
        payment_status="approved",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(order)
    db.commit()

    recipient = ServiceOrderRecipient(
        order_id=order.id,
        name="Jane",
        phone="+441234567890",
        status="pending",
        result_json="{}",
        created_at=datetime.utcnow(),
    )
    db.add(recipient)
    db.commit()

    mark_recipient_opted_out(db, recipient, source_text="remove me please")
    db.refresh(recipient)
    assert recipient.status == "opted_out"
    assert should_skip_recipient_for_opt_out(recipient) is True

    recipient2 = ServiceOrderRecipient(
        order_id=order.id,
        name="Bob",
        phone="+441234567891",
        status="no_answer",
        result_json="{}",
        created_at=datetime.utcnow(),
    )
    db.add(recipient2)
    db.commit()

    schedule_recipient_retry(db, recipient2, delay_seconds=3600)
    db.refresh(recipient2)
    assert recipient2.status == "pending"
    assert should_wait_for_retry(recipient2) is True
    result = json.loads(recipient2.result_json or "{}")
    assert result.get("retry_count") == 1
