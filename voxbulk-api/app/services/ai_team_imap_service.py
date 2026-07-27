"""IMAP inbound sync for Apify / AI Team campaign replies."""

from __future__ import annotations

import email.utils
import imaplib
import logging
import re
from datetime import datetime, timedelta
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

_AIT_RECIPIENT_RE = re.compile(r"ait-c-([0-9a-fA-F-]{36})", re.I)


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
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                payload = part.get_payload(decode=True)
                if payload:
                    raw = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
                    return re_sub_tags(raw)
    return ""


def re_sub_tags(html: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?>.*?(</\1>)", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _extract_recipient_id(msg: Message) -> str | None:
    for hdr in ("X-VoxBulk-Recipient", "In-Reply-To", "References", "Message-ID"):
        raw = _decode_mime(msg.get(hdr))
        if not raw:
            continue
        m = _AIT_RECIPIENT_RE.search(raw)
        if m:
            return m.group(1)
        # Plain UUID header (X-VoxBulk-Recipient)
        if hdr.lower() == "x-voxbulk-recipient":
            token = raw.strip().strip("<>")
            if re.fullmatch(r"[0-9a-fA-F-]{36}", token):
                return token
    return None


def _parse_address_list(header_val: str | None) -> list[str]:
    if not header_val:
        return []
    out: list[str] = []
    for name, addr in email.utils.getaddresses([header_val]):
        _ = name
        a = (addr or "").strip().lower()
        if a and "@" in a:
            out.append(a)
    return out


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
        return {"ok": True, "message": "IMAP connection OK — login works. Matching still needs From/thread to match a campaign audience email."}

    @staticmethod
    def sync_inbox(db: Session, *, limit: int = 50, since_days: int = 7) -> dict[str, Any]:
        """Fetch recent INBOX mail, match From / Reply-To / Message-ID → campaign recipients."""
        settings = AiTeamService.get_settings(db)
        user = (settings.imap_username or settings.smtp_username or "").strip()
        pwd = AiTeamImapService._imap_password(settings)
        if not (settings.imap_host or settings.smtp_host):
            raise AiTeamServiceError(
                "Configure IMAP under Sending — SMTP is send-only and cannot fetch replies"
            )
        if not user or not pwd:
            raise AiTeamServiceError("IMAP username/password missing — save under Sending")

        matched = 0
        scanned = 0
        unmatched = 0
        unmatched_samples: list[dict[str, str]] = []
        try:
            conn = AiTeamImapService._connect(settings)
            try:
                conn.login(user, pwd)
                typ, _ = conn.select("INBOX")
                if typ != "OK":
                    raise AiTeamServiceError("Could not open INBOX")

                ids: list[bytes] = []
                seen_ids: set[bytes] = set()
                typ, data = conn.search(None, "UNSEEN")
                if typ == "OK" and data and data[0]:
                    for num in data[0].split():
                        if num not in seen_ids:
                            ids.append(num)
                            seen_ids.add(num)
                days = max(1, min(int(since_days or 7), 30))
                since = (datetime.utcnow() - timedelta(days=days)).strftime("%d-%b-%Y")
                typ, data = conn.search(None, "SINCE", since)
                if typ == "OK" and data and data[0]:
                    for num in data[0].split():
                        if num not in seen_ids:
                            ids.append(num)
                            seen_ids.add(num)

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
                    from_addrs = _parse_address_list(_decode_mime(msg.get("From")))
                    reply_addrs = _parse_address_list(_decode_mime(msg.get("Reply-To")))
                    from_email = from_addrs[0] if from_addrs else ""
                    reply_to = reply_addrs[0] if reply_addrs else ""
                    thread_rid = _extract_recipient_id(msg)
                    body = _collect_text(msg)
                    row = AiTeamCampaignService.record_inbound_reply(
                        db,
                        from_email=from_email,
                        subject=subject,
                        body=body,
                        recipient_id=thread_rid,
                        reply_to_email=reply_to,
                    )
                    if row is not None:
                        matched += 1
                    else:
                        unmatched += 1
                        if len(unmatched_samples) < 5:
                            unmatched_samples.append(
                                {
                                    "from": from_email or "(no from)",
                                    "subject": (subject or "")[:120],
                                }
                            )
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

        tip = ""
        if scanned and matched == 0:
            froms = ", ".join(s["from"] for s in unmatched_samples) or "(none)"
            tip = (
                f" · Unmatched From: {froms}. "
                "Reply FROM the same address you used in Send test / audience, "
                "or Send test again then reply (new messages get a thread id)."
            )
        msg = f"Scanned {scanned} · matched {matched} · unmatched {unmatched}{tip}"
        settings.imap_last_sync_at = AiTeamService._now()
        settings.imap_last_sync_message = msg[:500]
        db.add(settings)
        db.commit()
        return {
            "ok": True,
            "scanned": scanned,
            "matched": matched,
            "unmatched": unmatched,
            "unmatched_samples": unmatched_samples,
            "message": msg,
            "imap_last_sync_at": settings.imap_last_sync_at.isoformat() if settings.imap_last_sync_at else None,
            "imap_last_sync_message": settings.imap_last_sync_message,
        }
