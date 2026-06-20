"""Outbound billing emails from billing@voxbulk.com (platform SMTP credentials)."""

from __future__ import annotations

import logging
import re
from typing import Any

from sqlalchemy.orm import Session

from app.services.billing_mailbox_settings_service import BillingMailboxSettingsService
from app.services.email_template_service import EmailTemplateService
from app.services.smtp_mailer_service import SmtpMailerError, SmtpMailerService
from app.services.transactional_email_service import TransactionalEmailService, substitute_placeholders

logger = logging.getLogger(__name__)

_HTML_TAG_RE = re.compile(r"<[a-z][\s\S]*?>", re.I)

BILLING_TEMPLATE_KEYS = frozenset(
    {
        "new_invoice",
        "payment_failed",
        "payment_receipt",
        "billing_cancellation_requested",
        "billing_cancellation_reversed",
        "billing_wallet_credit_issued",
        "billing_bank_refund_approved",
        "billing_refund_request_rejected",
        "billing_subscription_ended",
        "billing_renewal_reminder",
        "billing_pending_invoice_reminder",
        "billing_payment_action_required",
    }
)


def billing_from_address(db: Session) -> tuple[str, str]:
    row = BillingMailboxSettingsService.get_row(db)
    email = str(row.mailbox_email or "billing@voxbulk.com").strip().lower()
    return "VOXBULK Billing", email


def is_billing_template(template_key: str) -> bool:
    key = str(template_key or "").strip().lower()
    return key in BILLING_TEMPLATE_KEYS or key.startswith("billing_")


def _looks_like_html(text: str) -> bool:
    return bool(_HTML_TAG_RE.search(str(text or "")))


def _deliver_billing_message(
    db: Session,
    *,
    to_addr: str,
    subject: str,
    body: str,
    attachments: list[dict[str, Any]] | None = None,
) -> None:
    from_name, from_email = billing_from_address(db)
    clean_body = str(body or "")
    try:
        if _looks_like_html(clean_body):
            SmtpMailerService.send_html(
                db,
                to_addr=to_addr,
                subject=subject,
                body=clean_body,
                attachments=attachments,
                from_email=from_email,
                from_name=from_name,
            )
        else:
            SmtpMailerService.send_plain(
                db,
                to_addr=to_addr,
                subject=subject,
                body=clean_body or subject,
                attachments=attachments,
                from_email=from_email,
                from_name=from_name,
            )
    except SmtpMailerError as exc:
        if not _looks_like_html(clean_body):
            raise
        from app.services.smtp_mailer_service import _html_to_plain

        plain = _html_to_plain(clean_body) or subject
        logger.warning("billing_email_html_fallback to=%s from=%s err=%s", to_addr, from_email, exc)
        SmtpMailerService.send_plain(
            db,
            to_addr=to_addr,
            subject=subject,
            body=plain,
            attachments=attachments,
            from_email=from_email,
            from_name=from_name,
        )


class BillingEmailService:
    @staticmethod
    def send_templated_optional(
        db: Session,
        *,
        template_key: str,
        to_email: str,
        variables: dict[str, str],
        attachments: list[dict[str, Any]] | None = None,
    ) -> tuple[bool, str | None]:
        EmailTemplateService.ensure_system_templates(db)
        em = (to_email or "").strip().lower()
        if not em:
            return False, "missing_recipient"
        subject_tpl, body_tpl, is_enabled = TransactionalEmailService.load_template_fields(db, template_key=template_key)
        if not is_enabled:
            return False, "template_disabled"
        if not subject_tpl.strip() or not body_tpl.strip():
            return False, "template_empty"
        subject = substitute_placeholders(subject_tpl, variables)
        body = substitute_placeholders(body_tpl, variables)
        try:
            _deliver_billing_message(db, to_addr=em, subject=subject, body=body, attachments=attachments)
            return True, None
        except SmtpMailerError as exc:
            return False, str(exc)

    @staticmethod
    def send_template_test(
        db: Session,
        *,
        template_key: str,
        to_email: str,
        variables: dict[str, str],
        subject: str | None = None,
        body: str | None = None,
    ) -> tuple[bool, str | None]:
        key = str(template_key or "").strip().lower()
        row = EmailTemplateService.get(db, key=key)
        if row is None and not EmailTemplateService.is_system_key(key):
            return False, "Template not found"
        subject_tpl = (subject or (row.subject if row else "") or "").strip()
        body_tpl = (body or (row.body if row else "") or "").strip()
        if not subject_tpl or not body_tpl:
            return False, "template_empty"
        em = (to_email or "").strip().lower()
        if not em:
            return False, "missing_recipient"
        sub = substitute_placeholders(subject_tpl, variables)
        html = substitute_placeholders(body_tpl, variables)
        try:
            _deliver_billing_message(db, to_addr=em, subject=sub, body=html)
            return True, None
        except SmtpMailerError as exc:
            return False, str(exc)
