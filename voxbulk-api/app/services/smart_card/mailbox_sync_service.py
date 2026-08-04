"""Smart Card QR mailbox — SMTP test, IMAP test, sync unseen mail → support tickets."""

from __future__ import annotations

import email.utils
import imaplib
import logging
import re
import smtplib
import ssl
from email import message_from_bytes
from email.header import decode_header
from email.message import EmailMessage, Message
from email.utils import formataddr
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.membership import OrganisationMembership
from app.models.user import User
from app.services.smart_card.mailbox_settings_service import (
    DEFAULT_FROM_NAME,
    DEFAULT_MAILBOX,
    SmartCardMailboxSettingsService,
)
from app.services.smtp_mailer_service import SmtpMailerError, SmtpMailerService
from app.services.support_ticket_service import SupportTicketService

logger = logging.getLogger(__name__)

_PROCESSED_UID_RE = re.compile(r"uids=\[([^\]]*)\]")


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
    return "\n".join(chunks).strip()


def _connect_imap(row) -> imaplib.IMAP4:
    host = (row.imap_host or "").strip()
    port = int(row.imap_port or (993 if row.imap_use_ssl else 143))
    if row.imap_use_ssl:
        return imaplib.IMAP4_SSL(host, port)
    conn = imaplib.IMAP4(host, port)
    if getattr(row, "imap_use_tls", False):
        conn.starttls()
    return conn


def _parse_processed_uids(message: str | None) -> set[str]:
    if not message:
        return set()
    m = _PROCESSED_UID_RE.search(message)
    if not m:
        return set()
    raw = m.group(1).strip()
    if not raw:
        return set()
    return {p.strip() for p in raw.split(",") if p.strip()}


def _format_sync_message(*, processed: int, tickets: int, uids: list[str], extra: str = "") -> str:
    uid_tail = ",".join(uids[-40:])
    base = f"Synced {processed} email(s), {tickets} ticket(s). uids=[{uid_tail}]"
    if extra:
        return f"{base} {extra}"[:500]
    return base[:500]


def _resolve_inbox_actor(db: Session) -> tuple[str, str]:
    """Platform org + a user for inbound mailbox tickets (org-scoped SupportTicket)."""
    from app.services.sales_automation_service import SalesAutomationService

    org_id = SalesAutomationService._platform_org_id(db)
    if not org_id:
        raise RuntimeError("No organisation available for Smart Card inbox tickets")

    owner = db.execute(
        select(OrganisationMembership.user_id)
        .where(
            OrganisationMembership.org_id == org_id,
            OrganisationMembership.role.in_(["owner", "manager"]),
        )
        .limit(1)
    ).scalar_one_or_none()
    if owner:
        return str(org_id), str(owner)

    any_user = db.execute(
        select(OrganisationMembership.user_id).where(OrganisationMembership.org_id == org_id).limit(1)
    ).scalar_one_or_none()
    if any_user:
        return str(org_id), str(any_user)

    fallback_user = db.execute(select(User.id).order_by(User.created_at.asc()).limit(1)).scalar_one_or_none()
    if not fallback_user:
        raise RuntimeError("No user available for Smart Card inbox tickets")
    return str(org_id), str(fallback_user)


def _send_via_dedicated_smtp(
    *,
    host: str,
    port: int,
    username: str | None,
    password: str | None,
    from_email: str,
    from_name: str,
    to_addr: str,
    subject: str,
    body: str,
) -> None:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr((from_name, from_email)) if from_name else from_email
    msg["To"] = to_addr
    msg.set_content(body or "")

    from app.core.config import get_settings

    settings = get_settings()
    insecure = bool(settings.smtp_ssl_insecure)
    if insecure:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    else:
        try:
            import truststore

            ctx = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        except Exception:
            ctx = ssl.create_default_context()

    use_ssl = int(port) == 465
    try:
        if use_ssl:
            with smtplib.SMTP_SSL(host, port, context=ctx, timeout=30) as server:
                if username and password:
                    server.login(username, password)
                server.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=30) as server:
                server.ehlo()
                server.starttls(context=ctx)
                server.ehlo()
                if username and password:
                    server.login(username, password)
                server.send_message(msg)
    except smtplib.SMTPAuthenticationError as e:
        raise SmtpMailerError(
            f"SMTP authentication failed: {e.smtp_code} {e.smtp_error.decode(errors='replace')}"
        ) from e
    except smtplib.SMTPException as e:
        raise SmtpMailerError(f"SMTP error: {e}") from e
    except OSError as e:
        raise SmtpMailerError(f"Network error contacting SMTP server: {e}") from e


def test_smtp_send(db: Session, *, to_email: str) -> dict[str, Any]:
    to_addr = (to_email or "").strip()
    if not to_addr or "@" not in to_addr:
        raise SmtpMailerError("Invalid recipient email address.")

    row = SmartCardMailboxSettingsService.get_row(db)
    from_name, from_email = SmartCardMailboxSettingsService.from_address(db)
    smtp_user = (row.smtp_username or from_email or "").strip() or None
    smtp_pwd = SmartCardMailboxSettingsService.get_decrypted_password(db)
    subject = "VOXBULK / Smart Card QR mailbox test"
    body = (
        "This is a test message from the Smart Card QR mailbox (smartqr@voxbulk.com).\n\n"
        "If you received this email, outbound mail is working."
    )

    dedicated_host = (row.smtp_host or "").strip()
    if dedicated_host:
        port = int(row.smtp_port or 587)
        _send_via_dedicated_smtp(
            host=dedicated_host,
            port=port,
            username=smtp_user,
            password=smtp_pwd,
            from_email=from_email,
            from_name=from_name,
            to_addr=to_addr,
            subject=subject,
            body=body,
        )
        return {"ok": True, "detail": f"Test email sent to {to_addr} via {dedicated_host}.", "via": "dedicated"}

    SmtpMailerService.send_plain(
        db,
        to_addr=to_addr,
        subject=subject,
        body=body,
        from_email=from_email or DEFAULT_MAILBOX,
        from_name=from_name or DEFAULT_FROM_NAME,
        smtp_username=smtp_user if smtp_pwd else None,
        smtp_password=smtp_pwd,
    )
    return {"ok": True, "detail": f"Test email sent to {to_addr} via platform SMTP.", "via": "platform"}


def test_imap(db: Session) -> dict[str, Any]:
    row = SmartCardMailboxSettingsService.get_row(db)
    configured, missing = SmartCardMailboxSettingsService.compute_imap_status(row)
    if not configured:
        return {"ok": False, "detail": "Incomplete IMAP settings: " + ", ".join(missing)}
    password = SmartCardMailboxSettingsService.get_decrypted_imap_password(db)
    if not password:
        return {"ok": False, "detail": "IMAP password not configured"}
    user = (row.imap_username or row.mailbox_email or "").strip()
    try:
        conn = _connect_imap(row)
        conn.login(user, password)
        status, data = conn.select("INBOX", readonly=True)
        count = 0
        if status == "OK" and data:
            try:
                count = int(data[0])
            except (TypeError, ValueError):
                count = 0
        conn.logout()
        return {"ok": True, "detail": f"Connected — INBOX has {count} message(s).", "inbox_count": count}
    except Exception as e:
        return {"ok": False, "detail": f"Connection failed: {e}"}


def sync_to_tickets(db: Session) -> dict[str, Any]:
    row = SmartCardMailboxSettingsService.get_row(db)
    if not row.is_enabled:
        SmartCardMailboxSettingsService.record_imap_sync(db, message="Sync disabled")
        return {"ok": True, "skipped": True, "message": "Sync disabled"}

    configured, missing = SmartCardMailboxSettingsService.compute_imap_status(row)
    if not configured:
        msg = "Incomplete: " + ", ".join(missing)
        SmartCardMailboxSettingsService.record_imap_sync(db, message=msg)
        return {"ok": False, "message": msg}

    password = SmartCardMailboxSettingsService.get_decrypted_imap_password(db)
    if not password:
        msg = "IMAP password not configured"
        SmartCardMailboxSettingsService.record_imap_sync(db, message=msg)
        return {"ok": False, "message": msg}

    try:
        org_id, user_id = _resolve_inbox_actor(db)
    except RuntimeError as e:
        msg = str(e)
        SmartCardMailboxSettingsService.record_imap_sync(db, message=msg)
        return {"ok": False, "message": msg}

    user = (row.imap_username or row.mailbox_email or "").strip()
    already = _parse_processed_uids(row.imap_last_sync_message)
    processed = 0
    tickets = 0
    new_uids: list[str] = list(already)[-20:]

    try:
        conn = _connect_imap(row)
        conn.login(user, password)
        conn.select("INBOX")
        _typ, data = conn.uid("search", None, "UNSEEN")
        ids = (data[0] or b"").split() if data else []
        for num in ids:
            uid = num.decode() if isinstance(num, bytes) else str(num)
            if uid in already:
                continue
            _typ, msg_data = conn.uid("fetch", num, "(RFC822)")
            if not msg_data or not msg_data[0]:
                continue
            raw = msg_data[0][1]
            if not isinstance(raw, (bytes, bytearray)):
                continue
            msg = message_from_bytes(raw)
            subject = _decode_mime(msg.get("Subject")) or "(no subject)"
            from_hdr = _decode_mime(msg.get("From"))
            from_addr = email.utils.parseaddr(from_hdr)[1] if from_hdr else ""
            body_text = _collect_text(msg) or "(empty body)"
            ticket_body = (
                f"From: {from_hdr or from_addr or 'unknown'}\n"
                f"Subject: {subject}\n"
                f"IMAP UID: {uid}\n\n"
                f"{body_text}"
            )[:8000]
            staff_note = f"Inbound via smartqr mailbox UID {uid}"
            try:
                SupportTicketService.create_ticket(
                    db,
                    org_id=org_id,
                    user_id=user_id,
                    category="smart_card",
                    subject=f"[Smart Card] {subject}"[:240],
                    message=ticket_body,
                    priority="normal",
                    channel="imap",
                    staff_note=staff_note,
                )
                tickets += 1
            except Exception:
                logger.exception("smart_card_mailbox_ticket_failed uid=%s", uid)
                continue
            processed += 1
            new_uids.append(uid)
            already.add(uid)
            try:
                conn.uid("store", num, "+FLAGS", "\\Seen")
            except Exception:
                logger.warning("smart_card_mailbox_mark_seen_failed uid=%s", uid)

        conn.logout()
        message = _format_sync_message(processed=processed, tickets=tickets, uids=new_uids)
        SmartCardMailboxSettingsService.record_imap_sync(db, message=message)
        return {
            "ok": True,
            "processed": processed,
            "tickets": tickets,
            "message": message,
        }
    except Exception as e:
        msg = f"Sync failed: {e}"
        logger.exception("smart_card_mailbox_sync_failed")
        SmartCardMailboxSettingsService.record_imap_sync(db, message=msg)
        return {"ok": False, "message": msg}
