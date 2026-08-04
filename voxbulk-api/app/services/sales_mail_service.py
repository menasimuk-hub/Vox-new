"""Sales mail service — IMAP sync, SMTP send, labels, contacts for salesmen."""

from __future__ import annotations

import email.utils
import imaplib
import json
import logging
import re
import smtplib
import ssl
import uuid
from datetime import datetime
from email import message_from_bytes
from email.header import decode_header
from email.message import EmailMessage, Message
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.encryption import get_encryptor
from app.models.sales_mail import SalesMailContact, SalesMailLabel, SalesMailMessage
from app.models.sales_rep import SalesRep

logger = logging.getLogger(__name__)


class SalesMailServiceError(RuntimeError):
    pass


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


def _strip_html(html: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?>.*?(</\1>)", " ", html)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</p\s*>", "\n\n", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _collect_bodies(msg: Message) -> tuple[str, str]:
    text_parts: list[str] = []
    html_parts: list[str] = []
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = str(part.get("Content-Disposition") or "")
            if "attachment" in disp.lower():
                continue
            payload = part.get_payload(decode=True)
            if not payload:
                continue
            charset = part.get_content_charset() or "utf-8"
            decoded = payload.decode(charset, errors="replace")
            if ctype == "text/plain":
                text_parts.append(decoded)
            elif ctype == "text/html":
                html_parts.append(decoded)
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            decoded = payload.decode(charset, errors="replace")
            if msg.get_content_type() == "text/html":
                html_parts.append(decoded)
            else:
                text_parts.append(decoded)
    text = "\n".join(text_parts).strip()
    html = "\n".join(html_parts).strip()
    if not text and html:
        text = _strip_html(html)
    return text[:200000], html[:500000]


def _has_attachment(msg: Message) -> bool:
    if not msg.is_multipart():
        return False
    for part in msg.walk():
        disp = str(part.get("Content-Disposition") or "")
        if "attachment" in disp.lower():
            return True
        if part.get_filename():
            return True
    return False


def get_mailbox_status(db: Session, sales_rep_id: str) -> dict[str, Any]:
    """Return mailbox configuration status for a salesman."""
    rep = db.scalar(select(SalesRep).where(SalesRep.id == sales_rep_id))
    if not rep:
        raise SalesMailServiceError("Sales rep not found")

    has_imap = bool(rep.imap_host and rep.imap_username and rep.imap_password_enc)
    has_smtp = bool(rep.smtp_host and rep.smtp_username and rep.smtp_password_enc)
    return {
        "configured": has_imap and has_smtp,
        "has_imap": has_imap,
        "has_smtp": has_smtp,
        "signature_preview": rep.email_signature[:200] if rep.email_signature else "",
        "promo_code": rep.promo_code or "",
    }


def list_labels(db: Session, sales_rep_id: str) -> list[dict[str, Any]]:
    """List all labels for a salesman."""
    labels = db.scalars(
        select(SalesMailLabel)
        .where(SalesMailLabel.sales_rep_id == sales_rep_id)
        .order_by(SalesMailLabel.name)
    ).all()
    return [{"id": lb.id, "name": lb.name, "color": lb.color} for lb in labels]


def create_label(db: Session, sales_rep_id: str, name: str, color: str = "#3b82f6") -> dict[str, Any]:
    """Create a new label."""
    lb = SalesMailLabel(
        id=str(uuid.uuid4()),
        sales_rep_id=sales_rep_id,
        name=name.strip(),
        color=color,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(lb)
    db.commit()
    db.refresh(lb)
    return {"id": lb.id, "name": lb.name, "color": lb.color}


def delete_label(db: Session, sales_rep_id: str, label_id: str) -> None:
    """Delete a label."""
    lb = db.scalar(select(SalesMailLabel).where(SalesMailLabel.id == label_id, SalesMailLabel.sales_rep_id == sales_rep_id))
    if lb:
        db.delete(lb)
        db.commit()


def list_contacts(db: Session, sales_rep_id: str) -> list[dict[str, Any]]:
    """List all contacts for a salesman."""
    contacts = db.scalars(
        select(SalesMailContact)
        .where(SalesMailContact.sales_rep_id == sales_rep_id)
        .order_by(SalesMailContact.name)
    ).all()
    return [
        {
            "id": c.id,
            "email": c.email,
            "name": c.name,
            "company": c.company,
            "sales_customer_id": c.sales_customer_id,
        }
        for c in contacts
    ]


def sync_messages_from_imap(db: Session, sales_rep_id: str, folder: str = "INBOX", limit: int = 50) -> dict[str, Any]:
    """Sync messages from IMAP for a salesman."""
    rep = db.scalar(select(SalesRep).where(SalesRep.id == sales_rep_id))
    if not rep:
        raise SalesMailServiceError("Sales rep not found")
    if not rep.imap_host or not rep.imap_username or not rep.imap_password_enc:
        raise SalesMailServiceError("IMAP not configured")

    encryptor = get_encryptor()
    try:
        password = encryptor.decrypt_str(rep.imap_password_enc)
    except ValueError as e:
        raise SalesMailServiceError("Failed to decrypt IMAP password") from e

    ssl_context = ssl.create_default_context()
    try:
        if rep.imap_use_ssl:
            conn = imaplib.IMAP4_SSL(rep.imap_host, rep.imap_port, ssl_context=ssl_context)
        else:
            conn = imaplib.IMAP4(rep.imap_host, rep.imap_port)
            if rep.imap_use_tls:
                conn.starttls(ssl_context=ssl_context)
        conn.login(rep.imap_username, password)
        conn.select(folder, readonly=True)

        _, msg_nums = conn.search(None, "ALL")
        if not msg_nums or not msg_nums[0]:
            conn.logout()
            return {"synced": 0}

        uids = msg_nums[0].split()
        fetch_uids = uids[-limit:] if len(uids) > limit else uids

        synced = 0
        for uid in fetch_uids:
            _, data = conn.fetch(uid, "(RFC822)")
            if not data or not data[0]:
                continue
            raw_email = data[0][1]
            msg = message_from_bytes(raw_email)

            message_id = msg.get("Message-ID", "").strip()
            existing = db.scalar(
                select(SalesMailMessage).where(
                    SalesMailMessage.sales_rep_id == sales_rep_id,
                    SalesMailMessage.message_id == message_id,
                )
            )
            if existing:
                continue

            from_header = msg.get("From", "")
            from_email_parsed = email.utils.parseaddr(from_header)
            from_name = _decode_mime(from_email_parsed[0])
            from_email = from_email_parsed[1]

            subject = _decode_mime(msg.get("Subject", ""))
            to_email = _decode_mime(msg.get("To", ""))
            cc_email = _decode_mime(msg.get("Cc", ""))
            date_str = msg.get("Date", "")
            date = email.utils.parsedate_to_datetime(date_str) if date_str else datetime.utcnow()

            text, html = _collect_bodies(msg)
            has_att = _has_attachment(msg)

            mail_msg = SalesMailMessage(
                id=str(uuid.uuid4()),
                sales_rep_id=sales_rep_id,
                folder=folder,
                uid=uid.decode("utf-8") if isinstance(uid, bytes) else str(uid),
                message_id=message_id,
                from_email=from_email,
                from_name=from_name,
                to_email=to_email,
                cc_email=cc_email,
                subject=subject,
                body_text=text,
                body_html=html,
                has_attachments=has_att,
                direction="received",
                is_read=False,
                is_starred=False,
                is_deleted=False,
                date=date,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            db.add(mail_msg)
            synced += 1

        db.commit()
        conn.logout()
        return {"synced": synced}
    except imaplib.IMAP4.error as e:
        raise SalesMailServiceError(f"IMAP error: {e}") from e
    except Exception as e:
        raise SalesMailServiceError(f"IMAP sync failed: {e}") from e


def list_messages(
    db: Session, sales_rep_id: str, folder: str = "INBOX", label: str | None = None, limit: int = 50
) -> list[dict[str, Any]]:
    """List messages for a salesman. folder may be INBOX|Sent|Starred|Trash or an IMAP folder name."""
    query = select(SalesMailMessage).where(SalesMailMessage.sales_rep_id == sales_rep_id)
    folder_key = (folder or "INBOX").strip()
    if folder_key.lower() == "starred":
        query = query.where(SalesMailMessage.is_starred.is_(True), SalesMailMessage.is_deleted.is_(False))
    elif folder_key.lower() == "trash":
        query = query.where(SalesMailMessage.is_deleted.is_(True))
    elif folder_key.lower() == "sent":
        query = query.where(
            SalesMailMessage.is_deleted.is_(False),
            or_(
                SalesMailMessage.direction == "sent",
                SalesMailMessage.folder.in_(["Sent", "SENT", "INBOX.Sent"]),
            ),
        )
    else:
        query = query.where(
            SalesMailMessage.is_deleted.is_(False),
            SalesMailMessage.folder == folder_key,
        )
    if label:
        query = query.where(SalesMailMessage.labels_json.contains(label))
    query = query.order_by(SalesMailMessage.date.desc()).limit(limit)

    messages = db.scalars(query).all()
    return [
        {
            "id": m.id,
            "from_email": m.from_email,
            "from_name": m.from_name,
            "to_email": m.to_email,
            "subject": m.subject,
            "preview": (m.body_text or "")[:140],
            "date": m.date.isoformat() if m.date else None,
            "is_read": m.is_read,
            "is_starred": m.is_starred,
            "has_attachments": m.has_attachments,
            "direction": m.direction,
        }
        for m in messages
    ]


def get_message(db: Session, sales_rep_id: str, message_id: str) -> dict[str, Any]:
    """Get a single message detail."""
    msg = db.scalar(
        select(SalesMailMessage).where(SalesMailMessage.id == message_id, SalesMailMessage.sales_rep_id == sales_rep_id)
    )
    if not msg:
        raise SalesMailServiceError("Message not found")

    if not msg.is_read:
        msg.is_read = True
        db.commit()

    return {
        "id": msg.id,
        "from_email": msg.from_email,
        "from_name": msg.from_name,
        "to_email": msg.to_email,
        "cc_email": msg.cc_email,
        "subject": msg.subject,
        "body_text": msg.body_text,
        "body_html": msg.body_html,
        "has_attachments": msg.has_attachments,
        "date": msg.date.isoformat() if msg.date else None,
        "is_read": msg.is_read,
        "is_starred": msg.is_starred,
        "labels": json.loads(msg.labels_json) if msg.labels_json else [],
    }


def send_email(
    db: Session,
    sales_rep_id: str,
    to: str,
    subject: str,
    body_html: str,
    body_text: str | None = None,
    insert_promo: bool = False,
) -> dict[str, Any]:
    """Send an email via SMTP for a salesman."""
    rep = db.scalar(select(SalesRep).where(SalesRep.id == sales_rep_id))
    if not rep:
        raise SalesMailServiceError("Sales rep not found")
    if not rep.smtp_host or not rep.smtp_username or not rep.smtp_password_enc:
        raise SalesMailServiceError("SMTP not configured")

    encryptor = get_encryptor()
    try:
        password = encryptor.decrypt_str(rep.smtp_password_enc)
    except ValueError as e:
        raise SalesMailServiceError("Failed to decrypt SMTP password") from e

    final_body_html = body_html
    final_body_text = body_text or _strip_html(body_html)

    if insert_promo and rep.promo_code:
        promo_line = f"<p><strong>Use promo code:</strong> <code>{rep.promo_code}</code></p>"
        final_body_html = f"{body_html}\n{promo_line}"
        final_body_text = f"{final_body_text}\n\nUse promo code: {rep.promo_code}"

    if rep.email_signature:
        final_body_html = f"{final_body_html}\n<div>{rep.email_signature}</div>"
        final_body_text = f"{final_body_text}\n\n{_strip_html(rep.email_signature)}"

    msg = MIMEMultipart("alternative")
    msg["From"] = rep.smtp_username
    msg["To"] = to
    msg["Subject"] = subject
    msg["Message-ID"] = email.utils.make_msgid()
    msg.attach(MIMEText(final_body_text, "plain", "utf-8"))
    msg.attach(MIMEText(final_body_html, "html", "utf-8"))

    try:
        if rep.smtp_use_ssl:
            server = smtplib.SMTP_SSL(rep.smtp_host, rep.smtp_port, context=ssl.create_default_context())
        else:
            server = smtplib.SMTP(rep.smtp_host, rep.smtp_port)
            if rep.smtp_use_tls:
                server.starttls(context=ssl.create_default_context())
        server.login(rep.smtp_username, password)
        server.sendmail(rep.smtp_username, to, msg.as_string())
        server.quit()

        sent_msg = SalesMailMessage(
            id=str(uuid.uuid4()),
            sales_rep_id=sales_rep_id,
            folder="Sent",
            message_id=msg["Message-ID"],
            from_email=rep.smtp_username,
            from_name=rep.name,
            to_email=to,
            subject=subject,
            body_text=final_body_text,
            body_html=final_body_html,
            has_attachments=False,
            direction="sent",
            is_read=True,
            is_starred=False,
            is_deleted=False,
            date=datetime.utcnow(),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(sent_msg)
        db.commit()

        return {"id": sent_msg.id, "message": "Email sent successfully"}
    except smtplib.SMTPException as e:
        raise SalesMailServiceError(f"SMTP error: {e}") from e
    except Exception as e:
        raise SalesMailServiceError(f"Failed to send email: {e}") from e


def polish_body_with_ai(body: str) -> str:
    """AI polish body text (stub for now — can integrate OpenAI later)."""
    return body.strip()
