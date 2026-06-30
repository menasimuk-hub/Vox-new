"""Interview AI call opening prompt — company name, recording disclosure, confirmation."""

from __future__ import annotations

import uuid
from datetime import datetime

import pytest

from app.core.agent_services import SERVICE_INTERVIEW
from app.core.database import get_sessionmaker
from app.core.security import hash_password
from app.models.agent import AgentDefinition
from app.models.membership import OrganisationMembership
from app.models.organisation import Organisation
from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.models.user import User
from app.services.platform_catalog_service import PlatformCatalogService
from app.services.voice_agent_runtime import (
    build_service_opening_greeting,
    build_service_runtime_instructions,
    is_invalid_spoken_company_name,
    resolve_voice_call_company_name,
    substitute_voice_placeholders,
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


def _seed_interview_call(db):
    org = Organisation(name="Acme Health")
    db.add(org)
    db.flush()
    user = User(email=f"voice-{uuid.uuid4().hex[:8]}@test.com", password_hash=hash_password("pass123"), is_active=True)
    db.add(user)
    db.flush()
    db.add(OrganisationMembership(org_id=org.id, user_id=user.id, role="owner"))
    agent = AgentDefinition(
        name="interview_GB-Leo",
        slug=f"leo-{uuid.uuid4().hex[:8]}",
        voice_label="Leo",
        system_prompt="You are Leo for {company_name}.",
        kb_context="Call on behalf of {company_name} about {role}.",
        opening_disclosure_template=(
            "Hello {first_name}, this is {agent_name} calling on behalf of {company_name} "
            "about the {role} role. This call is recorded. Is now a good time?"
        ),
        supports_interview=True,
        disclosure_for_interview=True,
        disclosure_mandatory=True,
        is_active=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(agent)
    db.flush()
    order = ServiceOrder(
        org_id=org.id,
        user_id=user.id,
        service_code="interview",
        title="Care Assistant",
        status="running",
        payment_status="approved",
        config_json='{"role":"Care Assistant","delivery":"ai_call","approved_script":"INTRO\\nThanks.\\n\\nQUESTIONS\\n1. Example?\\n\\nCLOSING\\nBye."}',
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(order)
    db.flush()
    recipient = ServiceOrderRecipient(
        order_id=order.id,
        row_number=1,
        name="Jane Doe",
        phone="+447700900123",
        status="scheduled",
        created_at=datetime.utcnow(),
    )
    db.add(recipient)
    db.commit()
    return org, order, recipient, agent


def test_resolve_company_name_from_org_when_config_missing(db):
    org, order, _, _ = _seed_interview_call(db)
    company = resolve_voice_call_company_name(db, config={}, org_id=org.id, order=order)
    assert company == "Acme Health"


def test_literal_company_is_invalid_and_uses_hiring_team_fallback(db):
    org, order, _, _ = _seed_interview_call(db)
    company = resolve_voice_call_company_name(
        db,
        config={"company_name": "company", "organisation_name": "company"},
        org_id=org.id,
        order=order,
    )
    assert company == "Acme Health"
    assert is_invalid_spoken_company_name("company")


def test_interview_opening_greeting_uses_real_company_name(db):
    org, order, recipient, agent = _seed_interview_call(db)
    greeting = build_service_opening_greeting(
        db,
        agent=agent,
        config={"role": "Care Assistant"},
        recipient_name=recipient.name,
        service_key=SERVICE_INTERVIEW,
        org_id=org.id,
        order=order,
    )
    assert "Acme Health" in greeting
    assert "Leo" in greeting
    assert "record" in greeting.lower()
    assert "good time" in greeting.lower() or "hear me" in greeting.lower()
    assert " company" not in f" {greeting.lower()} "
    assert "{company_name}" not in greeting


def test_runtime_instructions_replace_kb_placeholders(db):
    org, order, recipient, agent = _seed_interview_call(db)
    instructions = build_service_runtime_instructions(
        db,
        order=order,
        config={"role": "Care Assistant"},
        recipient=recipient,
        agent=agent,
        service_key=SERVICE_INTERVIEW,
    )
    assert "Acme Health" in instructions
    assert "{company_name}" not in instructions
    assert "Never say the generic word 'company'" in instructions


def test_substitute_voice_placeholders_regression_leo_from_company(db):
    rendered = substitute_voice_placeholders(
        "Hello, this is {agent_name} from {company_name}.",
        company_name="Acme Health",
        agent_name="Leo",
        role="Nurse",
        first_name="Jane",
    )
    assert rendered == "Hello, this is Leo from Acme Health."
    assert "from company" not in rendered.lower()


def test_arabic_interview_runtime_uses_gulf_not_msa(db):
    org, order, recipient, _ = _seed_interview_call(db)
    agent = AgentDefinition(
        name="Jamal - Ar",
        slug=f"jamal-{uuid.uuid4().hex[:8]}",
        voice_label="Jamal",
        system_prompt="English template only.",
        supports_interview=True,
        is_active=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(agent)
    db.commit()
    instructions = build_service_runtime_instructions(
        db,
        order=order,
        config={"role": "مساعد رعاية", "approved_script": "INTRO\nThanks.\n\nQUESTIONS\n1. Example?\n\nCLOSING\nBye."},
        recipient=recipient,
        agent=agent,
        service_key=SERVICE_INTERVIEW,
    )
    assert "الخليجية" in instructions or "خليجي" in instructions
    assert "زين" in instructions or "منيح" in instructions or "تمام" in instructions
