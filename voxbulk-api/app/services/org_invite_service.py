"""Team invite helpers: pending invites, personal org for new users, auto-attach."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.membership import OrganisationMembership
from app.models.organisation import Organisation
from app.models.organisation_invite import OrganisationInvite
from app.models.user import User
from app.services.org_rbac import OrgRbacService, effective_role


def personal_org_name_from_email(email: str) -> str:
    local = (email.split("@")[0] if "@" in email else email).strip()
    if local:
        return f"{local.title()}'s organisation"
    return "My organisation"


def ensure_personal_org(db: Session, *, user: User, email: str) -> str:
    """Create a personal owner org if the user has no owner membership yet."""
    rows = list(
        db.execute(
            select(OrganisationMembership.org_id, OrganisationMembership.role).where(
                OrganisationMembership.user_id == user.id
            )
        ).all()
    )
    for org_id, role in rows:
        if effective_role(role) == "owner":
            return str(org_id)

    org = Organisation(name=personal_org_name_from_email(email))
    db.add(org)
    db.flush()
    db.add(OrganisationMembership(org_id=org.id, user_id=user.id, role="owner"))
    db.flush()
    return str(org.id)


def list_pending_invites_for_email(db: Session, *, email: str) -> list[OrganisationInvite]:
    email_norm = str(email or "").strip().lower()
    if not email_norm:
        return []
    now = datetime.utcnow()
    return list(
        db.execute(
            select(OrganisationInvite)
            .where(
                OrganisationInvite.email == email_norm,
                OrganisationInvite.consumed_at.is_(None),
                OrganisationInvite.expires_at >= now,
            )
            .order_by(OrganisationInvite.created_at.asc())
        ).scalars()
    )


def pending_invite_payloads(db: Session, *, email: str) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for inv in list_pending_invites_for_email(db, email=email):
        org = db.execute(select(Organisation).where(Organisation.id == inv.org_id)).scalar_one_or_none()
        out.append(
            {
                "token": inv.token,
                "org_id": str(inv.org_id),
                "organisation_name": str(org.name if org else "Organisation"),
                "role": str(inv.role or "member"),
                "expires_at": inv.expires_at.isoformat() if inv.expires_at else None,
            }
        )
    return out


def link_smart_card_reps_for_invite(
    db: Session,
    *,
    org_id: str,
    user: User,
    email: str | None = None,
    invite_id: str | None = None,
) -> int:
    """Attach unlinked Smart Card QRs to this user (by email and/or invite_id)."""
    from sqlalchemy import or_

    from app.models.smart_card import SmartCardRepresentative

    em = str(email or user.email or "").strip().lower()
    inv_id = str(invite_id or "").strip() or None
    if not em and not inv_id:
        return 0
    matchers = []
    if em:
        matchers.append(SmartCardRepresentative.email == em)
    if inv_id:
        matchers.append(SmartCardRepresentative.invite_id == inv_id)
    reps = (
        db.execute(
            select(SmartCardRepresentative).where(
                SmartCardRepresentative.org_id == org_id,
                SmartCardRepresentative.linked_user_id.is_(None),
                or_(*matchers),
            )
        )
        .scalars()
        .all()
    )
    linked = 0
    for rep in reps:
        rep.linked_user_id = user.id
        if em and not (rep.email or "").strip():
            rep.email = em
        db.add(rep)
        linked += 1
    return linked


def _mark_member_setup_complete(db: Session, *, user_id: str, org_id: str, role: str | None) -> None:
    """Members never run company onboarding — mark setup done so they are not trapped."""
    if effective_role(role) != "member":
        return
    mobj = db.execute(
        select(OrganisationMembership).where(
            OrganisationMembership.user_id == user_id,
            OrganisationMembership.org_id == org_id,
        )
    ).scalar_one_or_none()
    if mobj is None:
        return
    if mobj.dashboard_setup_completed_at is None:
        mobj.dashboard_setup_completed_at = datetime.utcnow()
        db.add(mobj)


def consume_invite_for_user(db: Session, *, inv: OrganisationInvite, user: User) -> None:
    mem = db.execute(
        select(OrganisationMembership.id).where(
            OrganisationMembership.user_id == user.id,
            OrganisationMembership.org_id == inv.org_id,
        )
    ).scalar_one_or_none()
    if mem is None:
        db.add(OrganisationMembership(org_id=inv.org_id, user_id=user.id, role=inv.role))
        db.flush()
    elif inv.role:
        mobj = db.execute(
            select(OrganisationMembership).where(
                OrganisationMembership.user_id == user.id,
                OrganisationMembership.org_id == inv.org_id,
            )
        ).scalar_one_or_none()
        if mobj is not None and (mobj.role is None or str(mobj.role).strip() == ""):
            mobj.role = inv.role
            db.add(mobj)
    _mark_member_setup_complete(db, user_id=user.id, org_id=str(inv.org_id), role=getattr(inv, "role", None))
    inv.consumed_at = datetime.utcnow()
    db.add(inv)
    try:
        link_smart_card_reps_for_invite(
            db,
            org_id=str(inv.org_id),
            user=user,
            email=str(inv.email or user.email or ""),
            invite_id=str(getattr(inv, "id", "") or ""),
        )
    except Exception:
        pass


def attach_pending_invites(db: Session, *, user: User) -> list[str]:
    """Attach all pending invites for the user's email. Returns newly joined org ids."""
    joined: list[str] = []
    for inv in list_pending_invites_for_email(db, email=str(user.email or "")):
        existing = db.execute(
            select(OrganisationMembership.id).where(
                OrganisationMembership.user_id == user.id,
                OrganisationMembership.org_id == inv.org_id,
            )
        ).scalar_one_or_none()
        if existing is not None:
            inv.consumed_at = datetime.utcnow()
            db.add(inv)
            try:
                link_smart_card_reps_for_invite(
                    db,
                    org_id=str(inv.org_id),
                    user=user,
                    email=str(inv.email or user.email or ""),
                    invite_id=str(getattr(inv, "id", "") or ""),
                )
            except Exception:
                pass
            continue
        consume_invite_for_user(db, inv=inv, user=user)
        joined.append(str(inv.org_id))
    return joined


def setup_new_invited_user(db: Session, *, user: User, email: str, inv: OrganisationInvite) -> None:
    """New invite signup: join inviting org. Personal owner org only for non-member roles."""
    role = effective_role(getattr(inv, "role", None))
    # Members (Smart Card invitees) should land in the company workspace only —
    # a second personal org makes Saved QRs look empty when they pick the wrong company.
    if role != "member":
        ensure_personal_org(db, user=user, email=email)
    consume_invite_for_user(db, inv=inv, user=user)


def organisations_for_user(db: Session, *, user_id: str) -> list[dict[str, object]]:
    return OrgRbacService.list_organisations_for_user(db, user_id=user_id)
