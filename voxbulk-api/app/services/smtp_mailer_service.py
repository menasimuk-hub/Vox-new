from __future__ import annotations

import re
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr
from typing import Any

from sqlalchemy.orm import Session

from app.services.smtp_settings_service import SmtpSettingsService

_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _html_to_plain(text: str) -> str:
    clean = str(text or "")
    clean = re.sub(r"(?i)<br\s*/?>", "\n", clean)
    clean = re.sub(r"(?i)</p\s*>", "\n\n", clean)
    clean = _HTML_TAG_RE.sub("", clean)
    clean = re.sub(r"\n{3,}", "\n\n", clean)
    return clean.strip()


class SmtpMailerError(RuntimeError):
    pass


class SmtpMailerService:
    @staticmethod
    def _send_message(
        db: Session,
        *,
        to_addr: str,
        subject: str,
        body: str,
        html: bool,
        attachments: list[dict[str, Any]] | None = None,
        from_email: str | None = None,
        from_name: str | None = None,
        reply_to: str | None = None,
        smtp_username: str | None = None,
        smtp_password: str | None = None,
    ) -> None:
        row = SmtpSettingsService.get_row(db)
        configured, missing = SmtpSettingsService.compute_status(row)
        if not configured:
            raise SmtpMailerError("SMTP is incomplete: missing " + ", ".join(missing))
        if not row.is_enabled:
            raise SmtpMailerError("SMTP is disabled; enable it in settings before sending.")

        to_addr = (to_addr or "").strip()
        if not to_addr or "@" not in to_addr:
            raise SmtpMailerError("Invalid recipient email address.")

        host = (row.host or "").strip()
        port = int(row.port or 587)

        override_user = str(smtp_username or "").strip() or None
        override_pwd = str(smtp_password or "").strip() or None
        if override_user and override_pwd:
            username = override_user
            pwd = override_pwd
        else:
            pwd = None
            if SmtpSettingsService._needs_password(row):
                pwd = SmtpSettingsService.get_decrypted_password(db)
                if not pwd:
                    raise SmtpMailerError("SMTP password is required but not configured.")
            username = (row.username or "").strip() or None

        from_email = str(from_email or row.from_email or "").strip()
        from_name = str(from_name if from_name is not None else row.from_name or "").strip()
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = formataddr((from_name, from_email)) if from_name else from_email
        msg["To"] = to_addr
        reply = str(reply_to or "").strip()
        if reply and "@" in reply:
            msg["Reply-To"] = reply
        if html:
            plain = _html_to_plain(body)
            if not plain:
                plain = "This message contains HTML content. Open in an email client that supports HTML."
            msg.set_content(plain)
            msg.add_alternative(body or "", subtype="html", charset="utf-8")
        else:
            msg.set_content(body or "")

        for attachment in attachments or []:
            filename = str(attachment.get("filename") or "attachment.bin")
            content = attachment.get("content")
            if content is None:
                continue
            maintype = str(attachment.get("maintype") or "application")
            subtype = str(attachment.get("subtype") or "octet-stream")
            msg.add_attachment(content, maintype=maintype, subtype=subtype, filename=filename)

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

        try:
            if row.use_ssl:
                with smtplib.SMTP_SSL(host, port, context=ctx, timeout=30) as server:
                    if username and pwd is not None:
                        server.login(username, pwd)
                    server.send_message(msg)
            else:
                with smtplib.SMTP(host, port, timeout=30) as server:
                    server.ehlo()
                    if row.use_tls:
                        server.starttls(context=ctx)
                        server.ehlo()
                    if username and pwd is not None:
                        server.login(username, pwd)
                    elif username and pwd is None:
                        raise SmtpMailerError("SMTP username is set but password is missing.")
                    server.send_message(msg)
        except SmtpMailerError:
            raise
        except smtplib.SMTPAuthenticationError as e:
            raise SmtpMailerError(f"SMTP authentication failed: {e.smtp_code} {e.smtp_error.decode(errors='replace')}") from e
        except smtplib.SMTPException as e:
            raise SmtpMailerError(f"SMTP error: {e}") from e
        except OSError as e:
            raise SmtpMailerError(f"Network error contacting SMTP server: {e}") from e

    @staticmethod
    def send_plain(
        db: Session,
        *,
        to_addr: str,
        subject: str,
        body: str,
        attachments: list[dict[str, Any]] | None = None,
        from_email: str | None = None,
        from_name: str | None = None,
        reply_to: str | None = None,
        smtp_username: str | None = None,
        smtp_password: str | None = None,
    ) -> None:
        SmtpMailerService._send_message(
            db,
            to_addr=to_addr,
            subject=subject,
            body=body,
            html=False,
            attachments=attachments,
            from_email=from_email,
            from_name=from_name,
            reply_to=reply_to,
            smtp_username=smtp_username,
            smtp_password=smtp_password,
        )

    @staticmethod
    def send_html(
        db: Session,
        *,
        to_addr: str,
        subject: str,
        body: str,
        attachments: list[dict[str, Any]] | None = None,
        from_email: str | None = None,
        from_name: str | None = None,
        reply_to: str | None = None,
        smtp_username: str | None = None,
        smtp_password: str | None = None,
    ) -> None:
        """Send message with text/html MIME (for DB-backed templates that store HTML)."""
        SmtpMailerService._send_message(
            db,
            to_addr=to_addr,
            subject=subject,
            body=body,
            html=True,
            attachments=attachments,
            from_email=from_email,
            from_name=from_name,
            reply_to=reply_to,
            smtp_username=smtp_username,
            smtp_password=smtp_password,
        )
