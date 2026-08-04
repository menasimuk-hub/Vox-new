"""Platform sender emails (@voxbulk.com) CRUD + purpose resolver."""

from __future__ import annotations

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
    )
    assert row.email == "sales@voxbulk.com"
    sender = PlatformSenderEmailService.get_sender_by_purpose(db, "sales")
    assert sender == ("Voxbulk Sales", "sales@voxbulk.com")


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
