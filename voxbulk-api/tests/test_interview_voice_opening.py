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
            "Hello {first_name}, this is {agent_name} calling from {company_name} "
            "about the {role} role. This call is recorded for quality and assessment. "
            "Do you have about 10 to 15 minutes now?"
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
    assert "10" in greeting and "15" in greeting
    assert "ai assistant" not in greeting.lower()
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
    assert "Do NOT repeat the disclosure or INTRO" in instructions
    assert "Sound like a skilled recruiter" in instructions or "Sound like a helpful recruiter" in instructions or "Sound like a real recruiter" in instructions or "British recruiter" in instructions or "real human phone interviewer" in instructions
    assert "Never say you are an AI assistant" in instructions
    assert "briefly explain the purpose" in instructions.lower()
    assert "anything else they would like to add" in instructions.lower()
    assert "ACTIVE LISTENING" in instructions or "off-topic" in instructions.lower()
    assert "FORBIDDEN" in instructions or "got it" in instructions.lower()

def test_strip_opening_and_intro_from_script():
    from app.services.voice_agent_runtime import strip_opening_and_intro_from_script

    script = (
        "OPENING DISCLOSURE\nHello there.\n\nINTRO\nDo you have time?\n\n"
        "QUESTIONS\n1. Example?\n\nCLOSING\nBye."
    )
    stripped = strip_opening_and_intro_from_script(script)
    assert stripped.startswith("QUESTIONS")
    assert "OPENING DISCLOSURE" not in stripped
    assert "INTRO" not in stripped
    assert "Example?" in stripped


def test_arabic_interview_generate_prompt_uses_dialect_not_fusha():
    from app.services.agent_prompt_generator import (
        is_arabic_interview_prompt_target,
        resolve_arabic_interview_dialect,
        _meta_for,
    )

    assert is_arabic_interview_prompt_target(
        agent_name="interview_AR-Sultan",
        description="Gulf Arabic interview agent",
        supports_interview=True,
    )
    assert not is_arabic_interview_prompt_target(
        agent_name="interview_GB-Leo",
        description="British English interview",
        supports_interview=True,
    )
    assert resolve_arabic_interview_dialect(
        agent_name="interview_AR-Jammal",
        description="Egyptian Arabic interview",
        supports_interview=True,
    ) == "EG"
    meta = _meta_for(kind="prompt", arabic_dialect="EG")
    assert "مصري" in meta
    assert "نبدأ" in meta
    assert "فصحى" in meta  # forbidden note
    assert "وش" not in meta or "ممنوع" in meta
    gulf = _meta_for(kind="prompt", arabic_dialect="SA")
    assert "خليجي" in gulf
    legacy = _meta_for(kind="prompt", arabic_fusha=True)
    assert "فصحى" in legacy
    assert "British English" not in meta


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


def test_arabic_interview_runtime_gulf_agent_uses_khaleeji(db):
    org, order, recipient, _ = _seed_interview_call(db)
    agent = AgentDefinition(
        name="Sultan - Ar",
        slug=f"sultan-{uuid.uuid4().hex[:8]}",
        voice_label="Sultan",
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
        config={"role": "مساعد رعاية", "approved_script": "INTRO\nThanks.\n\nQUESTIONS\n1. هل لديك خبرة؟\n\nCLOSING\nBye."},
        recipient=recipient,
        agent=agent,
        service_key=SERVICE_INTERVIEW,
    )
    assert "الخليجية" in instructions or "خليجي" in instructions
    assert "فصحى" in instructions
    assert "أسلوب الكلام" in instructions
    assert "في أمان الله" in instructions


def test_arabic_interview_runtime_egyptian_agent_uses_masri(db):
    org, order, recipient, _ = _seed_interview_call(db)
    agent = AgentDefinition(
        name="Jamal - Ar",
        slug=f"jamal-{uuid.uuid4().hex[:8]}",
        voice_label="Jammal",
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
        config={"role": "مساعد رعاية", "approved_script": "INTRO\nThanks.\n\nQUESTIONS\n1. هل لديك خبرة؟\n\nCLOSING\nBye."},
        recipient=recipient,
        agent=agent,
        service_key=SERVICE_INTERVIEW,
    )
    assert "المصرية" in instructions or "مصري" in instructions
    assert "دلوقتي" in instructions or "ماشي" in instructions
    assert "فصحى" in instructions
    assert "فرز قصيرة" not in instructions
    assert "مقابلة قصيرة بخصوص" in instructions or "بخصوص وظيفة" in instructions
    assert "ممكن توضح" in instructions or "الاستماع الذكي" in instructions or "برا الموضوع" in instructions
    assert "مع السلامة" in instructions
    assert "شو قصدك" not in instructions


def test_english_interview_runtime_uses_regional_dialect_pack(db):
    org, order, recipient, _ = _seed_interview_call(db)
    agent = AgentDefinition(
        name="interview-au-jack",
        slug=f"interview-au-jack-{uuid.uuid4().hex[:8]}",
        voice_label="Jack",
        accent_region="AU",
        system_prompt="You are Jack.",
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
        config={"role": "Receptionist", "approved_script": "INTRO\nHi.\n\nQUESTIONS\n1. Experience?\n\nCLOSING\nBye."},
        recipient=recipient,
        agent=agent,
        service_key=SERVICE_INTERVIEW,
    )
    assert "Australian" in instructions or "No worries" in instructions or "crack on" in instructions
    assert "got it" in instructions.lower() or "FORBIDDEN" in instructions or "never empty" in instructions.lower()
