"""Salesman mailbox password persistence + stored-credential decrypt."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.core.encryption import get_encryptor
from app.models.membership import OrganisationMembership  # noqa: F401
from app.models.organisation import Organisation  # noqa: F401
from app.models.sales_rep import SalesRep  # noqa: F401
from app.models.user import User  # noqa: F401
from app.services.sales_rep_service import SalesRepError, SalesRepService


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


def test_update_saves_encrypted_mailbox_password(db):
    email = f"s-{uuid.uuid4().hex[:8]}@test.com"
    rep = SalesRepService.create_rep(
        db,
        email=email,
        password="secret12",
        name="Sales One",
        promo_code=f"M{uuid.uuid4().hex[:6].upper()}",
        country="GB",
    )
    assert SalesRepService.rep_to_dict(rep)["has_smtp"] is False

    SalesRepService.update_rep(
        db,
        rep=rep,
        patch={
            "smtp_username": "sales1@voxbulk.com",
            "smtp_password": "Mailbox!Pass",
            "imap_username": "sales1@voxbulk.com",
            "imap_password": "Mailbox!Pass",
            "smtp_host": "voxbulk.com",
            "imap_host": "voxbulk.com",
        },
    )
    db.refresh(rep)
    d = SalesRepService.rep_to_dict(rep)
    assert d["has_smtp"] is True
    assert d["has_imap"] is True
    assert get_encryptor().decrypt_str(rep.smtp_password_enc) == "Mailbox!Pass"
    assert get_encryptor().decrypt_str(rep.imap_password_enc) == "Mailbox!Pass"


def test_single_password_enables_both_smtp_and_imap(db):
    email = f"s-{uuid.uuid4().hex[:8]}@test.com"
    rep = SalesRepService.create_rep(
        db,
        email=email,
        password="secret12",
        name="Sales Two",
        promo_code=f"N{uuid.uuid4().hex[:6].upper()}",
        country="GB",
        mailbox={
            "smtp_username": "sales2@voxbulk.com",
            "smtp_password": "OnlySmtpKey",
            "smtp_host": "voxbulk.com",
            "imap_host": "voxbulk.com",
            "imap_username": "sales2@voxbulk.com",
        },
    )
    d = SalesRepService.rep_to_dict(rep)
    assert d["has_smtp"] is True
    assert d["has_imap"] is True
    assert get_encryptor().decrypt_str(rep.imap_password_enc) == "OnlySmtpKey"


def test_username_without_password_rejected(db):
    email = f"s-{uuid.uuid4().hex[:8]}@test.com"
    rep = SalesRepService.create_rep(
        db,
        email=email,
        password="secret12",
        name="Sales Three",
        promo_code=f"P{uuid.uuid4().hex[:6].upper()}",
        country="GB",
    )
    with pytest.raises(SalesRepError, match="Mailbox password is required"):
        SalesRepService.update_rep(
            db,
            rep=rep,
            patch={"smtp_username": "sales3@voxbulk.com", "imap_username": "sales3@voxbulk.com"},
        )
