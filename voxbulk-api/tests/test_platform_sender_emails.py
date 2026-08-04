"""Platform sender emails (@voxbulk.com) CRUD + purpose resolver + passwords."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.platform_sender_email import PlatformSenderEmail  # noqa: F401
from app.services.platform_sender_email_service import (
    PlatformSenderEmailError,
    PlatformSenderEmailService,
)


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


def test_create_sales_and_resolve_purpose(db):
    row = PlatformSenderEmailService.create(
        db,
        local_part="sales",
        from_name="Voxbulk Sales",
        purpose="sales",
        notes="Hub invoices",
        password="secret-sales",
    )
    assert row.email == "sales@voxbulk.com"
    sender = PlatformSenderEmailService.get_sender_by_purpose(db, "sales")
    assert sender == ("Voxbulk Sales", "sales@voxbulk.com")
    outbound = PlatformSenderEmailService.resolve_outbound(db, "sales")
    assert outbound["from_email"] == "sales@voxbulk.com"
    assert outbound["smtp_password"] == "secret-sales"
    assert outbound["smtp_username"] == "sales@voxbulk.com"


def test_reject_non_voxbulk_domain(db):
    with pytest.raises(PlatformSenderEmailError, match="Domain must be"):
        PlatformSenderEmailService.create(db, local_part="sales@other.com", purpose="sales")


def test_freeze_hides_from_purpose_resolver(db):
    PlatformSenderEmailService.create(db, local_part="sales", from_name="Sales", purpose="sales")
    rows = PlatformSenderEmailService.list_all(db)
    assert len(rows) == 1
    PlatformSenderEmailService.freeze(db, rows[0].id, frozen=True)
    assert PlatformSenderEmailService.get_sender_by_purpose(db, "sales") is None
    PlatformSenderEmailService.freeze(db, rows[0].id, frozen=False)
    assert PlatformSenderEmailService.get_sender_by_purpose(db, "sales") is not None


def test_purpose_unique_when_active(db):
    PlatformSenderEmailService.create(db, local_part="sales", purpose="sales")
    with pytest.raises(PlatformSenderEmailError, match="Purpose"):
        PlatformSenderEmailService.create(db, local_part="sales2", purpose="sales")


def test_delete_sender(db):
    row = PlatformSenderEmailService.create(db, local_part="noreply", purpose="noreply")
    PlatformSenderEmailService.delete(db, row.id)
    assert PlatformSenderEmailService.list_all(db) == []


def test_ensure_system_senders_seeds(db):
    rows = PlatformSenderEmailService.ensure_system_senders(db)
    purposes = {r.purpose for r in rows}
    assert "sales" in purposes
    assert "noreply" in purposes
    assert "billing" in purposes
    # Idempotent
    rows2 = PlatformSenderEmailService.ensure_system_senders(db)
    assert len(rows2) >= len(rows)


def test_test_send_uses_row_password(db):
    row = PlatformSenderEmailService.create(
        db, local_part="noreply", purpose="noreply", password="npw", from_name="No Reply"
    )
    with patch("app.services.smtp_mailer_service.SmtpMailerService.send_plain") as send:
        send.return_value = None
        PlatformSenderEmailService.test_send(db, row.id, to_addr="admin@example.com")
        assert send.called
        kwargs = send.call_args.kwargs
        assert kwargs["from_email"] == "noreply@voxbulk.com"
        assert kwargs["smtp_password"] == "npw"
        assert kwargs["to_addr"] == "admin@example.com"
