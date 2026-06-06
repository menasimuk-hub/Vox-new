"""UK compliance baseline — validation, STOP keywords, org merge."""

from __future__ import annotations

import json
import uuid
from datetime import datetime

import pytest

from app.models.industry import Industry
from app.models.organisation import Organisation
from app.models.organisation_ai_config import OrganisationComplianceConfig
from app.models.service_order import ServiceOrder
from app.services.uk_compliance_opt_out import PECR_STOP_RE, is_pecr_stop_message
from app.services.uk_compliance_service import UkComplianceService, validate_compliance_block


@pytest.fixture()
def db():
    from app.core.database import Base, get_engine, get_sessionmaker
    import app.models  # noqa: F401

    engine = get_engine()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    SessionLocal = get_sessionmaker()
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def _org_with_compliance(db) -> tuple[Organisation, ServiceOrder]:
    now = datetime.utcnow()
    org = Organisation(id=str(uuid.uuid4()), name="Compliance Test Org")
    db.add(org)
    db.flush()
    comp = OrganisationComplianceConfig(
        id=str(uuid.uuid4()),
        org_id=org.id,
        privacy_notice_url="https://www.voxbulk.com/privacy",
        contact_email="Data.Pro@voxbulk.com",
        lawful_basis_default="consent",
        opt_out_enabled=True,
        special_category_data_present_default=False,
        created_at=now,
        updated_at=now,
    )
    db.add(comp)
    order = ServiceOrder(
        id=str(uuid.uuid4()),
        org_id=org.id,
        user_id=str(uuid.uuid4()),
        service_code="survey",
        title="Test survey",
        status="paid",
        payment_status="approved",
        recipient_count=0,
        quote_total_pence=0,
        config_json=json.dumps(
            {
                "compliance": {
                    "message_purpose": "survey",
                    "lawful_basis": "consent",
                }
            }
        ),
        created_at=now,
        updated_at=now,
    )
    db.add(order)
    db.commit()
    return org, order


def test_pecr_stop_keywords():
    for word in ("STOP", "stopall", "Unsubscribe", "END", "QUIT", "CANCEL"):
        assert is_pecr_stop_message(word)
    assert not is_pecr_stop_message("yes")
    assert PECR_STOP_RE.pattern


def test_validate_compliance_ok():
    block = {
        "lawful_basis": "consent",
        "message_purpose": "survey",
        "privacy_notice_url": "https://example.com/privacy",
        "contact_email": "dpo@example.com",
        "opt_out_enabled": True,
        "special_category_data_present": False,
    }
    assert validate_compliance_block(block, for_outbound=True) == []


def test_validate_special_category_requires_article9():
    block = {
        "lawful_basis": "consent",
        "message_purpose": "survey",
        "privacy_notice_url": "https://example.com/privacy",
        "contact_email": "dpo@example.com",
        "opt_out_enabled": True,
        "special_category_data_present": True,
    }
    errors = validate_compliance_block(block, for_outbound=True)
    assert any("article9" in e for e in errors)


def test_merged_compliance_from_org(db):
    org, order = _org_with_compliance(db)
    summary = UkComplianceService.readiness_summary(db, order)
    assert summary["ok"] is True
    assert summary["compliance"]["lawful_basis"] == "consent"
    assert summary["compliance"]["privacy_notice_url"] == "https://www.voxbulk.com/privacy"


def test_launch_passes_from_email_templates_when_org_defaults_missing(db):
    from app.models.email_template import EmailTemplate
    from app.services.email_template_service import EmailTemplateService
    from sqlalchemy import select

    org, order = _org_with_compliance(db)
    comp = db.execute(
        select(OrganisationComplianceConfig).where(OrganisationComplianceConfig.org_id == org.id)
    ).scalar_one()
    comp.privacy_notice_url = None
    comp.contact_email = None
    comp.lawful_basis_default = None
    db.add(comp)
    order.config_json = json.dumps({"compliance": {"message_purpose": "survey"}})
    db.add(order)
    EmailTemplateService.ensure_system_templates(db)
    notice = db.execute(
        select(EmailTemplate).where(EmailTemplate.template_key == "general_notification")
    ).scalar_one()
    notice.lawful_basis = "consent"
    notice.privacy_notice_url = "https://example.com/privacy"
    notice.contact_email = "dpo@example.com"
    db.add(notice)
    db.commit()

    summary = UkComplianceService.readiness_summary(db, order)
    assert summary["ok"] is True
    assert summary["compliance"]["lawful_basis"] == "consent"
    assert summary["compliance"]["privacy_notice_url"] == "https://example.com/privacy"
