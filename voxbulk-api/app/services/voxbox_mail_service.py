"""Voxbox multi-account IMAP sync + SMTP send + DeepSeek drafts."""

from __future__ import annotations

import base64
import email.utils
import imaplib
import logging
import re
import smtplib
import ssl
import uuid
from datetime import datetime, timedelta
from email import message_from_bytes
from email.header import decode_header
from email.message import EmailMessage, Message
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.encryption import get_encryptor
from app.models.voxbox_mail_account import VoxboxMailAccount
from app.models.voxbox_message import VoxboxMessage
from app.schemas.voxbox import VoxboxAccountIn, VoxboxAccountUpdate, VoxboxAiReplyIn, VoxboxComposeIn, VoxboxMessagePatch, VoxboxSendIn

logger = logging.getLogger(__name__)


class VoxboxServiceError(RuntimeError):
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


def _parse_from(header: str | None) -> tuple[str, str]:
    name, addr = email.utils.parseaddr(_decode_mime(header))
    return (name or "").strip()[:255], (addr or "").strip().lower()[:320]


def _parse_date(header: str | None) -> datetime:
    try:
        dt = email.utils.parsedate_to_datetime(header or "")
        if dt is None:
            return datetime.utcnow()
        if dt.tzinfo is not None:
            return dt.astimezone(tz=None).replace(tzinfo=None)
        return dt
    except Exception:
        return datetime.utcnow()


class VoxboxMailService:
    @staticmethod
    def _now() -> datetime:
        return datetime.utcnow()

    @staticmethod
    def _decrypt_password(account: VoxboxMailAccount) -> str:
        if not account.password_enc:
            return ""
        return get_encryptor().decrypt_str(account.password_enc)

    @staticmethod
    def _encrypt_password(password: str) -> str:
        return get_encryptor().encrypt_str(password)

    @staticmethod
    def account_to_dict(account: VoxboxMailAccount) -> dict[str, Any]:
        return {
            "id": account.id,
            "name": account.name,
            "email": account.email,
            "color": account.color,
            "imap_host": account.imap_host,
            "imap_port": account.imap_port,
            "smtp_host": account.smtp_host,
            "smtp_port": account.smtp_port,
            "username": account.username,
            "ssl": bool(account.imap_use_ssl),
            "imap_use_ssl": bool(account.imap_use_ssl),
            "smtp_use_ssl": bool(account.smtp_use_ssl),
            "smtp_use_tls": bool(account.smtp_use_tls),
            "status": account.status,
            "signature": account.signature or "",
            "frozen": bool(account.frozen),
            "sort_order": int(account.sort_order or 0),
            "password_configured": bool(account.password_enc),
            "last_sync_at": account.last_sync_at.isoformat() if account.last_sync_at else None,
            "last_sync_message": account.last_sync_message or "",
        }

    @staticmethod
    def message_to_dict(msg: VoxboxMessage, *, full: bool = False) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": msg.id,
            "account_id": msg.account_id,
            "from": msg.from_name or msg.from_email,
            "from_email": msg.from_email,
            "to": msg.to_addrs,
            "subject": msg.subject,
            "preview": msg.preview,
            "date": msg.date.isoformat() if msg.date else None,
            "unread": bool(msg.unread),
            "important": bool(msg.important),
            "starred": bool(msg.starred),
            "has_attachment": bool(msg.has_attachment),
            "folder": msg.folder,
            "html": "",
            "text": "",
        }
        if full:
            data["html"] = msg.body_html or ""
            data["text"] = msg.body_text or ""
        else:
            data["text"] = (msg.body_text or "")[:2000]
            data["html"] = ""
        return data

    @staticmethod
    def list_accounts(db: Session) -> list[dict[str, Any]]:
        rows = list(
            db.scalars(select(VoxboxMailAccount).order_by(VoxboxMailAccount.sort_order.asc(), VoxboxMailAccount.created_at.asc()))
        )
        return [VoxboxMailService.account_to_dict(r) for r in rows]

    @staticmethod
    def create_account(db: Session, payload: VoxboxAccountIn) -> dict[str, Any]:
        max_order = db.scalar(select(func.max(VoxboxMailAccount.sort_order))) or 0
        smtp_ssl = payload.smtp_use_ssl if payload.smtp_use_ssl is not None else bool(payload.ssl)
        smtp_tls = payload.smtp_use_tls if payload.smtp_use_tls is not None else (not smtp_ssl and int(payload.smtp_port) == 587)
        row = VoxboxMailAccount(
            id=str(uuid.uuid4()),
            name=(payload.name or payload.email).strip()[:120],
            email=payload.email.strip().lower()[:320],
            color=(payload.color or "var(--accent-1)")[:64],
            sort_order=int(max_order) + 1,
            imap_host=(payload.imap_host or "").strip()[:255],
            imap_port=int(payload.imap_port or 993),
            imap_use_ssl=bool(payload.ssl),
            smtp_host=(payload.smtp_host or "").strip()[:255],
            smtp_port=int(payload.smtp_port or 465),
            smtp_use_ssl=bool(smtp_ssl),
            smtp_use_tls=bool(smtp_tls),
            username=(payload.username or payload.email).strip()[:320],
            signature=(payload.signature or "")[:4000],
            frozen=bool(payload.frozen),
            status="untested",
            created_at=VoxboxMailService._now(),
            updated_at=VoxboxMailService._now(),
        )
        if payload.password and str(payload.password).strip():
            row.password_enc = VoxboxMailService._encrypt_password(str(payload.password).strip())
        db.add(row)
        db.commit()
        db.refresh(row)
        return VoxboxMailService.account_to_dict(row)

    @staticmethod
    def update_account(db: Session, account_id: str, payload: VoxboxAccountUpdate) -> dict[str, Any]:
        row = db.get(VoxboxMailAccount, account_id)
        if row is None:
            raise VoxboxServiceError("Account not found")
        data = payload.model_dump(exclude_unset=True)
        mapping = {
            "name": "name",
            "email": "email",
            "color": "color",
            "imap_host": "imap_host",
            "imap_port": "imap_port",
            "smtp_host": "smtp_host",
            "smtp_port": "smtp_port",
            "username": "username",
            "signature": "signature",
            "frozen": "frozen",
            "smtp_use_ssl": "smtp_use_ssl",
            "smtp_use_tls": "smtp_use_tls",
        }
        for src, dest in mapping.items():
            if src in data and data[src] is not None:
                val = data[src]
                if src == "email" and isinstance(val, str):
                    val = val.strip().lower()
                setattr(row, dest, val)
        if "ssl" in data and data["ssl"] is not None:
            row.imap_use_ssl = bool(data["ssl"])
        if "password" in data and data["password"] is not None and str(data["password"]).strip():
            row.password_enc = VoxboxMailService._encrypt_password(str(data["password"]).strip())
        row.updated_at = VoxboxMailService._now()
        db.add(row)
        db.commit()
        db.refresh(row)
        return VoxboxMailService.account_to_dict(row)

    @staticmethod
    def delete_account(db: Session, account_id: str) -> dict[str, Any]:
        row = db.get(VoxboxMailAccount, account_id)
        if row is None:
            raise VoxboxServiceError("Account not found")
        db.delete(row)
        db.commit()
        return {"ok": True, "deleted": account_id}

    @staticmethod
    def reorder_accounts(db: Session, ordered_ids: list[str]) -> list[dict[str, Any]]:
        rows = {r.id: r for r in db.scalars(select(VoxboxMailAccount)).all()}
        for idx, aid in enumerate(ordered_ids):
            row = rows.get(aid)
            if row is None:
                continue
            row.sort_order = idx
            row.updated_at = VoxboxMailService._now()
            db.add(row)
        db.commit()
        return VoxboxMailService.list_accounts(db)

    @staticmethod
    def _imap_connect(account: VoxboxMailAccount) -> imaplib.IMAP4:
        host = (account.imap_host or "").strip()
        if not host:
            raise VoxboxServiceError("IMAP host is required")
        port = int(account.imap_port or 993)
        if account.imap_use_ssl:
            return imaplib.IMAP4_SSL(host, port)
        return imaplib.IMAP4(host, port)

    @staticmethod
    def test_account(db: Session, account_id: str) -> dict[str, Any]:
        row = db.get(VoxboxMailAccount, account_id)
        if row is None:
            raise VoxboxServiceError("Account not found")
        user = (row.username or row.email or "").strip()
        pwd = VoxboxMailService._decrypt_password(row)
        if not user or not pwd:
            raise VoxboxServiceError("Username and password are required")
        if not (row.imap_host or "").strip() or not (row.smtp_host or "").strip():
            raise VoxboxServiceError("IMAP and SMTP hosts are required")
        try:
            conn = VoxboxMailService._imap_connect(row)
            try:
                conn.login(user, pwd)
                typ, _ = conn.select("INBOX", readonly=True)
                if typ != "OK":
                    raise VoxboxServiceError("Could not open INBOX")
            finally:
                try:
                    conn.logout()
                except Exception:
                    pass
            # SMTP probe
            VoxboxMailService._smtp_probe(row, user=user, password=pwd)
        except VoxboxServiceError:
            row.status = "failed"
            row.updated_at = VoxboxMailService._now()
            db.add(row)
            db.commit()
            raise
        except Exception as exc:
            row.status = "failed"
            row.last_sync_message = str(exc)[:500]
            row.updated_at = VoxboxMailService._now()
            db.add(row)
            db.commit()
            raise VoxboxServiceError(f"Connection failed: {exc}") from exc

        row.status = "ok"
        row.last_sync_message = "IMAP and SMTP OK"
        row.updated_at = VoxboxMailService._now()
        db.add(row)
        db.commit()
        return {"ok": True, "message": "IMAP and SMTP connection OK", "status": "ok"}

    @staticmethod
    def _smtp_probe(account: VoxboxMailAccount, *, user: str, password: str) -> None:
        host = (account.smtp_host or "").strip()
        port = int(account.smtp_port or 465)
        ctx = ssl.create_default_context()
        if account.smtp_use_ssl or port == 465:
            with smtplib.SMTP_SSL(host, port, context=ctx, timeout=30) as smtp:
                smtp.login(user, password)
        else:
            with smtplib.SMTP(host, port, timeout=30) as smtp:
                smtp.ehlo()
                if account.smtp_use_tls or port == 587:
                    smtp.starttls(context=ctx)
                    smtp.ehlo()
                smtp.login(user, password)

    @staticmethod
    def sync_all(db: Session, *, limit_per_account: int = 80, since_days: int = 14) -> dict[str, Any]:
        accounts = list(
            db.scalars(
                select(VoxboxMailAccount)
                .where(VoxboxMailAccount.frozen.is_(False))
                .order_by(VoxboxMailAccount.sort_order.asc())
            )
        )
        synced = 0
        fetched = 0
        errors: list[str] = []
        for account in accounts:
            try:
                n = VoxboxMailService.sync_account(db, account, limit=limit_per_account, since_days=since_days)
                synced += 1
                fetched += n
            except Exception as exc:
                logger.exception("voxbox_sync_failed account=%s", account.id)
                errors.append(f"{account.email or account.name}: {exc}")
                account.status = "failed"
                account.last_sync_message = str(exc)[:500]
                account.updated_at = VoxboxMailService._now()
                db.add(account)
                db.commit()
        msg = f"Synced {synced}/{len(accounts)} accounts, fetched {fetched} messages"
        if errors:
            msg += f". Errors: {'; '.join(errors[:3])}"
        return {"ok": len(errors) == 0, "synced_accounts": synced, "fetched": fetched, "message": msg, "errors": errors}

    @staticmethod
    def sync_account(db: Session, account: VoxboxMailAccount, *, limit: int = 80, since_days: int = 14) -> int:
        user = (account.username or account.email or "").strip()
        pwd = VoxboxMailService._decrypt_password(account)
        if not user or not pwd:
            raise VoxboxServiceError("Username/password missing")
        if not (account.imap_host or "").strip():
            raise VoxboxServiceError("IMAP host missing")

        stored = 0
        conn = VoxboxMailService._imap_connect(account)
        try:
            conn.login(user, pwd)
            folder_plan: list[tuple[str, str]] = [("INBOX", "inbox")]
            sent_aliases = ("Sent", "INBOX.Sent", "[Gmail]/Sent Mail", "Sent Items", "INBOX.Sent Items")
            sent_done = False
            for folder_name, folder_label in folder_plan + [(a, "sent") for a in sent_aliases]:
                if folder_label == "sent" and sent_done:
                    continue
                try:
                    typ, _ = conn.select(folder_name, readonly=True)
                except Exception:
                    continue
                if typ != "OK":
                    continue
                if folder_label == "sent":
                    sent_done = True
                ids: list[bytes] = []
                seen: set[bytes] = set()
                days = max(1, min(int(since_days or 14), 60))
                since = (datetime.utcnow() - timedelta(days=days)).strftime("%d-%b-%Y")
                typ, data = conn.search(None, "SINCE", since)
                if typ == "OK" and data and data[0]:
                    for num in data[0].split():
                        if num not in seen:
                            ids.append(num)
                            seen.add(num)
                ids = list(reversed(ids))[: max(1, min(int(limit or 80), 200))]
                for num in ids:
                    typ, msg_data = conn.fetch(num, "(RFC822 FLAGS)")
                    if typ != "OK" or not msg_data:
                        continue
                    raw = None
                    flags = ""
                    for item in msg_data:
                        if isinstance(item, tuple) and len(item) >= 2 and isinstance(item[1], (bytes, bytearray)):
                            raw = bytes(item[1])
                            meta = (
                                item[0].decode("utf-8", errors="replace")
                                if isinstance(item[0], (bytes, bytearray))
                                else str(item[0])
                            )
                            flags = meta
                    if not raw:
                        continue
                    msg = message_from_bytes(raw)
                    internet_id = (_decode_mime(msg.get("Message-ID")) or "").strip()[:500]
                    if not internet_id:
                        uid = num.decode() if isinstance(num, bytes) else str(num)
                        internet_id = f"voxbox-{account.id}-{folder_label}-{uid}"[:500]
                    existing = db.execute(
                        select(VoxboxMessage)
                        .where(
                            VoxboxMessage.account_id == account.id,
                            VoxboxMessage.internet_message_id == internet_id,
                        )
                        .limit(1)
                    ).scalar_one_or_none()
                    from_name, from_email = _parse_from(msg.get("From"))
                    to_addrs = _decode_mime(msg.get("To"))[:1000]
                    subject = _decode_mime(msg.get("Subject"))[:500]
                    text, html = _collect_bodies(msg)
                    preview = (text or _strip_html(html) or "")[:500]
                    date = _parse_date(msg.get("Date"))
                    unread = "\\Seen" not in flags
                    important = "\\Flagged" in flags or msg.get("X-Priority") == "1"
                    if existing is None:
                        db.add(
                            VoxboxMessage(
                                id=str(uuid.uuid4()),
                                account_id=account.id,
                                internet_message_id=internet_id,
                                imap_uid=(num.decode() if isinstance(num, bytes) else str(num))[:64],
                                folder=folder_label,
                                from_name=from_name,
                                from_email=from_email,
                                to_addrs=to_addrs,
                                subject=subject,
                                preview=preview,
                                body_text=text or None,
                                body_html=html or None,
                                date=date,
                                unread=unread if folder_label == "inbox" else False,
                                important=important,
                                starred="\\Flagged" in flags,
                                has_attachment=_has_attachment(msg),
                                created_at=VoxboxMailService._now(),
                                updated_at=VoxboxMailService._now(),
                            )
                        )
                        stored += 1
                    else:
                        existing.subject = subject or existing.subject
                        existing.preview = preview or existing.preview
                        if text:
                            existing.body_text = text
                        if html:
                            existing.body_html = html
                        existing.from_name = from_name or existing.from_name
                        existing.from_email = from_email or existing.from_email
                        existing.to_addrs = to_addrs or existing.to_addrs
                        # Keep local trash/archive — do not resurrect from INBOX sync
                        local_folder = (existing.folder or "").strip().lower()
                        if local_folder not in {"trash", "archive"}:
                            existing.folder = folder_label
                        existing.has_attachment = _has_attachment(msg) or bool(existing.has_attachment)
                        existing.updated_at = VoxboxMailService._now()
                        db.add(existing)
                    db.commit()
        finally:
            try:
                conn.logout()
            except Exception:
                pass

        account.status = "ok"
        account.last_sync_at = VoxboxMailService._now()
        account.last_sync_message = f"Fetched/updated {stored} new messages"
        account.updated_at = VoxboxMailService._now()
        db.add(account)
        db.commit()
        return stored

    @staticmethod
    def list_messages(
        db: Session,
        *,
        account_id: str | None = None,
        folder: str | None = None,
        tab: str | None = None,
        q: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        stmt = select(VoxboxMessage)
        if account_id and account_id != "all":
            stmt = stmt.where(VoxboxMessage.account_id == account_id)
        else:
            active = list(
                db.scalars(select(VoxboxMailAccount.id).where(VoxboxMailAccount.frozen.is_(False)))
            )
            if active:
                stmt = stmt.where(VoxboxMessage.account_id.in_(active))
            else:
                return []

        tab_l = (tab or folder or "inbox").strip().lower()
        if tab_l in {"sent", "archive", "trash"}:
            stmt = stmt.where(VoxboxMessage.folder == tab_l)
        elif tab_l == "unread":
            stmt = stmt.where(VoxboxMessage.folder == "inbox", VoxboxMessage.unread.is_(True))
        elif tab_l == "important":
            stmt = stmt.where(VoxboxMessage.folder == "inbox", VoxboxMessage.important.is_(True))
        elif tab_l == "starred":
            stmt = stmt.where(VoxboxMessage.starred.is_(True))
        else:
            stmt = stmt.where(VoxboxMessage.folder == "inbox")

        rows = list(db.scalars(stmt.order_by(VoxboxMessage.date.desc()).limit(max(1, min(limit, 500)))))
        qn = (q or "").strip().lower()
        out = [VoxboxMailService.message_to_dict(r, full=False) for r in rows]
        if qn:
            out = [
                m
                for m in out
                if qn in " ".join([m.get("subject") or "", m.get("from") or "", m.get("from_email") or "", m.get("text") or ""]).lower()
            ]
        return out

    @staticmethod
    def get_message(db: Session, message_id: str) -> dict[str, Any]:
        row = db.get(VoxboxMessage, message_id)
        if row is None:
            raise VoxboxServiceError("Message not found")
        return VoxboxMailService.message_to_dict(row, full=True)

    @staticmethod
    def _imap_delete_server_message(account: VoxboxMailAccount, row: VoxboxMessage) -> None:
        """Mark the message deleted on IMAP (INBOX/Sent) and expunge."""
        user = (account.username or account.email or "").strip()
        pwd = VoxboxMailService._decrypt_password(account)
        if not user or not pwd or not (account.imap_host or "").strip():
            raise VoxboxServiceError("IMAP credentials missing — cannot delete on server")

        mid = (row.internet_message_id or "").strip()
        folders = ["INBOX", "Sent", "INBOX.Sent", "[Gmail]/Sent Mail", "Sent Items", "INBOX.Sent Items"]
        source_folder = (row.folder or "").strip().lower()
        if source_folder == "sent":
            folders = ["Sent", "INBOX.Sent", "[Gmail]/Sent Mail", "Sent Items", "INBOX.Sent Items", "INBOX"]

        conn = VoxboxMailService._imap_connect(account)
        deleted = False
        try:
            conn.login(user, pwd)
            for folder_name in folders:
                try:
                    typ, _ = conn.select(folder_name)
                except Exception:
                    continue
                if typ != "OK":
                    continue
                ids: list[bytes] = []
                if mid and not mid.startswith("voxbox-"):
                    # HEADER Message-ID search (with and without angle brackets)
                    candidates = [mid]
                    if mid.startswith("<") and mid.endswith(">"):
                        candidates.append(mid[1:-1])
                    else:
                        candidates.append(f"<{mid}>")
                    for cand in candidates:
                        try:
                            typ, data = conn.search(None, "HEADER", "Message-ID", cand)
                        except Exception:
                            continue
                        if typ == "OK" and data and data[0]:
                            ids = data[0].split()
                            if ids:
                                break
                    if not ids:
                        continue
                elif (row.imap_uid or "").strip():
                    uid = (row.imap_uid or "").strip().encode()
                    ids = [uid]
                else:
                    continue
                for num in ids:
                    conn.store(num, "+FLAGS", "\\Deleted")
                    deleted = True
                if deleted:
                    conn.expunge()
                    break
            if not deleted:
                logger.warning(
                    "voxbox_imap_delete_not_found account=%s message_id=%s internet_id=%s",
                    account.id,
                    row.id,
                    mid[:80],
                )
        finally:
            try:
                conn.logout()
            except Exception:
                pass

    @staticmethod
    def patch_message(db: Session, message_id: str, payload: VoxboxMessagePatch) -> dict[str, Any]:
        row = db.get(VoxboxMessage, message_id)
        if row is None:
            raise VoxboxServiceError("Message not found")
        data = payload.model_dump(exclude_unset=True)
        prev_folder = (row.folder or "").strip().lower()
        new_folder = data.get("folder")
        moving_to_trash = (
            new_folder is not None
            and str(new_folder).strip().lower() == "trash"
            and prev_folder != "trash"
        )

        if moving_to_trash:
            account = db.get(VoxboxMailAccount, row.account_id)
            if account is None:
                raise VoxboxServiceError("Account not found")
            try:
                VoxboxMailService._imap_delete_server_message(account, row)
            except VoxboxServiceError:
                raise
            except Exception as exc:
                logger.exception("voxbox_imap_delete_failed message_id=%s", message_id)
                raise VoxboxServiceError(f"Could not delete on mail server: {exc}") from exc

        for key in ("unread", "starred", "important", "folder"):
            if key in data and data[key] is not None:
                setattr(row, key, data[key])
        row.updated_at = VoxboxMailService._now()
        db.add(row)
        db.commit()
        db.refresh(row)
        return VoxboxMailService.message_to_dict(row, full=True)

    @staticmethod
    def kpi(db: Session, *, account_id: str | None = None) -> dict[str, int]:
        stmt = select(VoxboxMessage).where(VoxboxMessage.folder == "inbox")
        if account_id and account_id != "all":
            stmt = stmt.where(VoxboxMessage.account_id == account_id)
        else:
            active = list(db.scalars(select(VoxboxMailAccount.id).where(VoxboxMailAccount.frozen.is_(False))))
            if not active:
                return {"total": 0, "unread": 0, "important": 0, "starred": 0}
            stmt = stmt.where(VoxboxMessage.account_id.in_(active))
        rows = list(db.scalars(stmt))
        return {
            "total": len(rows),
            "unread": sum(1 for r in rows if r.unread),
            "important": sum(1 for r in rows if r.important),
            "starred": sum(1 for r in rows if r.starred),
        }

    @staticmethod
    def _smtp_send(
        account: VoxboxMailAccount,
        *,
        to_addr: str,
        subject: str,
        body: str,
        body_html: str | None = None,
        in_reply_to: str | None = None,
        attachments: list[dict[str, str]] | None = None,
    ) -> EmailMessage:
        user = (account.username or account.email or "").strip()
        pwd = VoxboxMailService._decrypt_password(account)
        if not user or not pwd:
            raise VoxboxServiceError("SMTP credentials missing")
        if not to_addr or "@" not in to_addr:
            raise VoxboxServiceError("Recipient address required")

        text = body.strip()
        sig = (account.signature or "").strip()
        if sig and sig not in text:
            text = f"{text}\n\n{sig}"

        html = (body_html or "").strip() or None
        if html and sig and sig not in html:
            html = f"{html}<br/><br/><pre style=\"font-family:inherit;white-space:pre-wrap\">{sig}</pre>"

        msg = EmailMessage()
        msg["Subject"] = (subject or "(no subject)")[:500]
        msg["From"] = email.utils.formataddr((account.name or "", account.email))
        msg["To"] = to_addr
        if in_reply_to:
            msg["In-Reply-To"] = in_reply_to
            msg["References"] = in_reply_to
        msg.set_content(text)
        if html:
            msg.add_alternative(html, subtype="html")

        for att in attachments or []:
            name = (att.get("name") or "attachment").strip()[:255] or "attachment"
            ctype = (att.get("content_type") or "application/octet-stream").strip()[:120]
            raw_b64 = (att.get("data_base64") or "").strip()
            if "," in raw_b64 and raw_b64.lower().startswith("data:"):
                raw_b64 = raw_b64.split(",", 1)[1]
            try:
                data = base64.b64decode(raw_b64, validate=False)
            except Exception as exc:
                raise VoxboxServiceError(f"Invalid attachment data for {name}") from exc
            if len(data) > 5_000_000:
                raise VoxboxServiceError(f"Attachment {name} exceeds 5 MB")
            maintype, _, subtype = ctype.partition("/")
            if not subtype:
                maintype, subtype = "application", "octet-stream"
            msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=name)

        host = (account.smtp_host or "").strip()
        port = int(account.smtp_port or 465)
        ctx = ssl.create_default_context()
        try:
            if account.smtp_use_ssl or port == 465:
                with smtplib.SMTP_SSL(host, port, context=ctx, timeout=60) as smtp:
                    smtp.login(user, pwd)
                    smtp.send_message(msg, from_addr=account.email or user, to_addrs=[to_addr])
            else:
                with smtplib.SMTP(host, port, timeout=60) as smtp:
                    smtp.ehlo()
                    if account.smtp_use_tls or port == 587:
                        smtp.starttls(context=ctx)
                        smtp.ehlo()
                    smtp.login(user, pwd)
                    smtp.send_message(msg, from_addr=account.email or user, to_addrs=[to_addr])
        except Exception as exc:
            raise VoxboxServiceError(f"Send failed: {exc}") from exc
        return msg

    @staticmethod
    def _store_sent(
        db: Session,
        account: VoxboxMailAccount,
        *,
        to_addr: str,
        subject: str,
        body: str,
        msg: EmailMessage,
        body_html: str | None = None,
        has_attachment: bool = False,
    ) -> dict[str, Any]:
        text = body.strip()
        html = (body_html or "").strip() or f"<p>{text.replace(chr(10), '<br/>')}</p>"
        sent = VoxboxMessage(
            id=str(uuid.uuid4()),
            account_id=account.id,
            internet_message_id=str(msg.get("Message-ID") or f"sent-{uuid.uuid4()}")[:500],
            imap_uid="",
            folder="sent",
            from_name=account.name or "",
            from_email=account.email,
            to_addrs=to_addr,
            subject=subject[:500],
            preview=text[:500],
            body_text=text,
            body_html=html,
            date=VoxboxMailService._now(),
            unread=False,
            important=False,
            starred=False,
            has_attachment=bool(has_attachment),
            created_at=VoxboxMailService._now(),
            updated_at=VoxboxMailService._now(),
        )
        db.add(sent)
        db.commit()
        db.refresh(sent)
        return VoxboxMailService.message_to_dict(sent, full=True)

    @staticmethod
    def delete_message(db: Session, message_id: str) -> dict[str, str]:
        """Permanently remove a message from Voxbox (used for Trash / Empty trash)."""
        row = db.get(VoxboxMessage, message_id)
        if row is None:
            raise VoxboxServiceError("Message not found")
        # Already removed from IMAP when moved to trash; purge local row.
        db.delete(row)
        db.commit()
        return {"ok": "true", "id": message_id}

    @staticmethod
    def empty_trash(db: Session, *, account_id: str | None = None) -> dict[str, Any]:
        stmt = select(VoxboxMessage).where(VoxboxMessage.folder == "trash")
        if account_id and account_id != "all":
            stmt = stmt.where(VoxboxMessage.account_id == account_id)
        rows = list(db.scalars(stmt))
        for row in rows:
            db.delete(row)
        db.commit()
        return {"ok": True, "deleted": len(rows)}

    @staticmethod
    def send_message(db: Session, message_id: str, payload: VoxboxSendIn) -> dict[str, Any]:
        src = db.get(VoxboxMessage, message_id)
        if src is None:
            raise VoxboxServiceError("Message not found")
        account = db.get(VoxboxMailAccount, src.account_id)
        if account is None:
            raise VoxboxServiceError("Account not found")

        to_addr = (payload.to or src.from_email or "").strip()
        base_subj = (src.subject or "").strip()
        base_subj = re.sub(r"^(Re|Fwd):\s*", "", base_subj, flags=re.I)
        subject = f"{'Re' if payload.kind == 'reply' else 'Fwd'}: {base_subj}"[:500]
        body = payload.body.strip()
        in_reply = src.internet_message_id if payload.kind == "reply" else None
        msg = VoxboxMailService._smtp_send(
            account,
            to_addr=to_addr,
            subject=subject,
            body=body,
            in_reply_to=in_reply,
        )
        return VoxboxMailService._store_sent(
            db, account, to_addr=to_addr, subject=subject, body=body, msg=msg
        )

    @staticmethod
    def compose_message(db: Session, payload: VoxboxComposeIn) -> dict[str, Any]:
        account = db.get(VoxboxMailAccount, payload.account_id)
        if account is None:
            raise VoxboxServiceError("Account not found")
        if account.frozen:
            raise VoxboxServiceError("Account is frozen")
        to_addr = (payload.to or "").strip()
        subject = (payload.subject or "").strip() or "(no subject)"
        body = payload.body.strip()
        fmt = (payload.format or "text").strip().lower()
        html = (payload.body_html or "").strip() or None
        if fmt == "html" and not html:
            html = body
            plain = re.sub(r"<br\s*/?>", "\n", html, flags=re.I)
            plain = re.sub(r"<[^>]+>", "", plain)
            body = plain.strip() or body
        attachments = [
            {
                "name": a.name,
                "content_type": a.content_type,
                "data_base64": a.data_base64,
            }
            for a in (payload.attachments or [])
        ]
        msg = VoxboxMailService._smtp_send(
            account,
            to_addr=to_addr,
            subject=subject,
            body=body,
            body_html=html if fmt == "html" else None,
            attachments=attachments,
        )
        return VoxboxMailService._store_sent(
            db,
            account,
            to_addr=to_addr,
            subject=subject,
            body=body,
            msg=msg,
            body_html=html if fmt == "html" else None,
            has_attachment=bool(attachments),
        )

    @staticmethod
    def ai_reply(db: Session, payload: VoxboxAiReplyIn) -> dict[str, Any]:
        from app.services.agents.base import AgentMessage
        from app.services.providers.openai_service import OpenAIProviderService

        tone = (payload.tone or "professional").strip() or "professional"
        if payload.mode == "fix":
            user_prompt = (
                f"Rewrite and improve this email draft. Fix grammar, spelling, clarity and make the tone {tone}. "
                "Keep the author's intent and any links intact.\n\n"
                f"Original email being answered:\nFrom: {payload.from_}\nSubject: {payload.subject}\n{payload.body}\n\n"
                f"My draft:\n{payload.draft}"
            )
        else:
            user_prompt = (
                f"Write a {tone} reply to this email.\n\n"
                f"From: {payload.from_}\nSubject: {payload.subject}\n\n{payload.body}"
            )
        system = (
            "You write email replies for VoxBulk (Voxbox unified inbox). "
            "Return only the reply body text, no subject line, no markdown fences, "
            "no placeholders in brackets unless unavoidable. Keep it concise and actionable."
        )
        try:
            resp = OpenAIProviderService.complete(
                db,
                system_prompt=system,
                messages=[AgentMessage(role="user", content=user_prompt)],
                provider="deepseek",
                max_tokens=1200,
                temperature=0.4,
            )
            reply = (getattr(resp, "assistant_text", None) or "").strip()
            return {"reply": reply, "error": None if reply else "Empty AI response"}
        except Exception as exc:
            logger.exception("voxbox_ai_reply_failed")
            return {"reply": "", "error": f"AI request failed: {exc}"}
