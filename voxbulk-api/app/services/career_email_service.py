"""Interview/careers outreach — same SMTP transport as Admin → Email send-test."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.services.career_mailbox_settings_service import CareerMailboxSettingsService
from app.services.email_template_service import EmailTemplateService
from app.services.smtp_mailer_service import SmtpMailerError
from app.services.smtp_settings_service import SmtpSettingsService
from app.services.transactional_email_service import _deliver_message, substitute_placeholders

logger = logging.getLogger(__name__)


def careers_reply_to(db: Session) -> str:
    row = CareerMailboxSettingsService.get_row(db)
    return str(row.mailbox_email or "careers@voxbulk.com").strip().lower()


def interview_email_delivery_status(db: Session) -> dict[str, Any]:
    row = SmtpSettingsService.get_row(db)
    configured, missing = SmtpSettingsService.compute_status(row)
    return {
        "smtp_configured": configured,
        "smtp_enabled": bool(row.is_enabled),
        "smtp_missing_fields": missing,
        "smtp_from_email": str(row.from_email or "").strip(),
        "smtp_from_name": str(row.from_name or "").strip(),
        "careers_reply_to": careers_reply_to(db),
        "can_send_email": configured and row.is_enabled,
    }


def _render_interview_template(
    db: Session,
    *,
    template_key: str,
    variables: dict[str, str],
) -> tuple[str, str] | None:
    from app.data.system_email_defaults import SYSTEM_EMAIL_DEFAULTS
    from app.services.email_template_service import EMAIL_TEMPLATE_KEYS

    k = (template_key or "").strip().lower()
    if k not in EMAIL_TEMPLATE_KEYS:
        return None
    EmailTemplateService.ensure_system_templates(db)
    subject_tpl, body_tpl, _enabled = EmailTemplateService.get_send_content(db, key=k)
    if not str(subject_tpl).strip() and not str(body_tpl).strip():
        defaults = SYSTEM_EMAIL_DEFAULTS.get(k, {})
        subject_tpl = str(defaults.get("subject") or "")
        body_tpl = str(defaults.get("body") or "")
    if not str(subject_tpl).strip() and not str(body_tpl).strip():
        return None
    subject = substitute_placeholders(subject_tpl, variables).strip() or k.replace("_", " ").title()
    body = substitute_placeholders(body_tpl, variables)
    return subject, body


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
        to_addr = str(to_email or "").strip().lower()
        if not to_addr or "@" not in to_addr:
            return False, "missing_recipient"
        rendered = _render_interview_template(db, template_key=template_key, variables=variables)
        if rendered is None:
            return False, "empty_template"
        subject, body = rendered
        try:
            CareerEmailService.send(
                db,
                to_email=to_addr,
                subject=subject,
                body=body,
                attachments=attachments,
            )
        except SmtpMailerError as exc:
            logger.warning(
                "career_email_smtp_failed template_key=%s to=%s err=%s",
                template_key,
                to_addr,
                exc,
            )
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
        """Send interview email using admin SMTP settings (identical path to send-test)."""
        sent_ok, err = CareerEmailService.send_templated_optional(
            db,
            template_key=template_key,
            to_email=to_email,
            variables=variables,
            attachments=attachments,
        )
        if sent_ok:
            return True, None
        return False, err or "send_failed"

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
        to_addr = str(to_email or "").strip().lower()
        if not to_addr or "@" not in to_addr:
            raise SmtpMailerError("Invalid recipient email address.")
        reply = str(reply_to or careers_reply_to(db)).strip()
        _deliver_message(
            db,
            to_addr=to_addr,
            subject=subject,
            body=body,
            attachments=attachments,
            reply_to=reply,
        )
        logger.info("career_email_sent to=%s subject=%s reply_to=%s", to_addr, subject[:80], reply)

    @staticmethod
    def send_template_test(
        db: Session,
        *,
        template_key: str,
        to_email: str,
        variables: dict[str, str] | None = None,
    ) -> tuple[bool, str | None]:
        """Admin template send-test for interview_* — identical code path to launch invites."""
        from app.services.transactional_email_service import EMAIL_TEST_VARIABLES

        merged = dict(EMAIL_TEST_VARIABLES)
        if variables:
            merged.update({str(k): str(v) for k, v in variables.items()})
        return CareerEmailService.send_templated_critical(
            db,
            template_key=template_key,
            to_email=to_email,
            variables=merged,
        )
