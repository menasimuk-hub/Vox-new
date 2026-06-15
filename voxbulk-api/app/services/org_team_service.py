from __future__ import annotations

import secrets
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.membership import OrganisationMembership
from app.models.organisation import Organisation
from app.models.organisation_invite import OrganisationInvite
from app.models.user import User
from app.services.product_email_triggers import ProductEmailTriggers

ORG_TEAM_ROLES = frozenset({"owner", "manager", "accountant", "member", "receptionist"})
ORG_TEAM_MANAGERS = frozenset({"owner", "manager"})


def _can_manage_team(role: str | None) -> bool:
    r = str(role or "owner").strip().lower()
    return r in ORG_TEAM_MANAGERS or not role


def _normalize_role(role: str | None) -> str:
    r = str(role or "member").strip().lower()
    if r not in ORG_TEAM_ROLES:
        raise ValueError(f"role must be one of: {', '.join(sorted(ORG_TEAM_ROLES))}")
    return r


class OrgTeamService:
    @staticmethod
    def assert_can_manage(db: Session, *, org_id: str, user_id: str) -> OrganisationMembership:
        mem = db.execute(
            select(OrganisationMembership).where(
                OrganisationMembership.org_id == org_id,
                OrganisationMembership.user_id == user_id,
            )
        ).scalar_one_or_none()
        if mem is None:
            raise PermissionError("Tenant access denied")
        if not _can_manage_team(mem.role):
            raise PermissionError("Only owners and managers can manage team members")
        return mem

    @staticmethod
    def list_members(db: Session, org_id: str) -> list[dict[str, Any]]:
        rows = list(
            db.execute(
                select(
                    User.id,
                    User.email,
                    User.is_active,
                    OrganisationMembership.role,
                    OrganisationMembership.created_at,
                )
                .join(OrganisationMembership, OrganisationMembership.user_id == User.id)
                .where(OrganisationMembership.org_id == org_id)
                .order_by(OrganisationMembership.created_at.asc())
                .limit(200)
            ).all()
        )
        return [
            {
                "user_id": uid,
                "email": email,
                "is_active": is_active,
                "role": role or "owner",
                "linked_at": created_at,
            }
            for uid, email, is_active, role, created_at in rows
        ]

    @staticmethod
    def list_invites(db: Session, org_id: str) -> list[dict[str, Any]]:
        now = datetime.utcnow()
        rows = list(
            db.execute(
                select(OrganisationInvite)
                .where(
                    OrganisationInvite.org_id == org_id,
                    OrganisationInvite.consumed_at.is_(None),
                )
                .order_by(OrganisationInvite.created_at.desc())
                .limit(200)
            )
            .scalars()
            .all()
        )
        settings = get_settings()
        base = settings.public_app_origin.rstrip("/")
        return [
            {
                "id": i.id,
                "email": i.email,
                "role": i.role or "member",
                "created_at": i.created_at,
                "expires_at": i.expires_at,
                "is_expired": bool(i.expires_at and i.expires_at < now),
                "signup_url": f"{base}/signin?invite_token={i.token}",
            }
            for i in rows
        ]

    @staticmethod
    def create_invite(
        db: Session,
        *,
        org_id: str,
        email: str,
        role: str | None,
        invited_by: User,
        send_email: bool = True,
    ) -> dict[str, Any]:
        OrgTeamService.assert_can_manage(db, org_id=org_id, user_id=invited_by.id)
        org = db.get(Organisation, org_id)
        if org is None:
            raise ValueError("Organisation not found")
        if bool(org.is_suspended):
            raise ValueError("Organisation suspended")

        em = str(email or "").strip().lower()
        if not em or "@" not in em:
            raise ValueError("Valid email required")
        role_norm = _normalize_role(role)

        pending_user = db.execute(select(User.id).where(User.email == em)).scalar_one_or_none()
        if pending_user is not None:
            clash = db.execute(
                select(OrganisationMembership.id).where(
                    OrganisationMembership.org_id == org_id,
                    OrganisationMembership.user_id == pending_user,
                )
            ).scalar_one_or_none()
            if clash is not None:
                raise ValueError("User already belongs to this organisation")

        db.execute(
            delete(OrganisationInvite).where(
                OrganisationInvite.org_id == org_id,
                OrganisationInvite.email == em,
                OrganisationInvite.consumed_at.is_(None),
            )
        )
        token = secrets.token_urlsafe(32)
        exp = datetime.utcnow() + timedelta(days=21)
        inv = OrganisationInvite(
            org_id=org_id,
            email=em,
            role=role_norm,
            token=token,
            expires_at=exp,
            consumed_at=None,
        )
        db.add(inv)
        db.commit()
        db.refresh(inv)

        settings = get_settings()
        base = settings.public_app_origin.rstrip("/")
        signup_url = f"{base}/signin?invite_token={token}"

        email_sent = False
        if send_email:
            try:
                email_sent, _ = ProductEmailTriggers.send_team_invite(
                    db,
                    to_email=em,
                    organisation_name=org.name or "your organisation",
                    invite_role=role_norm,
                    signup_url=signup_url,
                )
            except Exception:
                email_sent = False

        return {
            "invite_id": inv.id,
            "email": em,
            "role": role_norm,
            "expires_at": inv.expires_at,
            "signup_url": signup_url,
            "email_sent": email_sent,
        }

    @staticmethod
    def revoke_invite(db: Session, *, org_id: str, invite_id: str, actor_user_id: str) -> bool:
        OrgTeamService.assert_can_manage(db, org_id=org_id, user_id=actor_user_id)
        inv = db.execute(
            select(OrganisationInvite).where(
                OrganisationInvite.id == invite_id,
                OrganisationInvite.org_id == org_id,
                OrganisationInvite.consumed_at.is_(None),
            )
        ).scalar_one_or_none()
        if inv is None:
            return False
        db.delete(inv)
        db.commit()
        return True

    @staticmethod
    def remove_member(db: Session, *, org_id: str, user_id: str, actor_user_id: str) -> bool:
        OrgTeamService.assert_can_manage(db, org_id=org_id, user_id=actor_user_id)
        if str(user_id) == str(actor_user_id):
            raise ValueError("You cannot remove yourself from the team")
        mem = db.execute(
            select(OrganisationMembership).where(
                OrganisationMembership.org_id == org_id,
                OrganisationMembership.user_id == user_id,
            )
        ).scalar_one_or_none()
        if mem is None:
            return False
        from app.services.org_rbac import OrgRbacService

        OrgRbacService.assert_can_remove_member(db, org_id=org_id, target_user_id=user_id)
        user = db.get(User, user_id)
        if user and user.is_superuser:
            raise ValueError("Cannot remove platform superuser")
        db.delete(mem)
        db.commit()
        return True
