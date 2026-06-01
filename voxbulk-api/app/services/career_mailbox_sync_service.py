"""IMAP sync for careers@ CV submissions with Task Reference routing."""

from __future__ import annotations

import email.utils
import imaplib
import logging
import re
from email import message_from_bytes
from email.header import decode_header
from email.message import Message
from typing import Any

from sqlalchemy.orm import Session

from app.models.service_order import ServiceOrder
from app.services.career_cv_storage_service import save_cv_bytes, storage_key_for
from app.services.career_mailbox_settings_service import CareerMailboxSettingsService
from app.services.interview_cv_parse_service import ParsedCv, parse_uploaded_cv_files
from app.services.interview_intake_service import intake_email_cv_for_order
from app.services.interview_cv_email_service import (
    CV_EMAIL_ALLOWED_EXTENSIONS,
    cv_email_window_state,
    format_cv_email_end_label,
)
from app.services.interview_reference_service import extract_reference_id, find_interview_order_by_reference
from app.services.smtp_mailer_service import SmtpMailerError, SmtpMailerService

logger = logging.getLogger(__name__)

CV_EXTENSIONS = CV_EMAIL_ALLOWED_EXTENSIONS
AUTO_REPLY_INVALID_SUBJECT = "Your CV could not be processed"
AUTO_REPLY_INVALID_BODY = (
    "We did not find a valid Interview Task ID in your email. "
    "Please check the instructions and resend with the correct Task ID.\n\n"
    "Your CV was not stored."
)
AUTO_REPLY_CLOSED_SUBJECT = "Collection is closed"


def _decode_mime(value: str | None) -> str:
    if not value:
        return ""
    parts = decode_header(value)
    out: list[str] = []
    for chunk, enc in parts:
        if isinstance(chunk, bytes):
            out.append(chunk.decode(enc or "utf-8", errors="replace"))
        else:
            out.append(str(chunk))
    return " ".join(out).strip()


def _collect_text(msg: Message) -> str:
    chunks: list[str] = []
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            if ctype == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    chunks.append(payload.decode(part.get_content_charset() or "utf-8", errors="replace"))
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            chunks.append(payload.decode(msg.get_content_charset() or "utf-8", errors="replace"))
    return "\n".join(chunks)


def _extract_attachments(msg: Message) -> list[tuple[str, bytes]]:
    files: list[tuple[str, bytes]] = []
    for part in msg.walk():
        if part.get_content_disposition() != "attachment":
            continue
        filename = _decode_mime(part.get_filename())
        if not filename:
            continue
        lower = filename.lower()
        if not any(lower.endswith(ext) for ext in CV_EXTENSIONS):
            continue
        payload = part.get_payload(decode=True)
        if payload and len(payload) <= 12 * 1024 * 1024:
            files.append((filename, payload))
    return files


def _send_auto_reply(db: Session, *, to_addr: str, subject: str, body: str) -> None:
    if not to_addr or "@" not in to_addr:
        return
    try:
        SmtpMailerService.send_plain(
            db,
            to_addr=to_addr.strip(),
            subject=subject[:180],
            body=body,
        )
    except SmtpMailerError as e:
        logger.warning("career_mailbox_auto_reply_failed", extra={"err": str(e)})


def _reply_invalid_reference(db: Session, *, to_addr: str) -> None:
    _send_auto_reply(db, to_addr=to_addr, subject=AUTO_REPLY_INVALID_SUBJECT, body=AUTO_REPLY_INVALID_BODY)


def _reply_collection_closed(db: Session, *, to_addr: str, order: ServiceOrder) -> None:
    end_label = format_cv_email_end_label(order)
    body = (
        f"CV collection for this task ended on {end_label}. Your CV cannot be added.\n\n"
        "Your CV was not stored."
    )
    _send_auto_reply(db, to_addr=to_addr, subject=AUTO_REPLY_CLOSED_SUBJECT, body=body)


def _process_message(db: Session, msg: Message) -> tuple[str, int]:
    subject = _decode_mime(msg.get("Subject"))
    from_hdr = _decode_mime(msg.get("From"))
    reply_to = email.utils.parseaddr(from_hdr)[1] if from_hdr else ""
    body_text = _collect_text(msg)
    ref = extract_reference_id(subject) or extract_reference_id(body_text)
    if not ref:
        _reply_invalid_reference(db, to_addr=reply_to)
        return "rejected_no_reference", 0

    order = find_interview_order_by_reference(db, ref)
    if order is None:
        _reply_invalid_reference(db, to_addr=reply_to)
        return "rejected_invalid_reference", 0

    window = cv_email_window_state(order)
    if window == "disabled":
        return "skipped_email_disabled", 0
    if window == "before":
        return "skipped_before_window", 0
    if window == "after":
        _reply_collection_closed(db, to_addr=reply_to, order=order)
        return "rejected_window_closed", 0

    attachments = _extract_attachments(msg)
    if not attachments:
        return "skipped_no_attachments", 0

    added = 0
    for filename, content in attachments:
        parsed_list = parse_uploaded_cv_files([(filename, content)])
        if not parsed_list:
            continue
        parsed: ParsedCv = parsed_list[0]
        key = storage_key_for(org_id=order.org_id, order_id=order.id, filename=filename)
        save_cv_bytes(storage_key=key, content=content)
        _order, recipient = intake_email_cv_for_order(
            db, order, parsed=parsed, storage_key=key, sender_email=reply_to or None
        )
        order = _order
        from app.services.interview_email_ats_service import auto_ats_after_email_cv

        auto_ats_after_email_cv(db, order, recipient, is_update=True)
        added += 1
    return "accepted", added


def _connect_imap(row) -> imaplib.IMAP4:
    host = (row.imap_host or "").strip()
    port = int(row.imap_port or (993 if row.imap_use_ssl else 143))
    if row.imap_use_ssl:
        return imaplib.IMAP4_SSL(host, port)
    conn = imaplib.IMAP4(host, port)
    if getattr(row, "imap_use_tls", False):
        conn.starttls()
    return conn


def test_imap_connection(db: Session) -> tuple[bool, str]:
    row = CareerMailboxSettingsService.get_row(db)
    configured, missing = CareerMailboxSettingsService.compute_status(row)
    if not configured:
        return False, "Incomplete settings: " + ", ".join(missing)
    password = CareerMailboxSettingsService.get_decrypted_password(db)
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


def sync_career_mailbox(db: Session) -> dict[str, Any]:
    row = CareerMailboxSettingsService.get_row(db)
    if not row.is_enabled:
        CareerMailboxSettingsService.record_sync_result(db, ok=True, message="Sync disabled")
        return {"ok": True, "skipped": True, "message": "Sync disabled"}

    configured, missing = CareerMailboxSettingsService.compute_status(row)
    if not configured:
        CareerMailboxSettingsService.record_sync_result(db, ok=False, message="Incomplete: " + ", ".join(missing))
        return {"ok": False, "message": "Incomplete settings"}

    password = CareerMailboxSettingsService.get_decrypted_password(db)
    user = (row.imap_username or row.mailbox_email or "").strip()
    processed = 0
    added_cvs = 0
    rejected = 0
    deleted = 0

    try:
        conn = _connect_imap(row)
        conn.login(user, password or "")
        conn.select("INBOX")
        _typ, data = conn.search(None, "UNSEEN")
        ids = (data[0] or b"").split()
        for num in ids:
            _typ, msg_data = conn.fetch(num, "(RFC822)")
            if not msg_data or not msg_data[0]:
                continue
            raw = msg_data[0][1]
            msg = message_from_bytes(raw)
            outcome, count = _process_message(db, msg)
            processed += 1
            if outcome == "accepted":
                added_cvs += count
            elif outcome.startswith("rejected"):
                rejected += 1
            conn.store(num, "+FLAGS", "\\Deleted")
            deleted += 1
        if deleted:
            conn.expunge()
        conn.logout()
        message = f"Processed {processed} email(s), {added_cvs} CV(s) added, {rejected} rejected, {deleted} deleted from inbox"
        CareerMailboxSettingsService.record_sync_result(db, ok=True, message=message)
        return {"ok": True, "processed": processed, "added_cvs": added_cvs, "rejected": rejected, "deleted": deleted, "message": message}
    except Exception as e:
        msg = f"Sync failed: {e}"
        logger.exception("career_mailbox_sync_failed")
        CareerMailboxSettingsService.record_sync_result(db, ok=False, message=msg)
        return {"ok": False, "message": msg}
