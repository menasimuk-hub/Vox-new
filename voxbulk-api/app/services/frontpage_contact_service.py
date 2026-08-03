"""Frontpage contact form — open a Support ticket + email sales inbox via Admin SMTP."""
from __future__ import annotations

import html
import logging
import os
import re

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.membership import OrganisationMembership
from app.models.user import User
from app.services.smtp_mailer_service import SmtpMailerError, SmtpMailerService
from app.services.support_ticket_service import SupportTicketService

logger = logging.getLogger(__name__)

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class FrontpageContactError(ValueError):
    pass


def contact_inbox() -> str:
    return (
        str(os.environ.get("FRONTPAGE_CONTACT_INBOX") or "").strip()
        or "hello@voxbulk.com"
    )


def _resolve_ticket_actor(db: Session, from_addr: str) -> tuple[str, str]:
    """Prefer matching customer by email; else platform org + owner."""
    addr = (from_addr or "").strip().lower()
    if addr and "@" in addr:
        user = db.execute(select(User).where(func.lower(User.email) == addr).limit(1)).scalar_one_or_none()
        if user is not None:
            membership = db.execute(
                select(OrganisationMembership)
                .where(OrganisationMembership.user_id == user.id)
                .order_by(OrganisationMembership.created_at.asc())
                .limit(1)
            ).scalar_one_or_none()
            if membership is not None:
                return str(membership.org_id), str(user.id)

    from app.services.sales_automation_service import SalesAutomationService

    org_id = SalesAutomationService._platform_org_id(db)
    if not org_id:
        raise FrontpageContactError("Support inbox is not ready yet. Please try again later.")

    owner = db.execute(
        select(OrganisationMembership.user_id)
        .where(
            OrganisationMembership.org_id == org_id,
            OrganisationMembership.role.in_(["owner", "manager"]),
        )
        .limit(1)
    ).scalar_one_or_none()
    if owner:
        return str(org_id), str(owner)

    any_user = db.execute(
        select(OrganisationMembership.user_id).where(OrganisationMembership.org_id == org_id).limit(1)
    ).scalar_one_or_none()
    if any_user:
        return str(org_id), str(any_user)

    fallback_user = db.execute(select(User.id).order_by(User.created_at.asc()).limit(1)).scalar_one_or_none()
    if not fallback_user:
        raise FrontpageContactError("Support inbox is not ready yet. Please try again later.")
    return str(org_id), str(fallback_user)


def _create_contact_ticket(
    db: Session,
    *,
    name: str,
    email: str,
    message: str,
    company: str | None,
) -> str | None:
    """Create a Support ticket for the website contact. Returns public_ref or None on soft failure."""
    org_id, user_id = _resolve_ticket_actor(db, email)
    company_line = f"Company: {company}\n" if company else ""
    body = (
        f"From: {name} <{email}>\n"
        f"{company_line}"
        f"Source: voxbulk.com/contact\n\n"
        f"{message}"
    )[:8000]
    subject = f"[Website] Contact from {name}"[:240]
    ticket = SupportTicketService.create_ticket(
        db,
        org_id=org_id,
        user_id=user_id,
        category="technical",
        subject=subject,
        message=body,
        priority="normal",
        staff_note=f"Frontpage contact form · reply-to {email}",
    )
    return ticket.public_ref


def send_frontpage_contact(
    db: Session,
    *,
    name: str,
    email: str,
    message: str,
    company: str | None = None,
    website: str | None = None,
) -> dict:
    """website is a honeypot — if filled, silently accept without sending or ticket."""
    if str(website or "").strip():
        logger.info("frontpage_contact_honeypot_dropped")
        return {"ok": True, "skipped": True}

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

    ticket_ref: str | None = None
    try:
        ticket_ref = _create_contact_ticket(
            db,
            name=name_s,
            email=email_s,
            message=message_s,
            company=company_s or None,
        )
    except FrontpageContactError:
        raise
    except Exception:
        logger.exception("frontpage_contact_ticket_failed email=%s", email_s)
        raise FrontpageContactError(
            "Could not open a support ticket right now. Please try again later or email hello@voxbulk.com."
        )

    to_addr = contact_inbox()
    subject = f"VoxBulk website contact — {name_s}"
    if ticket_ref:
        subject = f"{subject} ({ticket_ref})"
    body_html = (
        f"<p><strong>Name:</strong> {html.escape(name_s)}</p>"
        f"<p><strong>Email:</strong> {html.escape(email_s)}</p>"
        f"<p><strong>Company:</strong> {html.escape(company_s or '—')}</p>"
        f"<p><strong>Ticket:</strong> {html.escape(ticket_ref or '—')}</p>"
        f"<p><strong>Message:</strong></p>"
        f"<p>{html.escape(message_s).replace(chr(10), '<br/>')}</p>"
    )
    plain = (
        f"Name: {name_s}\nEmail: {email_s}\nCompany: {company_s or '—'}\n"
        f"Ticket: {ticket_ref or '—'}\n\n{message_s}\n"
    )
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
        except SmtpMailerError:
            # Ticket already exists — do not fail the visitor for email delivery issues.
            logger.exception("frontpage_contact_smtp_failed ticket=%s to=%s", ticket_ref, to_addr)

    logger.info("frontpage_contact_sent to=%s ticket=%s", to_addr, ticket_ref)
    return {"ok": True, "ticket_ref": ticket_ref, "emailed_to": to_addr}
