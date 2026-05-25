"""IMAP sync for careers@ CV submissions with Task Reference routing."""

from __future__ import annotations

import email.utils
import logging
import re
from email.header import decode_header
from email.message import Message
from typing import Any

from sqlalchemy.orm import Session

from app.models.service_order import ServiceOrder
from app.services.career_cv_storage_service import save_cv_bytes, storage_key_for
from app.services.career_mailbox_settings_service import CareerMailboxSettingsService
from app.services.interview_cv_parse_service import ParsedCv, parse_uploaded_cv_files
from app.services.interview_intake_service import intake_email_cv_for_order
from app.services.interview_reference_service import extract_reference_id, find_interview_order_by_reference
from app.services.smtp_mailer_service import SmtpMailerError, SmtpMailerService

logger = logging.getLogger(__name__)

CV_EXTENSIONS = (".pdf", ".docx", ".doc", ".txt")
AUTO_REPLY_SUBJECT = "Application not delivered — missing Job Reference Number"
AUTO_REPLY_BODY = (
    "Thank you for your interest.\n\n"
    "We could not deliver your application because your email is missing a valid Job Reference Number.\n\n"
    "Please ask your recruiter for the reference (format VB-INT-XXXXXXXX) and resend your CV to "
    "careers@voxbulk.com with that reference in the subject or message body.\n\n"
    "Best regards,\nVOXBULK Careers"
)


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


def _reply_missing_reference(db: Session, *, to_addr: str, subject: str) -> None:
    if not to_addr or "@" not in to_addr:
        return
    try:
        SmtpMailerService.send_plain(
            db,
            to_addr=to_addr.strip(),
            subject=f"Re: {subject}"[:180] if subject else AUTO_REPLY_SUBJECT,
            body=AUTO_REPLY_BODY,
        )
    except SmtpMailerError as e:
        logger.warning("career_mailbox_auto_reply_failed", extra={"err": str(e)})


def _process_message(db: Session, msg: Message) -> tuple[str, int]:
    subject = _decode_mime(msg.get("Subject"))
    from_hdr = _decode_mime(msg.get("From"))
    reply_to = email.utils.parseaddr(from_hdr)[1] if from_hdr else ""
    body_text = _collect_text(msg)
    ref = extract_reference_id(subject) or extract_reference_id(body_text)
    if not ref:
        _reply_missing_reference(db, to_addr=reply_to, subject=subject)
        return "rejected_no_reference", 0

    order = find_interview_order_by_reference(db, ref)
    if order is None:
        _reply_missing_reference(db, to_addr=reply_to, subject=subject)
        return "rejected_invalid_reference", 0

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
        intake_email_cv_for_order(db, order, parsed=parsed, storage_key=key, sender_email=reply_to or None)
        added += 1
    return "accepted", added


def test_imap_connection(db: Session) -> tuple[bool, str]:
    row = CareerMailboxSettingsService.get_row(db)
    configured, missing = CareerMailboxSettingsService.compute_status(row)
    if not configured:
        return False, "Incomplete settings: " + ", ".join(missing)
    password = CareerMailboxSettingsService.get_decrypted_password(db)
    if not password:
        return False, "Mailbox password not configured"
    user = (row.imap_username or row.mailbox_email or "").strip()
    host = (row.imap_host or "").strip()
    try:
        if row.imap_use_ssl:
            conn = imaplib.IMAP4_SSL(host, int(row.imap_port or 993))
        else:
            conn = imaplib.IMAP4(host, int(row.imap_port or 143))
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
    host = (row.imap_host or "").strip()
    processed = 0
    added_cvs = 0
    rejected = 0

    try:
        if row.imap_use_ssl:
            conn = imaplib.IMAP4_SSL(host, int(row.imap_port or 993))
        else:
            conn = imaplib.IMAP4(host, int(row.imap_port or 143))
        conn.login(user, password or "")
        conn.select("INBOX")
        _typ, data = conn.search(None, "UNSEEN")
        ids = (data[0] or b"").split()
        for num in ids:
            _typ, msg_data = conn.fetch(num, "(RFC822)")
            if not msg_data or not msg_data[0]:
                continue
            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw)
            outcome, count = _process_message(db, msg)
            processed += 1
            if outcome == "accepted":
                added_cvs += count
            elif outcome.startswith("rejected"):
                rejected += 1
            conn.store(num, "+FLAGS", "\\Seen")
        conn.logout()
        message = f"Processed {processed} email(s), {added_cvs} CV(s) added, {rejected} rejected"
        CareerMailboxSettingsService.record_sync_result(db, ok=True, message=message)
        return {"ok": True, "processed": processed, "added_cvs": added_cvs, "rejected": rejected, "message": message}
    except Exception as e:
        msg = f"Sync failed: {e}"
        logger.exception("career_mailbox_sync_failed")
        CareerMailboxSettingsService.record_sync_result(db, ok=False, message=msg)
        return {"ok": False, "message": msg}
