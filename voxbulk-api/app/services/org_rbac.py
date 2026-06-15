"""Organisation-scoped role checks for dashboard users."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.membership import OrganisationMembership
from app.models.organisation import Organisation

ORG_TEAM_ROLES = frozenset({"owner", "manager", "accountant", "member", "receptionist"})
ORG_TEAM_MANAGERS = frozenset({"owner", "manager"})
ORG_BILLING_ROLES = frozenset({"owner", "manager", "accountant"})
ORG_CAMPAIGN_ROLES = frozenset({"owner", "manager", "member", "receptionist"})
ORG_DIGEST_ROLES = frozenset({"owner", "manager", "accountant"})


def _normalize_role(role: str | None) -> str:
    r = str(role or "member").strip().lower()
    if r not in ORG_TEAM_ROLES:
        return "member"
    return r


class OrgRbacService:
    @staticmethod
    def membership_for(db: Session, *, org_id: str, user_id: str) -> OrganisationMembership | None:
        return db.execute(
            select(OrganisationMembership).where(
                OrganisationMembership.org_id == org_id,
                OrganisationMembership.user_id == user_id,
            )
        ).scalar_one_or_none()

    @staticmethod
    def role_for(db: Session, *, org_id: str, user_id: str) -> str:
        mem = OrgRbacService.membership_for(db, org_id=org_id, user_id=user_id)
        if mem is None:
            raise PermissionError("Tenant access denied")
        return _normalize_role(mem.role)

    @staticmethod
    def assert_can_manage_team(db: Session, *, org_id: str, user_id: str) -> OrganisationMembership:
        mem = OrgRbacService.membership_for(db, org_id=org_id, user_id=user_id)
        if mem is None:
            raise PermissionError("Tenant access denied")
        role = _normalize_role(mem.role)
        if role not in ORG_TEAM_MANAGERS:
            raise PermissionError("Only owners and managers can manage team members")
        return mem

    @staticmethod
    def assert_can_access_billing(db: Session, *, org_id: str, user_id: str) -> OrganisationMembership:
        mem = OrgRbacService.membership_for(db, org_id=org_id, user_id=user_id)
        if mem is None:
            raise PermissionError("Tenant access denied")
        role = _normalize_role(mem.role)
        if role not in ORG_BILLING_ROLES:
            raise PermissionError("Billing access denied for your role")
        return mem

    @staticmethod
    def assert_can_mutate_billing(db: Session, *, org_id: str, user_id: str) -> OrganisationMembership:
        return OrgRbacService.assert_can_access_billing(db, org_id=org_id, user_id=user_id)

    @staticmethod
    def assert_can_launch_campaigns(db: Session, *, org_id: str, user_id: str) -> OrganisationMembership:
        mem = OrgRbacService.membership_for(db, org_id=org_id, user_id=user_id)
        if mem is None:
            raise PermissionError("Tenant access denied")
        role = _normalize_role(mem.role)
        if role not in ORG_CAMPAIGN_ROLES:
            raise PermissionError("Campaign access denied for your role")
        return mem

    @staticmethod
    def list_organisations_for_user(db: Session, *, user_id: str) -> list[dict[str, object]]:
        rows = list(
            db.execute(
                select(
                    Organisation.id,
                    Organisation.name,
                    OrganisationMembership.role,
                    OrganisationMembership.created_at,
                )
                .join(OrganisationMembership, OrganisationMembership.org_id == Organisation.id)
                .where(OrganisationMembership.user_id == user_id)
                .order_by(Organisation.name.asc(), OrganisationMembership.created_at.asc())
            ).all()
        )
        out: list[dict[str, object]] = []
        for org_id, name, role, _created in rows:
            role_norm = _normalize_role(role)
            out.append(
                {
                    "org_id": str(org_id),
                    "name": str(name or "Organisation"),
                    "role": role_norm,
                    "is_owner": role_norm == "owner",
                }
            )
        return out

    @staticmethod
    def count_owners(db: Session, *, org_id: str) -> int:
        return int(
            db.execute(
                select(func.count())
                .select_from(OrganisationMembership)
                .where(
                    OrganisationMembership.org_id == org_id,
                    OrganisationMembership.role == "owner",
                )
            ).scalar_one()
            or 0
        )

    @staticmethod
    def assert_can_remove_member(db: Session, *, org_id: str, target_user_id: str) -> OrganisationMembership:
        mem = db.execute(
            select(OrganisationMembership).where(
                OrganisationMembership.org_id == org_id,
                OrganisationMembership.user_id == target_user_id,
            )
        ).scalar_one_or_none()
        if mem is None:
            raise ValueError("Member not found")
        if _normalize_role(mem.role) == "owner":
            owners = OrgRbacService.count_owners(db, org_id=org_id)
            if owners <= 1:
                raise ValueError("Cannot remove the only owner — transfer ownership first")
        return mem
