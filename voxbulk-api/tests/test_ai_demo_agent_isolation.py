"""Dedicated AI Demo agents vs interview/survey roster isolation."""

from __future__ import annotations

import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.core.agent_services import SERVICE_AI_DEMO, SERVICE_FEEDBACK_FOLLOWUP, SERVICE_INTERVIEW, SERVICE_SURVEY
from app.services.ai_demo_service import AiDemoError, AiDemoService, _is_ai_demo_agent
from app.services.survey_voice_agent_service import _service_support_field, list_agents_for_service


@pytest.fixture()
def db_session():
    from app.core.database import Base, get_engine, get_sessionmaker
    import app.models  # noqa: F401

    engine = get_engine()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    session = get_sessionmaker()()
    try:
        yield session
    finally:
        session.close()


def test_is_ai_demo_agent_by_flag_and_name():
    assert _is_ai_demo_agent(SimpleNamespace(supports_ai_demo=True, slug="x", name="Leo"))
    assert _is_ai_demo_agent(SimpleNamespace(supports_ai_demo=False, slug="ai-demo-leo-gb", name="Leo"))
    assert _is_ai_demo_agent(SimpleNamespace(supports_ai_demo=False, slug="leo", name="AI Demo — Leo"))
    assert not _is_ai_demo_agent(SimpleNamespace(supports_ai_demo=False, slug="leo-gb", name="Leo"))
    assert not _is_ai_demo_agent(None)


def test_feedback_followup_shares_survey_support_field():
    assert _service_support_field(SERVICE_SURVEY) == "supports_survey"
    assert _service_support_field(SERVICE_FEEDBACK_FOLLOWUP) == "supports_survey"
    assert _service_support_field(SERVICE_INTERVIEW) == "supports_interview"
    assert _service_support_field(SERVICE_AI_DEMO) == "supports_ai_demo"


def test_list_voice_agents_returns_only_demo(db_session: Session):
    from app.models.agent import AgentDefinition

    interview = AgentDefinition(
        id=str(uuid4()),
        name="Leo Interview",
        slug=f"leo-interview-{uuid4().hex[:8]}",
        system_prompt="Interview",
        is_active=True,
        supports_interview=True,
        supports_ai_demo=False,
        telnyx_assistant_id=f"asst_interview_{uuid4().hex[:8]}",
        accent_region="GB",
    )
    demo = AgentDefinition(
        id=str(uuid4()),
        name="AI Demo — Leo",
        slug=f"ai-demo-leo-{uuid4().hex[:8]}",
        system_prompt="Demo",
        is_active=True,
        supports_interview=False,
        supports_survey=False,
        supports_ai_demo=True,
        telnyx_assistant_id=f"asst_demo_{uuid4().hex[:8]}",
        accent_region="GB",
    )
    survey = AgentDefinition(
        id=str(uuid4()),
        name="Survey Leo",
        slug=f"survey-leo-{uuid4().hex[:8]}",
        system_prompt="Survey",
        is_active=True,
        supports_survey=True,
        supports_ai_demo=False,
        telnyx_assistant_id=f"asst_survey_{uuid4().hex[:8]}",
        accent_region="GB",
    )
    db_session.add_all([interview, demo, survey])
    db_session.commit()

    items = AiDemoService.list_voice_agents(db_session)
    ids = {i["id"] for i in items}
    assert demo.id in ids
    assert interview.id not in ids
    assert survey.id not in ids


def test_list_agents_for_service_isolates_rosters(db_session: Session):
    from app.models.agent import AgentDefinition

    interview = AgentDefinition(
        id=str(uuid4()),
        name="Interview Only",
        slug=f"interview-only-{uuid4().hex[:8]}",
        system_prompt="i",
        is_active=True,
        supports_interview=True,
        supports_ai_demo=False,
        telnyx_assistant_id=f"asst_i_{uuid4().hex[:8]}",
    )
    survey = AgentDefinition(
        id=str(uuid4()),
        name="Survey Followback",
        slug=f"survey-fb-{uuid4().hex[:8]}",
        system_prompt="s",
        is_active=True,
        supports_survey=True,
        supports_ai_demo=False,
        telnyx_assistant_id=f"asst_s_{uuid4().hex[:8]}",
    )
    demo = AgentDefinition(
        id=str(uuid4()),
        name="AI Demo Only",
        slug=f"ai-demo-only-{uuid4().hex[:8]}",
        system_prompt="d",
        is_active=True,
        supports_ai_demo=True,
        supports_interview=False,
        supports_survey=False,
        telnyx_assistant_id=f"asst_d_{uuid4().hex[:8]}",
    )
    leaky = AgentDefinition(
        id=str(uuid4()),
        name="Leaky Demo",
        slug=f"leaky-{uuid4().hex[:8]}",
        system_prompt="x",
        is_active=True,
        supports_ai_demo=True,
        supports_interview=True,
        telnyx_assistant_id=f"asst_l_{uuid4().hex[:8]}",
    )
    db_session.add_all([interview, survey, demo, leaky])
    db_session.commit()

    interview_ids = {a.id for a in list_agents_for_service(db_session, service_key=SERVICE_INTERVIEW)}
    survey_ids = {a.id for a in list_agents_for_service(db_session, service_key=SERVICE_SURVEY)}
    follow_ids = {a.id for a in list_agents_for_service(db_session, service_key=SERVICE_FEEDBACK_FOLLOWUP)}
    demo_ids = {a.id for a in list_agents_for_service(db_session, service_key=SERVICE_AI_DEMO)}

    assert interview.id in interview_ids
    assert leaky.id not in interview_ids
    assert demo.id not in interview_ids
    assert survey.id in survey_ids
    assert survey.id in follow_ids
    assert demo.id in demo_ids
    assert interview.id not in demo_ids


def test_resolve_assistant_skips_interview_mapping(db_session: Session):
    from app.models.agent import AgentDefinition
    from app.models.demo_request import DemoRequest

    interview = AgentDefinition(
        id=str(uuid4()),
        name="Interview Leo",
        slug=f"int-leo-{uuid4().hex[:8]}",
        system_prompt="i",
        is_active=True,
        supports_interview=True,
        supports_ai_demo=False,
        telnyx_assistant_id=f"asst_int_{uuid4().hex[:8]}",
        accent_region="GB",
    )
    demo = AgentDefinition(
        id=str(uuid4()),
        name="AI Demo — Leo",
        slug=f"ai-demo-leo-{uuid4().hex[:8]}",
        system_prompt="d",
        is_active=True,
        supports_ai_demo=True,
        telnyx_assistant_id=f"asst_demo_{uuid4().hex[:8]}",
        accent_region="GB",
    )
    db_session.add_all([interview, demo])
    db_session.commit()

    settings = AiDemoService.get_settings(db_session)
    settings.agent_by_region_json = json.dumps({"GB": interview.id, "DEFAULT": demo.id})
    db_session.add(settings)
    db_session.commit()

    req = DemoRequest(
        id=str(uuid4()),
        contact_name="Test",
        email=f"t-{uuid4().hex[:8]}@example.com",
        company_name="Co",
        website="https://voxbulk.com",
        preferred_language="en",
        whatsapp_e164="+447700900123",
        status="approved",
    )
    db_session.add(req)
    db_session.commit()

    out = AiDemoService.resolve_assistant_for_request(db_session, req)
    assert out["assistant_id"] == demo.telnyx_assistant_id
    assert out["agent_id"] == demo.id
    assert out["source"] == "region:DEFAULT"


def test_update_settings_rejects_non_demo_agent(db_session: Session):
    from app.models.agent import AgentDefinition

    interview = AgentDefinition(
        id=str(uuid4()),
        name="Interview",
        slug=f"int-{uuid4().hex[:8]}",
        system_prompt="i",
        is_active=True,
        supports_interview=True,
        telnyx_assistant_id=f"asst_{uuid4().hex[:8]}",
    )
    db_session.add(interview)
    db_session.commit()
    AiDemoService.get_settings(db_session)

    with pytest.raises(AiDemoError, match="dedicated AI Demo"):
        AiDemoService.update_settings(db_session, {"agent_by_region": {"GB": interview.id}})


def test_interview_sources_by_region_skips_demo(db_session: Session):
    from app.models.agent import AgentDefinition

    interview = AgentDefinition(
        id=str(uuid4()),
        name="Interview GB",
        slug=f"int-gb-{uuid4().hex[:8]}",
        system_prompt="i",
        is_active=True,
        supports_interview=True,
        supports_ai_demo=False,
        telnyx_assistant_id=f"asst_igb_{uuid4().hex[:8]}",
        accent_region="GB",
        is_default_interview=True,
    )
    demo = AgentDefinition(
        id=str(uuid4()),
        name="AI Demo — GB",
        slug=f"ai-demo-gb-{uuid4().hex[:8]}",
        system_prompt="d",
        is_active=True,
        supports_interview=True,  # wrongly dual-flagged
        supports_ai_demo=True,
        telnyx_assistant_id=f"asst_dgb_{uuid4().hex[:8]}",
        accent_region="GB",
    )
    db_session.add_all([interview, demo])
    db_session.commit()

    mapping = AiDemoService._interview_sources_by_region(db_session)
    assert mapping.get("GB") == interview.id
    assert mapping.get("DEFAULT") == interview.id
    assert mapping.get("SC") == interview.id
