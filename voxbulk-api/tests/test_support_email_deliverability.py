"""Support Disk recipient deliverability / anonymized placeholder suppression."""

from __future__ import annotations

import uuid
from datetime import datetime
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.core.security import hash_password
from app.models.organisation import Organisation
from app.models.support_ticket import SupportTicket
from app.models.user import User
from app.services.support_email_deliverability import (
    is_reserved_invalid_placeholder,
    recipient_suppression_reason,
    resolve_ticket_customer_recipient,
)
from app.services.support_ticket_email_service import SupportTicketEmailService
from app.services.support_ticket_service import ticket_requester_email


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


def _user(db, email: str, **extra) -> User:
    u = User(
        email=email,
        password_hash=hash_password("pass123"),
        is_active=extra.pop("is_active", True),
        deletion_status=extra.pop("deletion_status", "active"),
        anonymized_at=extra.pop("anonymized_at", None),
    )
    db.add(u)
    db.flush()
    return u


def _org(db, *, contact_email: str | None = None, **extra) -> Organisation:
    org = Organisation(
        name=f"Org {uuid.uuid4().hex[:6]}",
        contact_email=contact_email,
        deletion_status=extra.pop("deletion_status", "active"),
        anonymized_at=extra.pop("anonymized_at", None),
    )
    db.add(org)
    db.flush()
    return org


def _ticket(db, *, org: Organisation, creator: User, requester_email: str | None = None) -> SupportTicket:
    t = SupportTicket(
        organisation_id=org.id,
        created_by_user_id=creator.id,
        subject="Help please",
        category="technical",
        status="open",
        channel="web",
        priority="normal",
        requester_email=requester_email,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        last_message_at=datetime.utcnow(),
    )
    db.add(t)
    db.flush()
    return t


def test_placeholder_domain_detection():
    assert is_reserved_invalid_placeholder("deleted-abc@anonymized.voxbulk.invalid")
    assert is_reserved_invalid_placeholder("archived-x@anonymized.voxbulk.invalid")
    assert is_reserved_invalid_placeholder("x@other.invalid")
    assert not is_reserved_invalid_placeholder("customer@example.com")


def test_explicit_valid_requester_preferred(db):
    creator = _user(db, "owner@org.com")
    org = _org(db)
    ticket = _ticket(db, org=org, creator=creator, requester_email="customer@example.com")
    email, reason = resolve_ticket_customer_recipient(db, ticket)
    assert email == "customer@example.com"
    assert reason is None
    assert ticket_requester_email(db, ticket) == "customer@example.com"


def test_creator_fallback_when_no_requester(db):
    creator = _user(db, "owner@org.com")
    org = _org(db)
    ticket = _ticket(db, org=org, creator=creator, requester_email=None)
    email, reason = resolve_ticket_customer_recipient(db, ticket)
    assert email == "owner@org.com"
    assert reason is None


def test_anonymized_user_suppressed_falls_to_explicit(db):
    creator = _user(
        db,
        "deleted-aa@anonymized.voxbulk.invalid",
        is_active=False,
        deletion_status="archived",
        anonymized_at=datetime.utcnow(),
    )
    org = _org(db)
    ticket = _ticket(db, org=org, creator=creator, requester_email="still.real@customer.com")
    email, reason = resolve_ticket_customer_recipient(db, ticket)
    assert email == "still.real@customer.com"
    assert reason is None


def test_anonymized_creator_suppressed_without_requester(db):
    creator = _user(
        db,
        "deleted-bb@anonymized.voxbulk.invalid",
        is_active=False,
        deletion_status="archived",
        anonymized_at=datetime.utcnow(),
    )
    org = _org(db)
    ticket = _ticket(db, org=org, creator=creator, requester_email=None)
    email, reason = resolve_ticket_customer_recipient(db, ticket)
    assert email is None
    assert reason in {"placeholder_domain", "user_anonymized", "user_archived", "user_inactive"}


def test_anonymized_org_contact_suppressed(db):
    creator = _user(db, "owner@org.com")
    org = _org(
        db,
        contact_email="archived-cc@anonymized.voxbulk.invalid",
        deletion_status="archived",
        anonymized_at=datetime.utcnow(),
    )
    reason = recipient_suppression_reason(
        db, "archived-cc@anonymized.voxbulk.invalid", organisation=org
    )
    assert reason is not None
    # Explicit requester set to org placeholder must not deliver
    ticket = _ticket(
        db,
        org=org,
        creator=creator,
        requester_email="archived-cc@anonymized.voxbulk.invalid",
    )
    email, skip = resolve_ticket_customer_recipient(db, ticket)
    # Falls back to deliverable creator
    assert email == "owner@org.com"
    assert skip is None


def test_notify_created_skips_placeholder_without_smtp(db):
    creator = _user(
        db,
        "deleted-dd@anonymized.voxbulk.invalid",
        is_active=False,
        deletion_status="archived",
        anonymized_at=datetime.utcnow(),
    )
    org = _org(db)
    ticket = _ticket(db, org=org, creator=creator, requester_email=None)
    with patch(
        "app.services.smtp_mailer_service.SmtpMailerService.send_html"
    ) as send_html:
        result = SupportTicketEmailService.notify_created(db, ticket)
        send_html.assert_not_called()
    assert result.get("ok") is False
    assert result.get("skipped") is True
    assert result.get("reason")


def test_notify_reply_and_status_skip_placeholder(db):
    creator = _user(
        db,
        "deleted-ee@anonymized.voxbulk.invalid",
        is_active=False,
        deletion_status="archived",
        anonymized_at=datetime.utcnow(),
    )
    org = _org(db)
    ticket = _ticket(db, org=org, creator=creator, requester_email=None)
    with patch(
        "app.services.smtp_mailer_service.SmtpMailerService.send_html"
    ) as send_html:
        reply = SupportTicketEmailService.notify_reply(db, ticket, reply_body="Hello")
        status = SupportTicketEmailService.notify_status(db, ticket)
        send_html.assert_not_called()
    assert reply.get("skipped") is True
    assert status.get("skipped") is True


def test_notify_created_delivers_to_valid_requester(db):
    creator = _user(db, "owner@org.com")
    org = _org(db)
    ticket = _ticket(db, org=org, creator=creator, requester_email="customer@example.com")
    with patch.object(
        SupportTicketEmailService,
        "send_template",
        return_value={"ok": True, "to": "customer@example.com"},
    ) as send_template:
        result = SupportTicketEmailService.notify_created(db, ticket)
    assert result["ok"] is True
    send_template.assert_called_once()
    assert send_template.call_args.kwargs["to_email"] == "customer@example.com"


def test_send_template_blocks_placeholder_before_smtp(db):
    creator = _user(db, "owner@org.com")
    org = _org(db)
    ticket = _ticket(db, org=org, creator=creator, requester_email="customer@example.com")
    with patch(
        "app.services.smtp_mailer_service.SmtpMailerService.send_html"
    ) as send_html:
        result = SupportTicketEmailService.send_template(
            db,
            template_key="support_ticket_created",
            to_email="deleted-ff@anonymized.voxbulk.invalid",
            ticket=ticket,
        )
        send_html.assert_not_called()
    assert result.get("ok") is False
    assert result.get("skipped") is True
    assert result.get("reason") == "placeholder_domain"
