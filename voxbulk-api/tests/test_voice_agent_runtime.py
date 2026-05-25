from __future__ import annotations

import uuid
from datetime import datetime

import pytest

from app.core.database import get_sessionmaker
from app.models.agent import AgentDefinition
from app.models.voice_agent_platform_settings import VoiceAgentPlatformSettings
from app.services.platform_catalog_service import PlatformCatalogService
from app.services.survey_voice_agent_service import build_survey_runtime_instructions
from app.services.voice_agent_runtime import (
    build_script_generation_agent_block,
    build_voice_runtime_layers,
    disclosure_mandatory,
    resolve_opening_disclosure_template,
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


def _agent(**kwargs) -> AgentDefinition:
    defaults = dict(
        name="Sophie",
        slug=f"sophie-{uuid.uuid4().hex[:8]}",
        system_prompt="Be warm and concise.",
        is_active=True,
        supports_survey=True,
        disclosure_for_survey=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    defaults.update(kwargs)
    return AgentDefinition(**defaults)


def test_runtime_includes_call_workflow_in_instructions(db):
    agent = _agent(
        call_workflow="Ask if they have time now before starting the survey questions.",
        opening_disclosure_template="Hello, this is {agent_name} calling from {company_name}. This call is recorded.",
        service_survey_role="Run anonymous phone surveys politely.",
    )
    db.add(agent)
    db.commit()

    from app.models.service_order import ServiceOrder, ServiceOrderRecipient

    order = ServiceOrder(
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
        name="Jane Doe",
        phone="+441234567890",
        status="pending",
        result_json="{}",
        created_at=datetime.utcnow(),
    )
    db.add(recipient)
    db.commit()

    config = {
        "organisation_name": "Acme Clinic",
        "goal": "Satisfaction",
        "approved_script": "INTRO\nThanks for your time.\n\nQUESTIONS\n1. How was your visit?\n\nCLOSING\nThank you.",
        "system_prompt": "Campaign note: focus on booking experience.",
    }
    text = build_survey_runtime_instructions(db, order=order, config=config, recipient=recipient, agent=agent)
    assert "have time now" in text.lower()
    assert "Call workflow" in text
    assert "Campaign notes" in text
    assert "already been spoken" in text.lower()


def test_script_generation_block_includes_disclosure_and_workflow(db):
    agent = _agent(
        opening_disclosure_template="Hi, I am {agent_name} from {company_name}. Recorded line.",
        call_workflow="1. Ask if now is a good time.\n2. If yes, ask survey questions.",
    )
    db.add(agent)
    db.commit()

    block = build_script_generation_agent_block(
        db,
        agent=agent,
        config={"organisation_name": "Acme Clinic"},
        service_key="survey",
    )
    assert "OPENING DISCLOSURE" in block
    assert "Call workflow" in block
    assert "good time" in block.lower()


def test_opening_disclosure_respects_platform_survey_toggle(db):
    from app.services.survey_voice_agent_service import get_platform_voice_settings

    platform = get_platform_voice_settings(db)
    platform.disclosure_for_survey = False
    db.add(platform)
    db.commit()

    agent = _agent(opening_disclosure_template="Should not be used when platform disabled.")
    text = resolve_opening_disclosure_template(
        db,
        agent=agent,
        config={"organisation_name": "Acme"},
        service_key="survey",
    )
    assert text == ""


def test_layers_merge_campaign_system_prompt(db):
    agent = _agent(service_survey_role="Survey specialist.")
    layers = build_voice_runtime_layers(
        db,
        agent=agent,
        config={"system_prompt": "Mention parking."},
        service_key="survey",
    )
    assert layers.service_role == "Survey specialist."
    assert layers.campaign_system_prompt == "Mention parking."


def test_mandatory_disclosure_uses_default_when_templates_empty(db):
    from app.services.survey_voice_agent_service import get_platform_voice_settings

    platform = get_platform_voice_settings(db)
    platform.disclosure_mandatory = True
    platform.opening_disclosure_template = ""
    db.add(platform)
    db.commit()

    agent = _agent(opening_disclosure_template="", disclosure_mandatory=True)
    text = resolve_opening_disclosure_template(
        db,
        agent=agent,
        config={"organisation_name": "Acme"},
        service_key="survey",
    )
    assert text.strip()
    assert "AI assistant" in text or "Acme" in text


def test_mandatory_disclosure_respects_agent_opt_out(db):
    from app.services.survey_voice_agent_service import get_platform_voice_settings

    platform = get_platform_voice_settings(db)
    platform.disclosure_mandatory = True
    db.add(platform)
    db.commit()

    agent = _agent(disclosure_mandatory=False)
    assert disclosure_mandatory(platform, agent) is False


def test_script_block_notes_mandatory_disclosure(db):
    from app.services.survey_voice_agent_service import get_platform_voice_settings

    platform = get_platform_voice_settings(db)
    platform.disclosure_mandatory = True
    db.add(platform)
    db.commit()

    agent = _agent(
        opening_disclosure_template="Hi, I am {agent_name} from {company_name}. Recorded line.",
        disclosure_mandatory=True,
    )
    db.add(agent)
    db.commit()

    block = build_script_generation_agent_block(
        db,
        agent=agent,
        config={"organisation_name": "Acme Clinic"},
        service_key="survey",
    )
    assert "mandatory" in block.lower()
