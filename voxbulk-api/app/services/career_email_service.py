"""Interview outreach: SMTP transport with From = careers@ mailbox (not admin SMTP From)."""

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


def careers_from_address(db: Session) -> tuple[str, str]:
    """From line for all interview/careers candidate emails."""
    row = CareerMailboxSettingsService.get_row(db)
    email = str(row.mailbox_email or "careers@voxbulk.com").strip().lower()
    return "VOXBULK Careers", email


def _looks_like_html(text: str) -> bool:
    return bool(_HTML_TAG_RE.search(str(text or "")))


def _deliver_careers_message(
    db: Session,
    *,
    to_addr: str,
    subject: str,
    body: str,
    attachments: list[dict[str, Any]] | None = None,
) -> None:
    """
    Send via platform SMTP credentials but with From = careers@ (mailbox settings).
    Falls back to plain text if HTML is rejected by the mail server.
    """
    from_name, from_email = careers_from_address(db)
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
        logger.warning(
            "career_email_html_fallback to=%s from=%s err=%s",
            to_addr,
            from_email,
            exc,
        )
        SmtpMailerService.send_plain(
            db,
            to_addr=to_addr,
            subject=subject,
            body=plain,
            attachments=attachments,
            from_email=from_email,
            from_name=from_name,
        )


def interview_email_delivery_status(db: Session) -> dict[str, Any]:
    row = SmtpSettingsService.get_row(db)
    configured, missing = SmtpSettingsService.compute_status(row)
    from_name, from_email = careers_from_address(db)
    return {
        "smtp_configured": configured,
        "smtp_enabled": bool(row.is_enabled),
        "smtp_missing_fields": missing,
        "interview_from_email": from_email,
        "interview_from_name": from_name,
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
        delivery = interview_email_delivery_status(db)
        if not delivery.get("can_send_email"):
            missing = delivery.get("smtp_missing_fields") or []
            if not delivery.get("smtp_configured"):
                return False, "SMTP not configured in Admin → Email" + (
                    f" (missing: {', '.join(missing)})" if missing else ""
                )
            return False, "SMTP is disabled in Admin → Email — enable it before sending interview mail"
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
                "career_email_failed template_key=%s to=%s from=%s err=%s",
                template_key,
                to_addr,
                careers_from_address(db)[1],
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
        return CareerEmailService.send_templated_optional(
            db,
            template_key=template_key,
            to_email=to_email,
            variables=variables,
            attachments=attachments,
        )

    @staticmethod
    def send_booking_confirm_email(
        db: Session,
        *,
        to_email: str,
        variables: dict[str, str],
    ) -> tuple[bool, str | None, str]:
        """
        Send confirmation using Admin template interview_booking_confirm.
        Plain text is only used if the template render or SMTP HTML send fails.
        Returns (ok, error, channel) where channel is interview_booking_confirm | plain_fallback | none.
        """
        ok, err = CareerEmailService.send_templated_critical(
            db,
            template_key="interview_booking_confirm",
            to_email=to_email,
            variables=variables,
        )
        if ok:
            return True, None, "interview_booking_confirm"
        ok_fb, err_fb = CareerEmailService.send_booking_confirmation_fallback(
            db,
            to_email=to_email,
            variables=variables,
        )
        if ok_fb:
            logger.warning(
                "booking_confirm_used_plain_fallback to=%s template_err=%s",
                to_email,
                err,
            )
            return True, None, "plain_fallback"
        return False, err_fb or err, "none"

    @staticmethod
    def send_booking_reschedule_link_email(
        db: Session,
        *,
        to_email: str,
        variables: dict[str, str],
    ) -> tuple[bool, str | None, str]:
        """Send reschedule link by email (WA reschedule request — no WhatsApp reply)."""
        ok, err = CareerEmailService.send_templated_critical(
            db,
            template_key="interview_booking_reschedule_link",
            to_email=to_email,
            variables=variables,
        )
        if ok:
            return True, None, "interview_booking_reschedule_link"
        to_addr = str(to_email or "").strip().lower()
        if not to_addr or "@" not in to_addr:
            return False, "missing_recipient", "none"
        name = str(variables.get("candidate_name") or "there").strip()
        role = str(variables.get("role") or "Interview").strip()
        company = str(variables.get("company_name") or "the company").strip()
        slot = str(variables.get("current_slot") or "").strip()
        url = str(variables.get("reschedule_url") or variables.get("booking_url") or "").strip()
        subject = f"Reschedule your interview — {role}"
        body = (
            f"Hi {name},\n\n"
            f"Your {role} interview at {company}"
            + (f" is booked for {slot}." if slot else " is booked.")
            + "\n\n"
            f"Pick a new time here: {url}\n\n"
            "— VOXBULK Careers (careers@voxbulk.com)"
        )
        try:
            CareerEmailService.send(db, to_email=to_addr, subject=subject, body=body)
            return True, None, "plain_fallback"
        except SmtpMailerError as exc:
            return False, str(exc), "none"

    @staticmethod
    def send_booking_reminder_email(
        db: Session,
        *,
        to_email: str,
        variables: dict[str, str],
    ) -> tuple[bool, str | None, str]:
        ok, err = CareerEmailService.send_templated_critical(
            db,
            template_key="interview_booking_reminder",
            to_email=to_email,
            variables=variables,
        )
        if ok:
            return True, None, "interview_booking_reminder"
        ok_fb, err_fb = CareerEmailService.send_booking_reminder_fallback(
            db,
            to_email=to_email,
            variables=variables,
        )
        if ok_fb:
            return True, None, "plain_fallback"
        return False, err_fb or err, "none"

    @staticmethod
    def send_booking_confirmation_fallback(
        db: Session,
        *,
        to_email: str,
        variables: dict[str, str],
    ) -> tuple[bool, str | None]:
        """
        Plain confirmation when the HTML admin template fails (oversized/broken calendar block).
        Same From as other careers mail.
        """
        from app.data.system_email_defaults import SYSTEM_EMAIL_DEFAULTS

        to_addr = str(to_email or "").strip().lower()
        if not to_addr or "@" not in to_addr:
            return False, "missing_recipient"
        name = str(variables.get("candidate_name") or "there").strip()
        role = str(variables.get("role") or "Interview").strip()
        company = str(variables.get("company_name") or "the company").strip()
        date_line = str(variables.get("interview_date") or "").strip()
        time_line = str(variables.get("interview_time") or "").strip()
        subject = f"Interview confirmed — {role} on {date_line}" if date_line else f"Interview confirmed — {role}"
        meeting_url = str(variables.get("meeting_url") or "").strip()
        channel_note = str(variables.get("interview_channel_note") or "").strip()
        body = (
            f"Hi {name},\n\n"
            f"Your {role} interview at {company} is confirmed.\n\n"
            f"Date: {date_line}\n"
            f"Time: {time_line} UK time (GMT/BST)\n\n"
        )
        if meeting_url:
            body += f"Join your online meeting: {meeting_url}\n\n"
        elif channel_note:
            body += f"{channel_note}\n\n"
        else:
            body += "We will call you on the number you provided.\n\n"
        body += (
            "Need to change your time? Use the reschedule link from your original booking message.\n\n"
            "— VOXBULK Careers (careers@voxbulk.com)"
        )
        ics_url = str(variables.get("calendar_ics_url") or "").strip()
        if ics_url:
            body += f"\n\nAdd to calendar (ICS): {ics_url}"
        try:
            CareerEmailService.send(db, to_email=to_addr, subject=subject, body=body)
            return True, None
        except SmtpMailerError as exc:
            return False, str(exc)

    @staticmethod
    def send_booking_reminder_fallback(
        db: Session,
        *,
        to_email: str,
        variables: dict[str, str],
    ) -> tuple[bool, str | None]:
        to_addr = str(to_email or "").strip().lower()
        if not to_addr or "@" not in to_addr:
            return False, "missing_recipient"
        name = str(variables.get("candidate_name") or "there").strip()
        role = str(variables.get("role") or "Interview").strip()
        company = str(variables.get("company_name") or "the company").strip()
        date_line = str(variables.get("interview_date") or "").strip()
        time_line = str(variables.get("interview_time") or "").strip()
        subject = f"Reminder — {role} interview in 30 minutes"
        body = (
            f"Hi {name},\n\n"
            f"Reminder: your {role} phone interview with {company} starts in about 30 minutes.\n\n"
            f"Date: {date_line}\n"
            f"Time: {time_line} UK time (GMT/BST)\n\n"
            "Please keep your phone nearby — we will call you at the booked time.\n\n"
            "— VOXBULK Careers (careers@voxbulk.com)"
        )
        try:
            CareerEmailService.send(db, to_email=to_addr, subject=subject, body=body)
            return True, None
        except SmtpMailerError as exc:
            return False, str(exc)

    @staticmethod
    def send(
        db: Session,
        *,
        to_email: str,
        subject: str,
        body: str,
        attachments: list[dict[str, Any]] | None = None,
    ) -> None:
        to_addr = str(to_email or "").strip().lower()
        if not to_addr or "@" not in to_addr:
            raise SmtpMailerError("Invalid recipient email address.")
        from_name, from_email = careers_from_address(db)
        _deliver_careers_message(
            db,
            to_addr=to_addr,
            subject=subject,
            body=body,
            attachments=attachments,
        )
        logger.info(
            "career_email_sent from=%s <%s> to=%s subject=%s",
            from_name,
            from_email,
            to_addr,
            subject[:80],
        )

    @staticmethod
    def send_template_test(
        db: Session,
        *,
        template_key: str,
        to_email: str,
        variables: dict[str, str] | None = None,
    ) -> tuple[bool, str | None]:
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
