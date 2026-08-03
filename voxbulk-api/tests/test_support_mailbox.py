"""Support mailbox settings and sync helpers."""

from __future__ import annotations

from app.core.database import get_sessionmaker
from app.services.support_mailbox_settings_service import SupportMailboxSettingsService
from app.services.support_mailbox_sync_service import verify_support_imap_connection


def test_support_mailbox_defaults_and_public_dict():
    with get_sessionmaker()() as db:
        row = SupportMailboxSettingsService.get_row(db)
        assert row.mailbox_email == "support@voxbulk.com"
        public = SupportMailboxSettingsService.to_public_dict(db, row)
        assert public["mailbox_email"] == "support@voxbulk.com"
        assert public["configured"] is False
        assert "imap_host" in public["incomplete_fields"]


def test_support_imap_test_incomplete():
    with get_sessionmaker()() as db:
        ok, msg = verify_support_imap_connection(db)
        assert ok is False
        assert "Incomplete" in msg
