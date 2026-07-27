"""IMAP inbound sync for Apify / AI Team campaign replies."""

from __future__ import annotations

import email.utils
import imaplib
import logging
from email import message_from_bytes
from email.header import decode_header
from email.message import Message
from typing import Any

from sqlalchemy.orm import Session

from app.core.encryption import get_encryptor
from app.models.ai_team_settings import AiTeamSettings
from app.services.ai_team_campaign_service import AiTeamCampaignService
from app.services.ai_team_service import AiTeamService, AiTeamServiceError

logger = logging.getLogger(__name__)


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
    if chunks:
        return "\n".join(chunks).strip()
    # Fallback: strip HTML if only HTML part exists
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                payload = part.get_payload(decode=True)
                if payload:
                    raw = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
                    return re_sub_tags(raw)
    return ""


def re_sub_tags(html: str) -> str:
    import re

    text = re.sub(r"(?is)<(script|style).*?>.*?(</\1>)", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


class AiTeamImapService:
    @staticmethod
    def _imap_password(settings: AiTeamSettings) -> str:
        if settings.imap_password_enc:
            return get_encryptor().decrypt_str(settings.imap_password_enc)
        if settings.smtp_password_enc:
            return get_encryptor().decrypt_str(settings.smtp_password_enc)
        return ""

    @staticmethod
    def _connect(settings: AiTeamSettings) -> imaplib.IMAP4:
        host = (settings.imap_host or settings.smtp_host or "").strip()
        use_ssl = bool(settings.imap_use_ssl) if settings.imap_host else True
        use_tls = bool(settings.imap_use_tls)
        port = int(settings.imap_port or (993 if use_ssl else 143))
        if not host:
            raise AiTeamServiceError("IMAP host is not configured (Sending → IMAP)")
        if use_ssl:
            return imaplib.IMAP4_SSL(host, port)
        conn = imaplib.IMAP4(host, port)
        if use_tls:
            conn.starttls()
        return conn

    @staticmethod
    def test_connection(db: Session) -> dict[str, Any]:
        settings = AiTeamService.get_settings(db)
        user = (settings.imap_username or settings.smtp_username or "").strip()
        pwd = AiTeamImapService._imap_password(settings)
        if not user or not pwd:
            raise AiTeamServiceError("IMAP username and password are required (or reuse SMTP password)")
        try:
            conn = AiTeamImapService._connect(settings)
            try:
                conn.login(user, pwd)
                typ, _ = conn.select("INBOX", readonly=True)
                if typ != "OK":
                    raise AiTeamServiceError("Could not open INBOX")
            finally:
                try:
                    conn.logout()
                except Exception:
                    pass
        except AiTeamServiceError:
            raise
        except Exception as exc:
            raise AiTeamServiceError(f"IMAP connection failed: {exc}") from exc
        return {"ok": True, "message": "IMAP connection OK"}

    @staticmethod
    def sync_inbox(db: Session, *, limit: int = 50) -> dict[str, Any]:
        """Fetch UNSEEN messages, match From → campaign recipients, mark Seen."""
        settings = AiTeamService.get_settings(db)
        user = (settings.imap_username or settings.smtp_username or "").strip()
        pwd = AiTeamImapService._imap_password(settings)
        if not (settings.imap_host or settings.smtp_host):
            raise AiTeamServiceError("Configure IMAP host under Sending (or SMTP host to reuse)")
        if not user or not pwd:
            raise AiTeamServiceError("IMAP username/password missing — save under Sending")

        matched = 0
        scanned = 0
        unmatched = 0
        try:
            conn = AiTeamImapService._connect(settings)
            try:
                conn.login(user, pwd)
                typ, _ = conn.select("INBOX")
                if typ != "OK":
                    raise AiTeamServiceError("Could not open INBOX")
                typ, data = conn.search(None, "UNSEEN")
                if typ != "OK":
                    raise AiTeamServiceError("IMAP SEARCH failed")
                ids = (data[0] or b"").split()
                # Newest first
                ids = list(reversed(ids))[: max(1, min(int(limit or 50), 200))]
                for num in ids:
                    scanned += 1
                    typ, msg_data = conn.fetch(num, "(RFC822)")
                    if typ != "OK" or not msg_data or not msg_data[0]:
                        continue
                    raw = msg_data[0][1]
                    if not isinstance(raw, (bytes, bytearray)):
                        continue
                    msg = message_from_bytes(bytes(raw))
                    subject = _decode_mime(msg.get("Subject"))
                    from_hdr = _decode_mime(msg.get("From"))
                    from_email = email.utils.parseaddr(from_hdr)[1] if from_hdr else ""
                    body = _collect_text(msg)
                    row = AiTeamCampaignService.record_inbound_reply(
                        db,
                        from_email=from_email,
                        subject=subject,
                        body=body,
                    )
                    if row is not None:
                        matched += 1
                    else:
                        unmatched += 1
                    try:
                        conn.store(num, "+FLAGS", "\\Seen")
                    except Exception:
                        logger.warning("ai_team_imap_mark_seen_failed num=%s", num)
            finally:
                try:
                    conn.logout()
                except Exception:
                    pass
        except AiTeamServiceError as exc:
            settings.imap_last_sync_at = AiTeamService._now()
            settings.imap_last_sync_message = str(exc)[:500]
            db.add(settings)
            db.commit()
            raise
        except Exception as exc:
            settings.imap_last_sync_at = AiTeamService._now()
            settings.imap_last_sync_message = f"IMAP sync failed: {exc}"[:500]
            db.add(settings)
            db.commit()
            raise AiTeamServiceError(f"IMAP sync failed: {exc}") from exc

        msg = f"Scanned {scanned} unread · matched {matched} · unmatched {unmatched}"
        settings.imap_last_sync_at = AiTeamService._now()
        settings.imap_last_sync_message = msg[:500]
        db.add(settings)
        db.commit()
        return {
            "ok": True,
            "scanned": scanned,
            "matched": matched,
            "unmatched": unmatched,
            "message": msg,
            "imap_last_sync_at": settings.imap_last_sync_at.isoformat() if settings.imap_last_sync_at else None,
            "imap_last_sync_message": settings.imap_last_sync_message,
        }
