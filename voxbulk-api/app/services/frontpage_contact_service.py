"""Frontpage contact form — email sales inbox via Admin SMTP."""
from __future__ import annotations

import html
import logging
import os
import re

from sqlalchemy.orm import Session

from app.services.smtp_mailer_service import SmtpMailerError, SmtpMailerService

logger = logging.getLogger(__name__)

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class FrontpageContactError(ValueError):
    pass


def contact_inbox() -> str:
    return (
        str(os.environ.get("FRONTPAGE_CONTACT_INBOX") or "").strip()
        or "hello@voxbulk.com"
    )


def send_frontpage_contact(
    db: Session,
    *,
    name: str,
    email: str,
    message: str,
    company: str | None = None,
    website: str | None = None,
) -> None:
    """website is a honeypot — if filled, silently accept without sending."""
    if str(website or "").strip():
        logger.info("frontpage_contact_honeypot_dropped")
        return

    name_s = str(name or "").strip()
    email_s = str(email or "").strip().lower()
    message_s = str(message or "").strip()
    company_s = str(company or "").strip()

    if len(name_s) < 2 or len(name_s) > 100:
        raise FrontpageContactError("Please enter your name")
    if not EMAIL_RE.match(email_s) or len(email_s) > 255:
        raise FrontpageContactError("Enter a valid email")
    if len(message_s) < 10 or len(message_s) > 2000:
        raise FrontpageContactError("Please write at least 10 characters")

    to_addr = contact_inbox()
    subject = f"VoxBulk website contact — {name_s}"
    body_html = (
        f"<p><strong>Name:</strong> {html.escape(name_s)}</p>"
        f"<p><strong>Email:</strong> {html.escape(email_s)}</p>"
        f"<p><strong>Company:</strong> {html.escape(company_s or '—')}</p>"
        f"<p><strong>Message:</strong></p>"
        f"<p>{html.escape(message_s).replace(chr(10), '<br/>')}</p>"
    )
    plain = f"Name: {name_s}\nEmail: {email_s}\nCompany: {company_s or '—'}\n\n{message_s}\n"
    try:
        SmtpMailerService.send_html(
            db,
            to_addr=to_addr,
            subject=subject,
            body=body_html,
            reply_to=email_s,
        )
    except SmtpMailerError:
        try:
            SmtpMailerService.send_plain(
                db,
                to_addr=to_addr,
                subject=subject,
                body=plain,
                reply_to=email_s,
            )
        except SmtpMailerError as exc:
            logger.exception("frontpage_contact_smtp_failed")
            raise FrontpageContactError(
                "Email is temporarily unavailable. Please try again later or email hello@voxbulk.com."
            ) from exc

    logger.info("frontpage_contact_sent to=%s", to_addr)
