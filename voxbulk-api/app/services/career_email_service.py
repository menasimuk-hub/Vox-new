"""Send interview emails (SMTP from admin settings; Reply-To careers mailbox)."""

from __future__ import annotations

import logging
import re
from typing import Any

from sqlalchemy.orm import Session

from app.services.career_mailbox_settings_service import CareerMailboxSettingsService
from app.services.email_template_service import EmailTemplateService
from app.services.smtp_mailer_service import SmtpMailerError, SmtpMailerService
from app.services.smtp_settings_service import SmtpSettingsService
from app.services.transactional_email_service import substitute_placeholders

logger = logging.getLogger(__name__)

_HTML_TAG_RE = re.compile(r"<[a-z][\s\S]*?>", re.I)


def careers_reply_to(db: Session) -> str:
    row = CareerMailboxSettingsService.get_row(db)
    return str(row.mailbox_email or "careers@voxbulk.com").strip().lower()


def smtp_from_address(db: Session) -> tuple[str, str]:
    """Use the same From address as Admin → Email SMTP (matches send-test)."""
    row = SmtpSettingsService.get_row(db)
    email = str(row.from_email or "").strip()
    name = str(row.from_name or "VOXBULK").strip()
    if email and "@" in email:
        return name, email
    return "VOXBULK Careers", careers_reply_to(db)


def interview_email_delivery_status(db: Session) -> dict[str, Any]:
    """Diagnostics returned on launch / send-invites when email fails."""
    row = SmtpSettingsService.get_row(db)
    configured, missing = SmtpSettingsService.compute_status(row)
    return {
        "smtp_configured": configured,
        "smtp_enabled": bool(row.is_enabled),
        "smtp_missing_fields": missing,
        "smtp_from_email": str(row.from_email or "").strip(),
        "careers_reply_to": careers_reply_to(db),
        "can_send_email": configured and row.is_enabled,
    }


class CareerEmailService:
    @staticmethod
    def send_templated_optional(
        db: Session,
        *,
        template_key: str,
        to_email: str,
        variables: dict[str, str],
        attachments: list[dict[str, Any]] | None = None,
    ) -> tuple[bool, str | None]:
        from app.services.email_template_service import EMAIL_TEMPLATE_KEYS

        k = (template_key or "").strip().lower()
        if k not in EMAIL_TEMPLATE_KEYS:
            return False, "unknown_template"
        EmailTemplateService.ensure_system_templates(db)
        subject_tpl, body_tpl, is_enabled = EmailTemplateService.get_send_content(db, key=k)
        if not is_enabled:
            return False, "template_disabled"
        if not str(subject_tpl).strip() and not str(body_tpl).strip():
            return False, "empty_template"
        to_addr = str(to_email or "").strip().lower()
        if not to_addr:
            return False, "missing_recipient"
        subject = substitute_placeholders(subject_tpl, variables).strip() or k.replace("_", " ").title()
        body = substitute_placeholders(body_tpl, variables)
        try:
            CareerEmailService.send(db, to_email=to_addr, subject=subject, body=body, attachments=attachments)
        except SmtpMailerError as exc:
            return False, str(exc)
        return True, None

    @staticmethod
    def send_templated_critical(
        db: Session,
        *,
        template_key: str,
        to_email: str,
        variables: dict[str, str],
        attachments: list[dict[str, Any]] | None = None,
    ) -> tuple[bool, str | None]:
        """Send interview email; fall back to code default if admin template fails."""
        from app.data.system_email_defaults import SYSTEM_EMAIL_DEFAULTS

        to_addr = str(to_email or "").strip().lower()
        if not to_addr:
            return False, "missing_recipient"

        sent_ok, err = CareerEmailService.send_templated_optional(
            db,
            template_key=template_key,
            to_email=to_addr,
            variables=variables,
            attachments=attachments,
        )
        if sent_ok:
            return True, None

        k = str(template_key or "").strip().lower()
        defaults = SYSTEM_EMAIL_DEFAULTS.get(k, {})
        subject_tpl = str(defaults.get("subject") or "").strip()
        body_tpl = str(defaults.get("body") or "").strip()
        if not subject_tpl and not body_tpl:
            return False, err or "empty_template"

        subject = substitute_placeholders(subject_tpl, variables).strip() or k.replace("_", " ").title()
        body = substitute_placeholders(body_tpl, variables)
        try:
            CareerEmailService.send(db, to_email=to_addr, subject=subject, body=body, attachments=attachments)
        except SmtpMailerError as exc:
            logger.error(
                "career_email_failed template_key=%s to=%s err=%s delivery=%s",
                template_key,
                to_addr,
                exc,
                interview_email_delivery_status(db),
            )
            return False, str(exc)
        logger.warning(
            "career_email_sent_via_default template_key=%s to=%s reason=%s",
            template_key,
            to_addr,
            err,
        )
        return True, None

    @staticmethod
    def send(
        db: Session,
        *,
        to_email: str,
        subject: str,
        body: str,
        attachments: list[dict[str, Any]] | None = None,
        reply_to: str | None = None,
    ) -> None:
        from_name, from_email = smtp_from_address(db)
        reply = str(reply_to or careers_reply_to(db)).strip()
        to_addr = str(to_email or "").strip().lower()
        if not to_addr or "@" not in to_addr:
            raise SmtpMailerError("Invalid recipient email address.")
        if _looks_like_html(body):
            SmtpMailerService.send_html(
                db,
                to_addr=to_addr,
                subject=subject,
                body=body,
                attachments=attachments,
                from_email=from_email,
                from_name=from_name,
                reply_to=reply,
            )
        else:
            SmtpMailerService.send_plain(
                db,
                to_addr=to_addr,
                subject=subject,
                body=body,
                attachments=attachments,
                from_email=from_email,
                from_name=from_name,
                reply_to=reply,
            )


def _looks_like_html(text: str) -> bool:
    return bool(_HTML_TAG_RE.search(str(text or "")))
