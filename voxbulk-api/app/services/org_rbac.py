"""Organisation-scoped role checks for dashboard users."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.membership import OrganisationMembership
from app.models.organisation import Organisation
from app.models.user import User

ORG_TEAM_ROLES = frozenset({"owner", "manager", "accountant", "member"})
ORG_TEAM_MANAGERS = frozenset({"owner", "manager"})
ORG_BILLING_ROLES = frozenset({"owner", "manager", "accountant"})
ORG_CAMPAIGN_ROLES = frozenset({"owner", "manager", "member"})
ORG_DIGEST_ROLES = frozenset({"owner", "manager", "accountant"})


def effective_role(role: str | None) -> str:
    """Map stored membership role to a canonical RBAC role.

    Empty/NULL roles are treated as the lowest privilege (member) — never elevate.
    Legacy labels: receptionist → member, sales → owner.
    """
    r = str(role or "").strip().lower()
    if not r:
        return "member"
    if r == "receptionist":
        return "member"
    if r == "sales":
        return "owner"
    if r not in ORG_TEAM_ROLES:
        return "member"
    return r


def can_view_all_campaigns(role: str | None) -> bool:
    """Owners and managers see every org campaign; members see only their own."""
    return effective_role(role) in ORG_TEAM_MANAGERS


def campaign_owner_filter(role: str | None, user_id: str) -> str | None:
    """Return user_id to filter campaign lists/detail for members; None = no filter (owner/manager)."""
    if can_view_all_campaigns(role):
        return None
    uid = str(user_id or "").strip()
    return uid or None


def _normalize_role(role: str | None) -> str:
    return effective_role(role)


class OrgRbacService:
    @staticmethod
    def campaign_owner_filter_for(db: Session, *, org_id: str, user_id: str) -> str | None:
        role = OrgRbacService.role_for(db, org_id=org_id, user_id=user_id)
        return campaign_owner_filter(role, user_id)

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
    def assert_can_edit_org_profile(db: Session, *, org_id: str, user_id: str) -> OrganisationMembership:
        mem = OrgRbacService.membership_for(db, org_id=org_id, user_id=user_id)
        if mem is None:
            raise PermissionError("Tenant access denied")
        role = _normalize_role(mem.role)
        if role not in ORG_TEAM_MANAGERS:
            raise PermissionError("Only owners and managers can edit organisation profile")
        return mem

    @staticmethod
    def assert_can_export_org_data(db: Session, *, org_id: str, user_id: str) -> OrganisationMembership:
        mem = OrgRbacService.membership_for(db, org_id=org_id, user_id=user_id)
        if mem is None:
            raise PermissionError("Tenant access denied")
        role = _normalize_role(mem.role)
        if role not in ORG_TEAM_MANAGERS:
            raise PermissionError("Only owners and managers can export organisation data")
        return mem

    @staticmethod
    def preferred_org_id_for_user(db: Session, *, user_id: str) -> str | None:
        raw = db.execute(select(User.preferred_org_id).where(User.id == user_id)).scalar_one_or_none()
        pref = str(raw or "").strip()
        return pref or None

    @staticmethod
    def list_organisations_for_user(db: Session, *, user_id: str) -> list[dict[str, object]]:
        preferred = OrgRbacService.preferred_org_id_for_user(db, user_id=user_id)
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
            oid = str(org_id)
            out.append(
                {
                    "org_id": oid,
                    "name": str(name or "Organisation"),
                    "role": role_norm,
                    "is_owner": role_norm == "owner",
                    "is_main": bool(preferred and oid == preferred),
                }
            )
        # Surface the main company first so login pickers highlight it.
        out.sort(key=lambda row: (0 if row.get("is_main") else 1, str(row.get("name") or "").lower()))
        return out

    @staticmethod
    def resolve_login_org_id(
        db: Session,
        *,
        user_id: str,
        joined_org_ids: list[str] | None = None,
    ) -> str | None:
        """
        Pick an org automatically for login, or None if the client must show a picker.

        Priority: newly joined (this login) → preferred/main → single membership.
        """
        org_ids = [
            str(oid)
            for oid in db.execute(
                select(OrganisationMembership.org_id).where(OrganisationMembership.user_id == user_id)
            ).scalars()
        ]
        if not org_ids:
            return None
        if len(org_ids) == 1:
            return org_ids[0]

        joined = [str(j) for j in (joined_org_ids or []) if str(j) in org_ids]
        if joined:
            return joined[-1]

        preferred = OrgRbacService.preferred_org_id_for_user(db, user_id=user_id)
        if preferred and preferred in org_ids:
            return preferred
        return None

    @staticmethod
    def count_owners(db: Session, *, org_id: str) -> int:
        roles = list(
            db.execute(
                select(OrganisationMembership.role).where(OrganisationMembership.org_id == org_id)
            ).scalars()
        )
        return sum(1 for role in roles if effective_role(role) == "owner")

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
