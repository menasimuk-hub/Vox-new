"""VoxBox sync: Message-ID idempotency and list visibility after upsert."""

from __future__ import annotations

import uuid
from datetime import datetime
from email.message import EmailMessage

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.voxbox_mail_account import VoxboxMailAccount
from app.models.voxbox_message import VoxboxMessage
from app.services.voxbox_mail_service import VoxboxMailService


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


def _account(db) -> VoxboxMailAccount:
    row = VoxboxMailAccount(
        id=str(uuid.uuid4()),
        name="Test Mailbox",
        email="box@example.com",
        imap_host="imap.example.com",
        smtp_host="smtp.example.com",
        username="box@example.com",
        status="ok",
        frozen=False,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(row)
    db.commit()
    return row


def _rfc_message(*, message_id: str, subject: str = "Hello", body: str = "Body text") -> EmailMessage:
    msg = EmailMessage()
    msg["Message-ID"] = message_id
    msg["From"] = "Sender <sender@example.com>"
    msg["To"] = "box@example.com"
    msg["Subject"] = subject
    msg["Date"] = "Mon, 05 Aug 2026 10:00:00 +0000"
    msg.set_content(body)
    return msg


def test_upsert_idempotent_by_message_id(db):
    account = _account(db)
    mid = f"<idem-{uuid.uuid4().hex}@example.com>"
    msg = _rfc_message(message_id=mid, subject="First", body="One")

    row1, created1 = VoxboxMailService.upsert_synced_message(
        db,
        account=account,
        folder_label="inbox",
        imap_uid="101",
        msg=msg,
        flags="FLAGS (\\Seen)",
        commit=True,
    )
    assert created1 is True

    msg2 = _rfc_message(message_id=mid, subject="First updated", body="Two")
    row2, created2 = VoxboxMailService.upsert_synced_message(
        db,
        account=account,
        folder_label="inbox",
        imap_uid="101",
        msg=msg2,
        flags="FLAGS (\\Seen)",
        commit=True,
    )
    assert created2 is False
    assert row2.id == row1.id
    assert row2.subject == "First updated"
    assert (row2.body_text or "").startswith("Two")

    count = db.scalar(
        select(func.count())
        .select_from(VoxboxMessage)
        .where(
            VoxboxMessage.account_id == account.id,
            VoxboxMessage.internet_message_id == mid,
        )
    )
    assert count == 1


def test_sync_upsert_then_list_visible(db):
    account = _account(db)
    mid = f"<list-{uuid.uuid4().hex}@example.com>"
    msg = _rfc_message(message_id=mid, subject="Visible after sync", body="Synced body")
    VoxboxMailService.upsert_synced_message(
        db,
        account=account,
        folder_label="inbox",
        imap_uid="202",
        msg=msg,
        flags="FLAGS ()",
        commit=True,
    )

    listed = VoxboxMailService.list_messages(db, account_id=account.id, folder="inbox")
    assert any(m["subject"] == "Visible after sync" for m in listed)
    assert any(m.get("from_email") == "sender@example.com" for m in listed)


def test_sync_all_partial_flag_when_account_errors(db, monkeypatch):
    good = _account(db)
    bad = VoxboxMailAccount(
        id=str(uuid.uuid4()),
        name="Broken",
        email="broken@example.com",
        imap_host="imap.example.com",
        smtp_host="smtp.example.com",
        username="broken@example.com",
        status="untested",
        frozen=False,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(bad)
    db.commit()

    def fake_sync(db_sess, account, **_kwargs):
        if account.id == bad.id:
            raise RuntimeError("imap down")
        return 3

    monkeypatch.setattr(VoxboxMailService, "sync_account", staticmethod(fake_sync))
    result = VoxboxMailService.sync_all(db)
    assert result["ok"] is False
    assert result["partial"] is True
    assert result["synced_accounts"] == 1
    assert result["fetched"] == 3
    assert result["errors"]
    assert good.email in result["message"] or "Synced 1/2" in result["message"]
