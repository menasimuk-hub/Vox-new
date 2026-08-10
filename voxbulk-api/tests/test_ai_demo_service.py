"""Tests for AI Demo Agent request + magic-link lifecycle."""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.demo_knowledge_base import DemoKnowledgeBase  # noqa: F401
from app.models.demo_platform_settings import DemoPlatformSettings  # noqa: F401
from app.models.demo_request import DemoRequest  # noqa: F401
from app.models.demo_session import DemoSession  # noqa: F401
from app.services.ai_demo_service import AiDemoError, AiDemoService, resend_signature, token_hmac
from sqlalchemy import select


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


def test_web_request_and_token_single_use(db):
    req = AiDemoService.create_web_request(
        db,
        contact_name="Alex Demo",
        email="alex@example.com",
        company_name="Acme Ltd",
        whatsapp="+447700900123",
        website="https://acme.example",
        preferred_language="en",
        message="We want to see recruitment screening please",
    )
    assert req is not None
    assert req.status == "pending"

    with patch.object(AiDemoService, "_send_invite_email", return_value=(True, None)), patch.object(
        AiDemoService, "_send_wa_notice", return_value=None
    ):
        out = AiDemoService.approve_and_send(db, req.id, admin_id="admin-1")

    assert out["email_sent"] is True
    demo_link = out["demo_link"]
    token = demo_link.split("token=")[-1]
    assert token_hmac(token)

    verified = AiDemoService.verify_token(db, token)
    assert verified["session_id"]
    assert verified["contact_name"] == "Alex Demo"

    with pytest.raises(AiDemoError):
        AiDemoService.verify_token(db, token)


def test_public_resend_keeps_memory(db):
    req = AiDemoService.create_web_request(
        db,
        contact_name="Sara",
        email="sara@example.com",
        company_name="Sara Co",
        whatsapp="+966500000001",
        website="sara.example",
        preferred_language="ar",
        message="Interested in WhatsApp surveys and feedback",
    )
    assert req is not None
    AiDemoService.update_memory(db, req, {"active_service_code": "surveys", "note": "mid-demo"})
    db.refresh(req)
    assert "surveys" in (req.conversation_memory or "")

    with patch.object(AiDemoService, "_send_invite_email", return_value=(True, None)), patch.object(
        AiDemoService, "_send_wa_notice", return_value=None
    ):
        AiDemoService.approve_and_send(db, req.id, admin_id="admin-1")
        sig = resend_signature(req.id)
        out = AiDemoService.public_resend(db, request_id=req.id, sig=sig)

    assert out["request"]["id"] == req.id
    db.refresh(req)
    memory = req.conversation_memory or ""
    assert "surveys" in memory


def test_ensure_knowledge_bases_seeds_five_products(db):
    AiDemoService.ensure_knowledge_bases(db)
    items = AiDemoService.list_knowledge_bases(db)
    codes = {i["service_code"] for i in items}
    assert "platform_overview" in codes
    assert {"recruitment", "surveys", "feedback", "expo", "smart_card"} <= codes


def test_batch_send_and_open_tracking(db):
    with patch.object(AiDemoService, "_send_invite_email", return_value=(True, None)), patch.object(
        AiDemoService, "_send_wa_notice", return_value=None
    ):
        out = AiDemoService.batch_send(
            db,
            recipients=[{"email": "a@example.com"}, {"email": "b@example.com"}],
            admin_id="admin-1",
            skip_wa=True,
        )
    assert out["sent"] == 2
    assert out["failed"] == 0
    req = db.execute(select(DemoRequest).where(DemoRequest.email == "a@example.com")).scalar_one()
    token = AiDemoService._ensure_tracking_token(db, req)
    AiDemoService.record_open(db, token)
    db.refresh(req)
    assert req.open_count >= 1
    assert req.opened_at is not None
