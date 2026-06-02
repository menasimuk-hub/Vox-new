"""Send interview emails from careers@voxbulk.com."""

from __future__ import annotations

import logging
import re
from typing import Any

from sqlalchemy.orm import Session

from app.services.career_mailbox_settings_service import CareerMailboxSettingsService
from app.services.email_template_service import EmailTemplateService
from app.services.smtp_mailer_service import SmtpMailerError, SmtpMailerService
from app.services.transactional_email_service import substitute_placeholders

logger = logging.getLogger(__name__)

_HTML_TAG_RE = re.compile(r"<[a-z][\s\S]*?>", re.I)


def careers_from_address(db: Session) -> tuple[str, str]:
    row = CareerMailboxSettingsService.get_row(db)
    email = str(row.mailbox_email or "careers@voxbulk.com").strip().lower()
    return "VOXBULK Careers", email


def _looks_like_html(text: str) -> bool:
    return bool(_HTML_TAG_RE.search(str(text or "")))


def _resend_api_key(db: Session) -> str:
    from app.core.config import get_settings
    from app.services.provider_settings import ProviderSettingsService

    env_key = str(get_settings().resend_api_key or "").strip()
    if env_key:
        return env_key
    cfg, _ = ProviderSettingsService.get_platform_config_decrypted(db, provider="resend")
    return str((cfg or {}).get("api_key") or "").strip()


def interview_email_delivery_status(db: Session) -> dict[str, Any]:
    """Diagnostics returned on launch / send-invites when email fails."""
    from app.services.smtp_settings_service import SmtpSettingsService

    row = SmtpSettingsService.get_row(db)
    configured, missing = SmtpSettingsService.compute_status(row)
    resend_key = _resend_api_key(db)
    return {
        "smtp_configured": configured,
        "smtp_enabled": bool(row.is_enabled),
        "smtp_missing_fields": missing,
        "resend_configured": bool(resend_key),
        "can_send_email": (configured and row.is_enabled) or bool(resend_key),
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
                "career_email_failed template_key=%s to=%s smtp_err=%s delivery=%s",
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
    def _send_via_resend(
        db: Session,
        *,
        to_addr: str,
        subject: str,
        body: str,
        from_email: str,
        from_name: str,
    ) -> None:
        from app.services.resend_service import ResendService, ResendServiceError

        api_key = _resend_api_key(db)
        if not api_key:
            raise SmtpMailerError("No SMTP and no Resend API key — configure Admin → Email → SMTP or Resend integration")
        from_line = f"{from_name} <{from_email}>" if from_name else from_email
        plain = body
        if _looks_like_html(body):
            from app.services.smtp_mailer_service import _html_to_plain

            plain = _html_to_plain(body) or "Please view this message in an HTML-capable email client."
        try:
            ResendService.send_email(
                api_key,
                from_email=from_line,
                to_email=to_addr,
                subject=subject,
                text=plain,
                html=body if _looks_like_html(body) else None,
            )
        except ResendServiceError as exc:
            raise SmtpMailerError(str(exc)) from exc
        logger.info("career_email_sent_via_resend to=%s subject=%s", to_addr, subject[:80])

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
        smtp_error: SmtpMailerError | None = None
        try:
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
            return
        except SmtpMailerError as exc:
            smtp_error = exc
            logger.warning("career_email_smtp_failed to=%s err=%s — trying Resend", to_addr, exc)
        if attachments:
            raise smtp_error or SmtpMailerError("SMTP failed and Resend cannot send attachments")
        try:
            CareerEmailService._send_via_resend(
                db,
                to_addr=to_addr,
                subject=subject,
                body=body,
                from_email=from_email,
                from_name=from_name,
            )
        except SmtpMailerError:
            raise
        except Exception as exc:
            raise SmtpMailerError(
                f"SMTP failed ({smtp_error}); Resend failed ({exc})"
            ) from exc
