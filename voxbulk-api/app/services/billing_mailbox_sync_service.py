"""IMAP connectivity checks for billing@voxbulk.com mailbox."""

from __future__ import annotations

import imaplib
import logging
from typing import Any

from sqlalchemy.orm import Session

from app.services.billing_mailbox_settings_service import BillingMailboxSettingsService

logger = logging.getLogger(__name__)


def _connect_imap(row) -> imaplib.IMAP4:
    host = (row.imap_host or "").strip()
    port = int(row.imap_port or (993 if row.imap_use_ssl else 143))
    if row.imap_use_ssl:
        return imaplib.IMAP4_SSL(host, port)
    conn = imaplib.IMAP4(host, port)
    if getattr(row, "imap_use_tls", False):
        conn.starttls()
    return conn


def verify_billing_imap_connection(db: Session) -> tuple[bool, str]:
    row = BillingMailboxSettingsService.get_row(db)
    configured, missing = BillingMailboxSettingsService.compute_status(row)
    if not configured:
        return False, "Incomplete settings: " + ", ".join(missing)
    password = BillingMailboxSettingsService.get_decrypted_password(db)
    if not password:
        return False, "Mailbox password not configured"
    user = (row.imap_username or row.mailbox_email or "").strip()
    try:
        conn = _connect_imap(row)
        conn.login(user, password)
        conn.logout()
        return True, "Connected successfully"
    except Exception as e:
        return False, f"Connection failed: {e}"


def sync_billing_mailbox(db: Session) -> dict[str, Any]:
    row = BillingMailboxSettingsService.get_row(db)
    if not row.is_enabled:
        BillingMailboxSettingsService.record_sync_result(db, ok=True, message="Sync disabled")
        return {"ok": True, "skipped": True, "message": "Sync disabled"}

    configured, missing = BillingMailboxSettingsService.compute_status(row)
    if not configured:
        BillingMailboxSettingsService.record_sync_result(db, ok=False, message="Incomplete: " + ", ".join(missing))
        return {"ok": False, "message": "Incomplete settings"}

    password = BillingMailboxSettingsService.get_decrypted_password(db)
    user = (row.imap_username or row.mailbox_email or "").strip()
    try:
        conn = _connect_imap(row)
        conn.login(user, password)
        status, data = conn.select("INBOX", readonly=True)
        unread = 0
        if status == "OK" and data:
            try:
                unread = int(data[0])
            except (TypeError, ValueError):
                unread = 0
        conn.logout()
        msg = f"Inbox OK — {unread} message(s)"
        BillingMailboxSettingsService.record_sync_result(db, ok=True, message=msg)
        return {"ok": True, "message": msg, "inbox_count": unread}
    except Exception as e:
        err = f"Sync failed: {e}"
        logger.warning("billing_mailbox_sync_failed err=%s", e)
        BillingMailboxSettingsService.record_sync_result(db, ok=False, message=err)
        return {"ok": False, "message": err}
