"""Salesman Mail Support/Billing escalation + IMAP fingerprint dedupe."""

from __future__ import annotations

import uuid
from datetime import datetime
from email.message import EmailMessage
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.core.encryption import get_encryptor
from app.core.security import hash_password
from app.models.membership import OrganisationMembership
from app.models.organisation import Organisation
from app.models.sales_mail import SalesMailMessage
from app.models.sales_rep import SalesRep
from app.models.support_ticket import SupportTicket, SupportTicketMessage
from app.models.user import User
from app.services import sales_mail_service
from app.services.sales_mail_service import (
    ESCALATE_HEADER,
    SalesMailServiceError,
    escalation_fingerprint,
    escalation_message_id,
    fingerprint_from_rfc_message_id,
    send_escalation,
)
from app.services.support_mailbox_sync_service import _extract_escalation_fingerprint
from app.services.support_ticket_service import SupportTicketService


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


def _seed(db) -> tuple[SalesRep, Organisation, User, SalesMailMessage]:
    user = User(
        email=f"sales-{uuid.uuid4().hex[:8]}@test.com",
        password_hash=hash_password("pass123"),
        is_active=True,
    )
    db.add(user)
    db.flush()
    org = Organisation(name=f"Escalation Org {uuid.uuid4().hex[:6]}")
    db.add(org)
    db.flush()
    db.add(OrganisationMembership(org_id=org.id, user_id=user.id, role="owner"))
    enc = get_encryptor().encrypt_str("smtp-secret")
    rep = SalesRep(
        user_id=user.id,
        name="Sales Person",
        kind="salesman",
        promo_code=f"ESC{uuid.uuid4().hex[:6].upper()}",
        is_active=True,
        smtp_host="smtp.test",
        smtp_port=587,
        smtp_use_tls=True,
        smtp_username="sales@voxbulk.com",
        smtp_password_enc=enc,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(rep)
    db.flush()
    msg = SalesMailMessage(
        id=str(uuid.uuid4()),
        sales_rep_id=rep.id,
        folder="INBOX",
        message_id=f"<orig-{uuid.uuid4().hex}@example.com>",
        from_email="customer@example.com",
        from_name="Customer",
        to_email="sales@voxbulk.com",
        subject="Need help with invoice",
        body_text="Please look at this invoice issue.",
        body_html="<p>Please look at this invoice issue.</p>",
        has_attachments=True,
        direction="received",
        is_read=True,
        date=datetime.utcnow(),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(msg)
    db.commit()
    db.refresh(rep)
    db.refresh(msg)
    return rep, org, user, msg


def test_fingerprint_helpers_stable():
    fp = escalation_fingerprint(target="support", sales_rep_id="rep-1", source_message_id="msg-1")
    assert len(fp) == 64
    assert fp == escalation_fingerprint(target="support", sales_rep_id="rep-1", source_message_id="msg-1")
    mid = escalation_message_id(fp)
    assert mid == f"<{fp}@escalate.voxbulk.com>"
    assert fingerprint_from_rfc_message_id(mid) == fp
    assert fingerprint_from_rfc_message_id(f"<{fp}@other.example>") is None


def test_extract_escalation_fingerprint_from_header_and_body():
    fp = "a" * 64
    msg = EmailMessage()
    msg[ESCALATE_HEADER] = fp
    msg["Message-ID"] = escalation_message_id(fp)
    assert _extract_escalation_fingerprint(msg, "") == fp

    msg2 = EmailMessage()
    msg2["Message-ID"] = escalation_message_id(fp)
    assert _extract_escalation_fingerprint(msg2, "hello") == fp

    msg3 = EmailMessage()
    body = f"Forwarded\n{ESCALATE_HEADER}: {fp}\n"
    assert _extract_escalation_fingerprint(msg3, body) == fp


@patch("app.services.support_ticket_email_service.SupportTicketEmailService.notify_created", return_value={"ok": True})
@patch("app.services.sales_mail_service.smtplib.SMTP")
def test_escalate_support_creates_technical_ticket(mock_smtp, _notify, db):
    rep, org, user, msg = _seed(db)
    server = MagicMock()
    mock_smtp.return_value = server

    result = send_escalation(
        db,
        sales_rep_id=rep.id,
        org_id=org.id,
        user_id=user.id,
        escalate_target="support",
        source_message_id=msg.id,
        body_text="Please investigate.",
    )
    assert result["sent"] is True
    assert result["duplicate"] is False
    assert result["category"] == "technical"
    assert result["ticket_id"]

    ticket = db.get(SupportTicket, result["ticket_id"])
    assert ticket is not None
    assert ticket.organisation_id == org.id
    assert ticket.created_by_user_id == user.id
    assert ticket.category == "technical"
    assert ticket.channel == "email"
    assert ticket.requester_email == "customer@example.com"
    assert ticket.email_fingerprint == escalation_fingerprint(
        target="support", sales_rep_id=rep.id, source_message_id=msg.id
    )
    body = db.scalar(
        select(SupportTicketMessage.body).where(
            SupportTicketMessage.ticket_id == ticket.id,
            SupportTicketMessage.is_internal_note == False,  # noqa: E712
        )
    )
    assert "customer@example.com" in (body or "")
    assert "Need help with invoice" in (body or "")
    assert "attachments" in (body or "").lower()
    server.login.assert_called_once()
    server.sendmail.assert_called_once()
    recipients = server.sendmail.call_args[0][1]
    assert "support@voxbulk.com" in recipients


@patch("app.services.support_ticket_email_service.SupportTicketEmailService.notify_created", return_value={"ok": True})
@patch("app.services.sales_mail_service.smtplib.SMTP")
def test_escalate_billing_creates_invoices_ticket(mock_smtp, _notify, db):
    rep, org, user, msg = _seed(db)
    mock_smtp.return_value = MagicMock()

    result = send_escalation(
        db,
        sales_rep_id=rep.id,
        org_id=org.id,
        user_id=user.id,
        escalate_target="billing",
        source_message_id=msg.id,
    )
    assert result["category"] == "invoices"
    ticket = db.get(SupportTicket, result["ticket_id"])
    assert ticket is not None
    assert ticket.category == "invoices"
    recipients = mock_smtp.return_value.sendmail.call_args[0][1]
    assert "billing@voxbulk.com" in recipients


@patch("app.services.support_ticket_email_service.SupportTicketEmailService.notify_created", return_value={"ok": True})
@patch("app.services.sales_mail_service.smtplib.SMTP")
def test_escalate_retry_does_not_duplicate_ticket(mock_smtp, _notify, db):
    rep, org, user, msg = _seed(db)
    mock_smtp.return_value = MagicMock()

    first = send_escalation(
        db,
        sales_rep_id=rep.id,
        org_id=org.id,
        user_id=user.id,
        escalate_target="support",
        source_message_id=msg.id,
    )
    second = send_escalation(
        db,
        sales_rep_id=rep.id,
        org_id=org.id,
        user_id=user.id,
        escalate_target="support",
        source_message_id=msg.id,
    )
    assert first["ticket_id"] == second["ticket_id"]
    assert second["duplicate"] is True
    assert second["sent"] is False
    assert mock_smtp.return_value.sendmail.call_count == 1
    tickets = list(
        db.scalars(select(SupportTicket).where(SupportTicket.email_fingerprint == first["email_fingerprint"]))
    )
    assert len(tickets) == 1


def test_escalate_invalid_message_access(db):
    rep, org, user, msg = _seed(db)
    other_user = User(
        email=f"other-{uuid.uuid4().hex[:8]}@test.com",
        password_hash=hash_password("x"),
        is_active=True,
    )
    db.add(other_user)
    db.flush()
    other = SalesRep(
        user_id=other_user.id,
        name="Other",
        kind="salesman",
        promo_code=f"OTH{uuid.uuid4().hex[:6].upper()}",
        is_active=True,
        smtp_host="smtp.test",
        smtp_port=587,
        smtp_username="other@voxbulk.com",
        smtp_password_enc=get_encryptor().encrypt_str("x"),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(other)
    db.commit()

    with pytest.raises(SalesMailServiceError, match="not found"):
        send_escalation(
            db,
            sales_rep_id=other.id,
            org_id=org.id,
            user_id=user.id,
            escalate_target="support",
            source_message_id=msg.id,
        )


@patch("app.services.support_ticket_email_service.SupportTicketEmailService.notify_created", return_value={"ok": True})
@patch("app.services.sales_mail_service.smtplib.SMTP")
def test_escalate_send_failure_does_not_create_ticket(mock_smtp, _notify, db):
    rep, org, user, msg = _seed(db)
    server = MagicMock()
    server.sendmail.side_effect = sales_mail_service.smtplib.SMTPException("boom")
    mock_smtp.return_value = server

    with pytest.raises(SalesMailServiceError, match="SMTP"):
        send_escalation(
            db,
            sales_rep_id=rep.id,
            org_id=org.id,
            user_id=user.id,
            escalate_target="support",
            source_message_id=msg.id,
        )
    tickets = list(db.scalars(select(SupportTicket)))
    assert tickets == []


@patch("app.services.support_ticket_email_service.SupportTicketEmailService.notify_created", return_value={"ok": True})
def test_imap_skips_duplicate_when_fingerprint_exists(_notify, db):
    rep, org, user, msg = _seed(db)
    fp = escalation_fingerprint(target="support", sales_rep_id=rep.id, source_message_id=msg.id)
    ticket = SupportTicketService.create_ticket(
        db,
        org_id=org.id,
        user_id=user.id,
        category="technical",
        subject="Fwd: Need help with invoice",
        message="already escalated",
        channel="email",
        email_fingerprint=fp,
        requester_email="customer@example.com",
    )
    inbound = EmailMessage()
    inbound["Message-ID"] = escalation_message_id(fp)
    inbound[ESCALATE_HEADER] = fp
    inbound["Subject"] = "Fwd: Need help with invoice"
    inbound.set_content("copy of forward")
    extracted = _extract_escalation_fingerprint(inbound, inbound.get_content())
    assert extracted == fp
    found = SupportTicketService.find_by_email_fingerprint(db, extracted)
    assert found is not None
    assert found.id == ticket.id

    # create_ticket with same fingerprint returns existing (retry-safe)
    again = SupportTicketService.create_ticket(
        db,
        org_id=org.id,
        user_id=user.id,
        category="technical",
        subject="should not create",
        message="duplicate",
        channel="imap",
        email_fingerprint=fp,
    )
    assert again.id == ticket.id
    assert len(list(db.scalars(select(SupportTicket)))) == 1
