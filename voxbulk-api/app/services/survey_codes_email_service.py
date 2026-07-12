"""Outbound promo-code emails from survey.codes@voxbulk.com after AI follow-up."""

from __future__ import annotations

import logging
import re
from typing import Any

from sqlalchemy.orm import Session

from app.services.email_template_service import EmailTemplateService
from app.services.smtp_mailer_service import SmtpMailerError, SmtpMailerService
from app.services.survey_codes_mailbox_settings_service import SurveyCodesMailboxSettingsService
from app.services.transactional_email_service import TransactionalEmailService, substitute_placeholders

logger = logging.getLogger(__name__)

_HTML_TAG_RE = re.compile(r"<[a-z][\s\S]*?>", re.I)

SURVEY_AI_FOLLOWUP_PROMO_TEMPLATE_KEY = "survey_ai_followup_promo"


def _looks_like_html(text: str) -> bool:
    return bool(_HTML_TAG_RE.search(str(text or "")))


def _smtp_auth_override(db: Session) -> tuple[str | None, str | None]:
    """When mailbox password is set, authenticate as that mailbox on platform SMTP host."""
    row = SurveyCodesMailboxSettingsService.get_row(db)
    pwd = SurveyCodesMailboxSettingsService.get_decrypted_password(db)
    if not pwd:
        return None, None
    username = (row.smtp_username or row.mailbox_email or "").strip() or None
    return username, pwd


def _deliver(
    db: Session,
    *,
    to_addr: str,
    subject: str,
    body: str,
) -> None:
    from_name, from_email = SurveyCodesMailboxSettingsService.from_address(db)
    smtp_username, smtp_password = _smtp_auth_override(db)
    clean_body = str(body or "")
    kwargs: dict[str, Any] = {
        "to_addr": to_addr,
        "subject": subject,
        "from_email": from_email,
        "from_name": from_name,
        "smtp_username": smtp_username,
        "smtp_password": smtp_password,
    }
    try:
        if _looks_like_html(clean_body):
            SmtpMailerService.send_html(db, body=clean_body, **kwargs)
        else:
            SmtpMailerService.send_plain(db, body=clean_body or subject, **kwargs)
    except SmtpMailerError as exc:
        if not _looks_like_html(clean_body):
            raise
        from app.services.smtp_mailer_service import _html_to_plain

        plain = _html_to_plain(clean_body) or subject
        logger.warning("survey_codes_email_html_fallback to=%s from=%s err=%s", to_addr, from_email, exc)
        SmtpMailerService.send_plain(db, body=plain, **kwargs)


def send_followup_promo_email(
    db: Session,
    *,
    to_email: str | None,
    org_name: str,
    promo_code: str,
    promo_description: str | None = None,
    customer_name: str | None = None,
) -> dict[str, Any]:
    """
    Send promo code after a completed AI follow-up call.
    Returns a small status dict for job outcome (never raises to hangup handler).
    """
    row = SurveyCodesMailboxSettingsService.get_row(db)
    em = (to_email or "").strip().lower()
    code = (promo_code or "").strip()
    if not em or "@" not in em:
        return {"ok": False, "reason": "missing_recipient_email"}
    if not code:
        return {"ok": False, "reason": "missing_promo_code"}
    if not row.is_enabled:
        return {"ok": False, "reason": "survey_codes_mailbox_disabled"}

    try:
        EmailTemplateService.ensure_system_templates(db)
        subject_tpl, body_tpl, is_enabled = TransactionalEmailService.load_template_fields(
            db, template_key=SURVEY_AI_FOLLOWUP_PROMO_TEMPLATE_KEY
        )
        if not is_enabled:
            return {"ok": False, "reason": "template_disabled"}
        if not subject_tpl.strip() or not body_tpl.strip():
            return {"ok": False, "reason": "template_empty"}

        variables = {
            "customer_name": (customer_name or "").strip() or "there",
            "organisation_name": (org_name or "").strip() or "the business",
            "promo_code": code,
            "promo_description": (promo_description or "").strip()
            or "a thank-you offer for your feedback",
            "support_email": SurveyCodesMailboxSettingsService.from_address(db)[1],
        }
        subject = substitute_placeholders(subject_tpl, variables)
        body = substitute_placeholders(body_tpl, variables)
        _deliver(db, to_addr=em, subject=subject, body=body)
        logger.info("survey_ai_followup_promo_sent to=%s code=%s", em, code)
        return {"ok": True, "to": em, "from": variables["support_email"], "promo_code": code}
    except Exception as exc:
        logger.exception("survey_ai_followup_promo_failed to=%s", em)
        return {"ok": False, "reason": "send_failed", "error": str(exc)[:300]}
