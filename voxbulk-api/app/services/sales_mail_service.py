"""Sales mail service — IMAP sync, SMTP send, labels, contacts for salesmen."""

from __future__ import annotations

import email.utils
import hashlib
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
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email import encoders
import base64
from typing import Any, Literal

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.encryption import get_encryptor
from app.models.sales_mail import SalesMailContact, SalesMailLabel, SalesMailMessage
from app.models.sales_rep import SalesRep

logger = logging.getLogger(__name__)

SalesMailEscalateTarget = Literal["support", "billing"]

ESCALATE_TARGETS: dict[str, dict[str, str]] = {
    "support": {"to": "support@voxbulk.com", "category": "technical", "label": "Support"},
    "billing": {"to": "billing@voxbulk.com", "category": "invoices", "label": "Billing"},
}
ESCALATE_MESSAGE_ID_DOMAIN = "escalate.voxbulk.com"
ESCALATE_HEADER = "X-Voxbulk-Escalation"


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
        "smtp_username": rep.smtp_username or "",
        "smtp_host": rep.smtp_host or "",
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
    """Contacts = mailbox address book + all sales customers with an email (follow-up list)."""
    from app.models.sales_rep import SalesCustomer
    from app.services.sales_rep_service import SalesRepService

    contacts = db.scalars(
        select(SalesMailContact)
        .where(SalesMailContact.sales_rep_id == sales_rep_id)
        .order_by(SalesMailContact.name)
    ).all()
    by_email: dict[str, dict[str, Any]] = {}
    for c in contacts:
        email = (c.email or "").strip().lower()
        if not email:
            continue
        by_email[email] = {
            "id": c.id,
            "email": c.email,
            "name": c.name,
            "company": c.company,
            "sales_customer_id": c.sales_customer_id,
            "stage": None,
            "source": "contact",
        }

    customers = db.scalars(
        select(SalesCustomer)
        .where(SalesCustomer.sales_rep_id == str(sales_rep_id))
        .order_by(SalesCustomer.created_at.desc())
    ).all()
    for cust in customers:
        email = (cust.email or "").strip().lower()
        if not email:
            continue
        stage = SalesRepService._derive_stage(cust)
        # Follow-up pool = everyone not yet won
        if stage == "won":
            continue
        existing = by_email.get(email)
        if existing:
            existing["name"] = existing["name"] or cust.full_name or cust.contact_person
            existing["company"] = existing["company"] or cust.company_name
            existing["sales_customer_id"] = existing["sales_customer_id"] or cust.id
            existing["stage"] = stage
            existing["source"] = "customer"
        else:
            by_email[email] = {
                "id": cust.id,
                "email": cust.email,
                "name": cust.full_name or cust.contact_person,
                "company": cust.company_name,
                "sales_customer_id": cust.id,
                "stage": stage,
                "source": "customer",
            }

    items = list(by_email.values())
    items.sort(key=lambda r: (str(r.get("name") or r.get("email") or "").lower()))
    return items


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
        "is_deleted": msg.is_deleted,
        "direction": msg.direction,
        "labels": json.loads(msg.labels_json) if msg.labels_json else [],
    }


def patch_message(
    db: Session,
    sales_rep_id: str,
    message_id: str,
    *,
    is_starred: bool | None = None,
    is_deleted: bool | None = None,
    is_read: bool | None = None,
) -> dict[str, Any]:
    msg = db.scalar(
        select(SalesMailMessage).where(SalesMailMessage.id == message_id, SalesMailMessage.sales_rep_id == sales_rep_id)
    )
    if not msg:
        raise SalesMailServiceError("Message not found")
    if is_starred is not None:
        msg.is_starred = bool(is_starred)
    if is_deleted is not None:
        msg.is_deleted = bool(is_deleted)
    if is_read is not None:
        msg.is_read = bool(is_read)
    msg.updated_at = datetime.utcnow()
    db.commit()
    return get_message(db, sales_rep_id, message_id)


def delete_messages(db: Session, sales_rep_id: str, message_ids: list[str], *, permanent: bool = False) -> dict[str, Any]:
    ids = [str(i).strip() for i in (message_ids or []) if str(i).strip()]
    if not ids:
        return {"deleted": 0}
    rows = list(
        db.scalars(
            select(SalesMailMessage).where(
                SalesMailMessage.sales_rep_id == sales_rep_id,
                SalesMailMessage.id.in_(ids),
            )
        ).all()
    )
    count = 0
    for msg in rows:
        if permanent or msg.is_deleted:
            db.delete(msg)
        else:
            msg.is_deleted = True
            msg.updated_at = datetime.utcnow()
        count += 1
    db.commit()
    return {"deleted": count}


def empty_trash(db: Session, sales_rep_id: str) -> dict[str, Any]:
    rows = list(
        db.scalars(
            select(SalesMailMessage).where(
                SalesMailMessage.sales_rep_id == sales_rep_id,
                SalesMailMessage.is_deleted.is_(True),
            )
        ).all()
    )
    for msg in rows:
        db.delete(msg)
    db.commit()
    return {"deleted": len(rows)}


def normalize_escalate_target(target: str | None) -> SalesMailEscalateTarget:
    key = (target or "").strip().lower()
    if key not in ESCALATE_TARGETS:
        raise SalesMailServiceError("escalate_target must be 'support' or 'billing'")
    return key  # type: ignore[return-value]


def escalation_fingerprint(*, target: str, sales_rep_id: str, source_message_id: str) -> str:
    raw = f"salesmail:{target}:{sales_rep_id}:{source_message_id}".strip().lower()
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def escalation_message_id(fingerprint: str) -> str:
    fp = (fingerprint or "").strip().lower()
    return f"<{fp}@{ESCALATE_MESSAGE_ID_DOMAIN}>"


def fingerprint_from_rfc_message_id(message_id: str | None) -> str | None:
    mid = (message_id or "").strip()
    if not mid:
        return None
    if mid.startswith("<") and mid.endswith(">"):
        mid = mid[1:-1]
    mid = mid.strip().lower()
    if mid.endswith(f"@{ESCALATE_MESSAGE_ID_DOMAIN}"):
        return mid[: -len(f"@{ESCALATE_MESSAGE_ID_DOMAIN}")] or None
    return None


def send_email(
    db: Session,
    sales_rep_id: str,
    to: str,
    subject: str,
    body_html: str,
    body_text: str | None = None,
    insert_promo: bool = False,
    *,
    cc: str | None = None,
    attachments: list[dict[str, Any]] | None = None,
    message_id_override: str | None = None,
    extra_headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Send an email via SMTP for a salesman (optional CC + base64 attachments)."""
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

    attachments = attachments or []
    has_att = len(attachments) > 0

    if has_att:
        root = MIMEMultipart("mixed")
        alt = MIMEMultipart("alternative")
        alt.attach(MIMEText(final_body_text, "plain", "utf-8"))
        alt.attach(MIMEText(final_body_html, "html", "utf-8"))
        root.attach(alt)
        for att in attachments:
            name = str(att.get("filename") or att.get("name") or "attachment").strip() or "attachment"
            ctype = str(att.get("content_type") or "application/octet-stream").strip()
            raw_b64 = str(att.get("data_base64") or att.get("dataBase64") or "")
            if "," in raw_b64 and raw_b64.strip().startswith("data:"):
                raw_b64 = raw_b64.split(",", 1)[1]
            try:
                payload = base64.b64decode(raw_b64, validate=False)
            except Exception as e:
                raise SalesMailServiceError(f"Invalid attachment data for {name}") from e
            if len(payload) > 8_000_000:
                raise SalesMailServiceError(f"Attachment {name} exceeds 8 MB")
            maintype, _, subtype = ctype.partition("/")
            part = MIMEBase(maintype or "application", subtype or "octet-stream")
            part.set_payload(payload)
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", "attachment", filename=name)
            root.attach(part)
        msg = root
    else:
        msg = MIMEMultipart("alternative")
        msg.attach(MIMEText(final_body_text, "plain", "utf-8"))
        msg.attach(MIMEText(final_body_html, "html", "utf-8"))

    msg["From"] = rep.smtp_username
    msg["To"] = to
    if cc:
        msg["Cc"] = cc
    msg["Subject"] = subject
    rfc_message_id = (message_id_override or "").strip() or email.utils.make_msgid()
    msg["Message-ID"] = rfc_message_id
    for hk, hv in (extra_headers or {}).items():
        key = str(hk or "").strip()
        val = str(hv or "").strip()
        if key and val:
            msg[key] = val

    recipients = [p.strip() for p in to.split(",") if p.strip()]
    if cc:
        recipients.extend([p.strip() for p in cc.split(",") if p.strip()])

    try:
        if rep.smtp_use_ssl:
            server = smtplib.SMTP_SSL(rep.smtp_host, rep.smtp_port, context=ssl.create_default_context())
        else:
            server = smtplib.SMTP(rep.smtp_host, rep.smtp_port)
            if rep.smtp_use_tls:
                server.starttls(context=ssl.create_default_context())
        server.login(rep.smtp_username, password)
        server.sendmail(rep.smtp_username, recipients, msg.as_string())
        server.quit()

        sent_msg = SalesMailMessage(
            id=str(uuid.uuid4()),
            sales_rep_id=sales_rep_id,
            folder="Sent",
            message_id=rfc_message_id,
            from_email=rep.smtp_username,
            from_name=rep.name,
            to_email=to,
            cc_email=cc or None,
            subject=subject,
            body_text=final_body_text,
            body_html=final_body_html,
            has_attachments=has_att,
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

        return {
            "id": sent_msg.id,
            "message": "Email sent successfully",
            "message_id": rfc_message_id,
        }
    except smtplib.SMTPException as e:
        raise SalesMailServiceError(f"SMTP error: {e}") from e
    except Exception as e:
        raise SalesMailServiceError(f"Failed to send email: {e}") from e


def send_escalation(
    db: Session,
    *,
    sales_rep_id: str,
    org_id: str,
    user_id: str,
    escalate_target: str,
    source_message_id: str,
    subject: str | None = None,
    body_html: str | None = None,
    body_text: str | None = None,
    cc: str | None = None,
    attachments: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Forward a salesman mail message to Support/Billing and create a ticket (idempotent)."""
    target = normalize_escalate_target(escalate_target)
    meta = ESCALATE_TARGETS[target]
    src_id = str(source_message_id or "").strip()
    if not src_id:
        raise SalesMailServiceError("source_message_id is required")

    source = db.scalar(
        select(SalesMailMessage).where(
            SalesMailMessage.id == src_id,
            SalesMailMessage.sales_rep_id == sales_rep_id,
        )
    )
    if source is None:
        raise SalesMailServiceError("Message not found")

    org = str(org_id or "").strip()
    actor = str(user_id or "").strip()
    if not org or not actor:
        raise SalesMailServiceError("Organisation and user are required for escalation")

    fingerprint = escalation_fingerprint(target=target, sales_rep_id=sales_rep_id, source_message_id=src_id)
    rfc_mid = escalation_message_id(fingerprint)

    from app.services.support_ticket_service import SupportTicketService

    existing = SupportTicketService.find_by_email_fingerprint(db, fingerprint)
    if existing is not None:
        return {
            "id": None,
            "message": "Already escalated",
            "message_id": rfc_mid,
            "ticket_id": existing.id,
            "ticket_ref": existing.public_ref or f"TKT-{existing.id:06d}",
            "email_fingerprint": fingerprint,
            "duplicate": True,
            "sent": False,
        }

    intro_text = (body_text or "").strip() or _strip_html(body_html or "")
    intro_html = (body_html or "").strip()
    if not intro_html and intro_text:
        intro_html = f"<p>{intro_text.replace(chr(10), '<br/>')}</p>"

    quote_lines = [
        "",
        "---------- Original message ----------",
        f"From: {source.from_name or source.from_email or ''} <{source.from_email or ''}>",
        f"Subject: {source.subject or ''}",
        f"To: {source.to_email or ''}",
        f"Date: {source.date.isoformat() if source.date else ''}",
        "",
        (source.body_text or _strip_html(source.body_html or "") or "(empty body)"),
    ]
    if source.has_attachments and not (attachments or []):
        quote_lines.append("")
        quote_lines.append(
            "[Note: the original message had attachments. Attachment bytes are not stored in Salesman Mail; "
            "only this quoted body was escalated.]"
        )

    quote_text = "\n".join(quote_lines)
    final_text = f"{intro_text}\n{quote_text}".strip() if intro_text else quote_text.strip()
    quote_html = source.body_html or f"<pre>{_strip_html(source.body_html or source.body_text or '')}</pre>"
    att_note_html = (
        "<p><em>Note: the original message had attachments. Attachment bytes are not stored in Salesman Mail; "
        "only this quoted body was escalated.</em></p>"
        if source.has_attachments and not (attachments or [])
        else ""
    )
    final_html = (
        f"{intro_html}<br/><hr/>"
        f"<p style='color:#666;font-size:12px'>---------- Original message ----------<br/>"
        f"From: {source.from_name or source.from_email or ''} &lt;{source.from_email or ''}&gt;<br/>"
        f"Subject: {source.subject or ''}<br/>"
        f"To: {source.to_email or ''}</p>"
        f"{quote_html}{att_note_html}"
    )
    if ESCALATE_HEADER.lower() not in final_text.lower():
        final_text = f"{final_text}\n\n{ESCALATE_HEADER}: {fingerprint}"
        final_html = f"{final_html}<p style='display:none'>{ESCALATE_HEADER}: {fingerprint}</p>"

    fwd_subject = (subject or "").strip()
    if not fwd_subject:
        subj = source.subject or "(no subject)"
        if subj.lower().startswith("fw:") or subj.lower().startswith("fwd:"):
            fwd_subject = subj
        else:
            fwd_subject = f"Fwd: {subj}"

    send_result = send_email(
        db,
        sales_rep_id,
        meta["to"],
        fwd_subject,
        final_html,
        final_text,
        False,
        cc=cc,
        attachments=attachments,
        message_id_override=rfc_mid,
        extra_headers={ESCALATE_HEADER: fingerprint},
    )

    ticket_body = (
        f"Escalated from Salesman Mail → {meta['label']}\n"
        f"Original From: {source.from_name or ''} <{source.from_email or ''}>\n"
        f"Original Subject: {source.subject or ''}\n"
        f"Original To: {source.to_email or ''}\n"
        f"Sales message id: {source.id}\n"
        f"{ESCALATE_HEADER}: {fingerprint}\n\n"
        f"{final_text}"
    )[:8000]
    staff_note = (
        f"Salesman Mail escalation to {meta['to']} "
        f"(target={target}, fingerprint={fingerprint}, message-id={rfc_mid})"
    )
    ticket_atts: list[dict[str, Any]] = []
    for att in attachments or []:
        name = str(att.get("filename") or att.get("name") or "attachment").strip() or "attachment"
        ctype = str(att.get("content_type") or "application/octet-stream").strip()
        raw_b64 = str(att.get("data_base64") or att.get("dataBase64") or "")
        if "," in raw_b64 and raw_b64.strip().startswith("data:"):
            raw_b64 = raw_b64.split(",", 1)[1]
        try:
            payload = base64.b64decode(raw_b64, validate=False)
        except Exception:
            continue
        if not payload or len(payload) > 8_000_000:
            continue
        ticket_atts.append(
            {
                "filename": name,
                "content_type": ctype,
                "size_bytes": len(payload),
                "data": payload,
            }
        )

    ticket = SupportTicketService.create_ticket(
        db,
        org_id=org,
        user_id=actor,
        category=meta["category"],
        subject=fwd_subject[:240],
        message=ticket_body,
        priority="normal",
        channel="email",
        attachments=ticket_atts or None,
        staff_note=staff_note,
        requester_email=source.from_email or None,
        requester_name=source.from_name or None,
        email_fingerprint=fingerprint,
    )

    return {
        **send_result,
        "ticket_id": ticket.id,
        "ticket_ref": ticket.public_ref or f"TKT-{ticket.id:06d}",
        "email_fingerprint": fingerprint,
        "duplicate": False,
        "sent": True,
        "category": meta["category"],
        "escalate_target": target,
    }


def polish_body_with_ai(
    db: Session,
    *,
    body: str,
    mode: str = "fix",
    subject: str = "",
    from_line: str = "",
    context_body: str = "",
    sales_rep_id: str | None = None,
) -> str:
    """AI write or polish an email draft using platform OpenAI/DeepSeek when configured."""
    mode_key = (mode or "fix").strip().lower()
    draft = (body or "").strip()
    incoming = _plain_email_text(context_body)
    if mode_key == "write" and not draft and not incoming:
        raise SalesMailServiceError(
            "Nothing to reply to — open the email first so AI can read it, or paste the incoming message."
        )
    if mode_key != "write" and not draft:
        return draft

    promo_bits = ""
    package_bits = ""
    rep_name = ""
    if sales_rep_id:
        try:
            rep = db.scalar(select(SalesRep).where(SalesRep.id == str(sales_rep_id)))
            if rep:
                from app.services.sales_hub_benefits import (
                    benefit_summaries,
                    currency_of_rep,
                    packages_for_currency,
                    parse_promo_benefits,
                )

                rep_name = str(rep.name or "").strip()
                currency = currency_of_rep(rep)
                benefits = parse_promo_benefits(rep)
                summaries = benefit_summaries(benefits, currency=currency)
                if rep.promo_code:
                    promo_bits = f"Promo code: {rep.promo_code}\n"
                if summaries:
                    promo_bits += "Customer promo benefits:\n- " + "\n- ".join(summaries[:8])
                pkgs = packages_for_currency(db, currency)[:8]
                if pkgs:
                    package_bits = "\n".join(
                        f"- {p.get('name')}: {p.get('list_price_display') or p.get('monthly_display') or 'price on request'}"
                        for p in pkgs
                    )
        except Exception as e:  # noqa: BLE001
            logger.debug("sales mail AI context load skipped: %s", e)

    try:
        from app.services.agents.base import AgentMessage
        from app.services.providers.openai_service import OpenAIProviderService

        product_brief = (
            "VoxBulk is a B2B SaaS platform. Core products:\n"
            "- AI Interview Screening — automated voice/video candidate interviews\n"
            "- WA Survey / AI Call Survey — WhatsApp and voice surveys at scale\n"
            "- Customer Feedback — QR / Smart Card feedback collection\n"
            "- Voxbulk Expo — event / expo engagement packages\n"
            "- Smart Card QR — physical NFC/QR cards linked to feedback\n"
            "Be accurate, helpful, and sales-aware. Do not invent pricing not listed below. "
            "Invite a short call or demo when appropriate. Use UK professional tone."
        )

        if mode_key == "write":
            system = (
                "You are a VoxBulk salesman writing a reply email. "
                "Read the incoming message carefully and answer their points. "
                f"{product_brief} "
                "Return only the email body in plain text — no subject line, no markdown fences, no preamble like 'Here is a draft'."
            )
            user = (
                f"Salesman name: {rep_name or '(sales team)'}\n"
                f"Incoming subject: {subject or '(none)'}\n"
                f"From: {from_line or '(unknown)'}\n\n"
                f"Incoming message:\n{incoming[:5000] or '(empty — write a short proactive follow-up)'}\n\n"
                f"{promo_bits}\n"
                f"Price sheet to quote if relevant:\n{package_bits or '(use general product names only)'}\n\n"
                "Write a complete reply that:\n"
                "1) Acknowledges what they asked\n"
                "2) Explains how VoxBulk helps for their case\n"
                "3) Mentions relevant product(s) and promo code when useful\n"
                "4) Ends with a clear next step (reply, book a demo, or try the promo)\n"
            )
            if draft:
                user += f"\nSalesman notes / partial draft to incorporate:\n{draft[:2000]}\n"
        else:
            system = (
                "You are an expert editor for professional VoxBulk sales email. "
                "Improve clarity, grammar, and tone while keeping the salesman's intent and facts. "
                f"{product_brief} "
                "Return only the rewritten email body plain text — no commentary."
            )
            user = (
                f"Subject context: {subject or '(none)'}\n"
                f"Original thread from: {from_line or '(n/a)'}\n\n"
                f"Incoming message (for context):\n{incoming[:3000] or '(none)'}\n\n"
                f"{promo_bits}\n"
                f"Draft to improve:\n{draft[:4000]}"
            )

        result = OpenAIProviderService.complete(
            db,
            system_prompt=system,
            messages=[AgentMessage(role="user", content=user)],
            max_tokens=1200,
            temperature=0.45,
        )
        text = str(getattr(result, "assistant_text", None) or getattr(result, "text", None) or "").strip()
        # Some providers wrap content; strip common wrappers
        if text.startswith("```"):
            text = re.sub(r"^```(?:\w+)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text).strip()
        if text:
            return text
        raise SalesMailServiceError(
            "AI returned an empty reply. Check Admin → Integrations → OpenAI/DeepSeek is configured, then try again."
        )
    except SalesMailServiceError:
        raise
    except Exception as e:
        logger.warning("sales mail AI polish failed: %s", e)
        raise SalesMailServiceError(
            f"AI reply failed: {e}. Check OpenAI/DeepSeek is configured in Admin integrations."
        ) from e


def _plain_email_text(value: str | None) -> str:
    """Prefer plain text; strip HTML tags when only HTML is available."""
    raw = (value or "").strip()
    if not raw:
        return ""
    if "<" in raw and ">" in raw:
        text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", raw)
        text = re.sub(r"(?i)<br\s*/?>", "\n", text)
        text = re.sub(r"(?i)</p>", "\n", text)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"[ \t]+\n", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"[ \t]{2,}", " ", text)
        return text.strip()
    return raw
