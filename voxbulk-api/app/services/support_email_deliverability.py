"""Central recipient deliverability / suppression for Support Disk emails.

Blocks SMTP to anonymized account-deletion placeholders and other reserved
``.invalid`` addresses, and to users/org contacts marked deleted/inactive.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.organisation import Organisation
from app.models.user import User

ANONYMIZED_DOMAIN = "anonymized.voxbulk.invalid"


def normalize_recipient_email(value: str | None) -> str | None:
    em = (value or "").strip().lower()
    return em if em and "@" in em else None


def email_domain(email: str) -> str:
    return (email.rsplit("@", 1)[-1] or "").strip().lower()


def is_reserved_invalid_placeholder(email: str) -> bool:
    """True for anonymized.voxbulk.invalid and any reserved RFC 2606 .invalid domain."""
    domain = email_domain(email)
    if not domain:
        return True
    if domain == ANONYMIZED_DOMAIN or domain.endswith(".invalid"):
        return True
    return False


def _user_suppression_reason(user: User | None) -> str | None:
    if user is None:
        return None
    if getattr(user, "anonymized_at", None) is not None:
        return "user_anonymized"
    deletion = (getattr(user, "deletion_status", None) or "active").strip().lower()
    if deletion in {"archived", "deleted"}:
        return f"user_{deletion}"
    if getattr(user, "is_active", True) is False:
        return "user_inactive"
    user_email = normalize_recipient_email(getattr(user, "email", None))
    if user_email and is_reserved_invalid_placeholder(user_email):
        return "placeholder_domain"
    return None


def _org_contact_suppression_reason(org: Organisation | None, *, email: str) -> str | None:
    if org is None:
        return None
    contact = normalize_recipient_email(getattr(org, "contact_email", None))
    if not contact or contact != email:
        return None
    if getattr(org, "anonymized_at", None) is not None:
        return "org_contact_anonymized"
    deletion = (getattr(org, "deletion_status", None) or "active").strip().lower()
    if deletion in {"archived", "deleted"}:
        return f"org_contact_{deletion}"
    if is_reserved_invalid_placeholder(contact):
        return "placeholder_domain"
    return None


def recipient_suppression_reason(
    db: Session,
    email: str | None,
    *,
    user: User | None = None,
    organisation: Organisation | None = None,
) -> str | None:
    """Return a skip reason if this address must not receive SMTP mail."""
    em = normalize_recipient_email(email)
    if not em:
        return "missing_recipient"
    if is_reserved_invalid_placeholder(em):
        return "placeholder_domain"

    if user is not None and normalize_recipient_email(getattr(user, "email", None)) == em:
        reason = _user_suppression_reason(user)
        if reason:
            return reason

    if organisation is not None:
        reason = _org_contact_suppression_reason(organisation, email=em)
        if reason:
            return reason

    # Look up user/org by address when caller did not pass entities.
    if user is None:
        matched = db.execute(select(User).where(User.email == em).limit(1)).scalar_one_or_none()
        reason = _user_suppression_reason(matched)
        if reason:
            return reason

    if organisation is None:
        matched_org = db.execute(
            select(Organisation).where(Organisation.contact_email == em).limit(1)
        ).scalar_one_or_none()
        reason = _org_contact_suppression_reason(matched_org, email=em)
        if reason:
            return reason

    return None


def resolve_ticket_customer_recipient(db: Session, ticket: Any) -> tuple[str | None, str | None]:
    """Prefer an explicit valid requester_email; else a deliverable creator email.

    Returns ``(email, None)`` when deliverable, or ``(None, skip_reason)``.
    """
    org = db.get(Organisation, getattr(ticket, "organisation_id", None)) if getattr(ticket, "organisation_id", None) else None
    creator = db.get(User, getattr(ticket, "created_by_user_id", None)) if getattr(ticket, "created_by_user_id", None) else None

    explicit = normalize_recipient_email(getattr(ticket, "requester_email", None))
    if explicit:
        reason = recipient_suppression_reason(db, explicit, organisation=org)
        if reason is None:
            return explicit, None
        # Explicit was undeliverable — fall through to creator rather than sending it.

    creator_email = normalize_recipient_email(getattr(creator, "email", None) if creator else None)
    if creator_email:
        reason = recipient_suppression_reason(db, creator_email, user=creator, organisation=org)
        if reason is None:
            return creator_email, None
        return None, reason

    if explicit:
        return None, recipient_suppression_reason(db, explicit, organisation=org) or "placeholder_domain"

    return None, "missing_recipient"
