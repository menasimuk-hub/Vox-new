"""Send interview emails from careers@voxbulk.com."""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import Session

from app.services.career_mailbox_settings_service import CareerMailboxSettingsService
from app.services.email_template_service import EmailTemplateService
from app.services.smtp_mailer_service import SmtpMailerError, SmtpMailerService
from app.services.transactional_email_service import substitute_placeholders

_HTML_TAG_RE = re.compile(r"<[a-z][\s\S]*?>", re.I)


def careers_from_address(db: Session) -> tuple[str, str]:
    row = CareerMailboxSettingsService.get_row(db)
    email = str(row.mailbox_email or "careers@voxbulk.com").strip().lower()
    return "VOXBULK Careers", email


def _looks_like_html(text: str) -> bool:
    return bool(_HTML_TAG_RE.search(str(text or "")))


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
            return False, None
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
    def send(
        db: Session,
        *,
        to_email: str,
        subject: str,
        body: str,
        attachments: list[dict[str, Any]] | None = None,
    ) -> None:
        from_name, from_email = careers_from_address(db)
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
            )
