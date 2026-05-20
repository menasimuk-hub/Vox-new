from __future__ import annotations

import logging
import re
from typing import Any

from sqlalchemy.orm import Session

from app.services.email_template_service import EMAIL_TEMPLATE_KEYS, EmailTemplateService
from app.services.smtp_mailer_service import SmtpMailerError, SmtpMailerService

logger = logging.getLogger(__name__)

_PLACEHOLDER = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")

EMAIL_TEST_VARIABLES: dict[str, str] = {
    "user_email": "test@example.com",
    "user_name": "Alex Demo",
    "first_name": "Alex",
    "last_name": "Demo",
    "clinic_name": "Demo Clinic",
    "organisation_name": "Demo Organisation",
    "amount": "£49.99",
    "invoice_number": "INV-1001",
    "invoice_id": "INV-1001",
    "amount_gbp_pence": "4999",
    "currency": "GBP",
    "invoice_status": "open",
    "message": "This is a test notification from the admin console.",
    "code": "123456",
    "date": "20 May 2026",
    "time": "14:30",
    "reset_link": "https://example.com/reset/demo-token",
    "reset_url": "https://example.com/reset/demo-token",
    "appointment_date": "21 May 2026",
    "appointment_time": "10:30",
    "patient_name": "Jamie Demo",
    "doctor_name": "Dr. Smith",
}


def substitute_placeholders(template: str, variables: dict[str, str]) -> str:
    if not template:
        return ""

    def repl(m: re.Match[str]) -> str:
        key = m.group(1)
        return variables.get(key, m.group(0))

    return _PLACEHOLDER.sub(repl, template)


class TransactionalEmailService:
    """Sends SMTP mail using persisted templates + simple {{placeholder}} substitution."""

    @staticmethod
    def send_templated_optional(
        db: Session,
        *,
        template_key: str,
        to_email: str,
        variables: dict[str, str],
    ) -> tuple[bool, str | None]:
        """
        Sends if template exists, is enabled, and SMTP works.
        Never raises SMTP errors to callers (product flows stay stable).

        Returns: (attempted_mail_send, error_message_or_none)
        """
        k = (template_key or "").strip().lower()
        if k not in EMAIL_TEMPLATE_KEYS:
            return False, "unknown_template"

        row = EmailTemplateService.get(db, key=k)
        if row is None or not row.is_enabled:
            logger.info("transactional_skip_disabled", extra={"template": k})
            return False, None

        to_addr = (to_email or "").strip().lower()
        if not to_addr:
            return False, "missing_recipient"

        subject = substitute_placeholders(row.subject or "", variables)
        body = substitute_placeholders(row.body or "", variables)
        try:
            SmtpMailerService.send_html(db, to_addr=to_addr, subject=subject, body=body)
        except SmtpMailerError as e:
            logger.warning("transactional_smtp_failed", extra={"template": k, "err": str(e)})
            return False, str(e)
        return True, None

    @staticmethod
    def send_template_test(
        db: Session,
        *,
        template_key: str,
        to_email: str,
        subject: str | None = None,
        body: str | None = None,
        variables: dict[str, str] | None = None,
    ) -> tuple[bool, str | None]:
        """Send a test email using draft or saved template content with dummy placeholder data."""
        k = (template_key or "").strip().lower()
        row = EmailTemplateService.get(db, key=k)
        if row is None:
            return False, "Template not found"

        to_addr = (to_email or "").strip().lower()
        if not to_addr:
            return False, "Recipient email is required"

        merged_vars = dict(EMAIL_TEST_VARIABLES)
        if variables:
            merged_vars.update({str(key): "" if val is None else str(val) for key, val in variables.items()})

        raw_subject = (subject if subject is not None else row.subject or "").strip()
        raw_body = body if body is not None else row.body or ""
        if not raw_subject and not str(raw_body).strip():
            return False, "Template subject and body are empty"

        rendered_subject = substitute_placeholders(raw_subject, merged_vars).strip() or f"Test: {k}"
        if not rendered_subject.lower().startswith("[test]"):
            rendered_subject = f"[TEST] {rendered_subject}"
        rendered_body = substitute_placeholders(str(raw_body or ""), merged_vars)

        try:
            SmtpMailerService.send_html(
                db,
                to_addr=to_addr,
                subject=rendered_subject,
                body=rendered_body,
            )
        except SmtpMailerError as e:
            return False, str(e)
        return True, None
