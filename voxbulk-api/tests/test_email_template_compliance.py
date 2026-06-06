"""Email template UK compliance field persistence."""

from __future__ import annotations

import pytest

from app.services.email_template_service import EmailTemplateService
from app.services.uk_compliance_constants import (
    DEFAULT_COMPLIANCE_CONTACT_EMAIL,
    DEFAULT_LAWFUL_BASIS,
    DEFAULT_PRIVACY_NOTICE_URL,
)


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


def test_create_email_template_sets_compliance_defaults(db):
    row = EmailTemplateService.create(
        db,
        key="custom_notice",
        title="Custom notice",
        subject="Hello",
        body="<p>Hi</p>",
        is_enabled=True,
    )
    assert row.lawful_basis == DEFAULT_LAWFUL_BASIS
    assert row.privacy_notice_url == DEFAULT_PRIVACY_NOTICE_URL
    assert row.contact_email == DEFAULT_COMPLIANCE_CONTACT_EMAIL


def test_launch_outbound_compliance_defaults_from_interview_templates(db):
    EmailTemplateService.ensure_system_templates(db)
    defaults = EmailTemplateService.launch_outbound_compliance_defaults(db, service_code="interview")
    assert defaults["lawful_basis"]
    assert defaults["privacy_notice_url"].startswith("https://")
    assert "@" in defaults["contact_email"]
