"""Billing mailbox settings and IMAP test helpers."""

from __future__ import annotations

from app.core.database import get_sessionmaker
from app.services.billing_mailbox_settings_service import BillingMailboxSettingsService
from app.services.billing_mailbox_sync_service import verify_billing_imap_connection


def test_billing_mailbox_defaults_and_public_dict():
    with get_sessionmaker()() as db:
        row = BillingMailboxSettingsService.get_row(db)
        assert row.mailbox_email == "billing@voxbulk.com"
        public = BillingMailboxSettingsService.to_public_dict(db, row)
        assert public["mailbox_email"] == "billing@voxbulk.com"
        assert public["configured"] is False
        assert "imap_host" in public["incomplete_fields"]


def test_billing_imap_test_incomplete():
    with get_sessionmaker()() as db:
        ok, msg = verify_billing_imap_connection(db)
        assert ok is False
        assert "Incomplete" in msg
