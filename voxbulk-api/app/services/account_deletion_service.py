"""Account deletion — soft archive, anonymize PII, retain invoices and audit records."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.membership import OrganisationMembership
from app.models.organisation import Organisation
from app.models.user import User
from app.services.org_audit_service import OrgAuditService


class AccountDeletionError(ValueError):
    pass


class AccountDeletionService:
    @staticmethod
    def request_user_deletion(db: Session, user: User, *, reason: str | None = None) -> dict[str, Any]:
        if str(getattr(user, "deletion_status", "active") or "active") != "active":
            raise AccountDeletionError("Account deletion is already in progress or completed")
        user.deletion_status = "pending"
        user.deletion_requested_at = datetime.utcnow()
        user.is_active = False
        db.add(user)
        memberships = list(
            db.execute(select(OrganisationMembership).where(OrganisationMembership.user_id == user.id)).scalars().all()
        )
        for m in memberships:
            org = db.get(Organisation, m.org_id)
            if org is not None and str(getattr(org, "deletion_status", "active") or "active") == "active":
                org.deletion_status = "pending"
                org.deletion_requested_at = datetime.utcnow()
                db.add(org)
                OrgAuditService.record_admin(
                    db,
                    org_id=org.id,
                    event_type="account.deletion_requested",
                    action="Account deletion requested by user",
                    entity_type="user",
                    entity_id=user.id,
                    detail=reason,
                    actor_user_id=user.id,
                    actor_email=user.email,
                )
        db.commit()
        db.refresh(user)
        return {"ok": True, "deletion_status": user.deletion_status}

    @staticmethod
    def _anonymize_user(db: Session, user: User) -> None:
        token = uuid.uuid4().hex[:10]
        user.email = f"deleted-{token}@anonymized.voxbulk.invalid"
        user.password_hash = "!"
        user.phone_number = None
        user.phone_e164 = None
        user.is_active = False
        user.deletion_status = "archived"
        user.deleted_at = datetime.utcnow()
        user.anonymized_at = datetime.utcnow()
        db.add(user)

    @staticmethod
    def _anonymize_org(db: Session, org: Organisation) -> None:
        token = uuid.uuid4().hex[:8]
        org.name = f"Archived organisation {token}"
        org.contact_name = None
        org.contact_email = f"archived-{token}@anonymized.voxbulk.invalid"
        org.contact_phone = None
        org.website = None
        org.address_line1 = None
        org.address_line2 = None
        org.city = None
        org.county_state = None
        org.postcode = None
        org.profile_notes = None
        org.is_suspended = True
        org.deletion_status = "archived"
        org.deleted_at = datetime.utcnow()
        org.anonymized_at = datetime.utcnow()
        db.add(org)

    @staticmethod
    def execute_org_deletion(
        db: Session,
        org_id: str,
        *,
        actor_user_id: str | None = None,
        actor_email: str | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        org = db.get(Organisation, org_id)
        if org is None:
            raise AccountDeletionError("Organisation not found")
        if str(getattr(org, "deletion_status", "active") or "active") == "archived":
            raise AccountDeletionError("Organisation is already archived")

        from app.models.service_order import ServiceOrder

        running = db.execute(
            select(ServiceOrder.id).where(
                ServiceOrder.org_id == org_id,
                ServiceOrder.status.in_(("running", "paused", "scheduled")),
            )
        ).first()
        if running:
            raise AccountDeletionError("Stop all running campaigns before deleting this account")

        memberships = list(
            db.execute(select(OrganisationMembership).where(OrganisationMembership.org_id == org_id)).scalars().all()
        )
        AccountDeletionService._anonymize_org(db, org)
        for m in memberships:
            user = db.get(User, m.user_id)
            if user is not None:
                AccountDeletionService._anonymize_user(db, user)
        OrgAuditService.record_admin(
            db,
            org_id=org_id,
            event_type="account.deleted",
            action="Organisation archived — PII anonymized; invoices and audit retained",
            entity_type="organisation",
            entity_id=org_id,
            detail=reason,
            metadata={"retained": ["billing_invoices", "organisation_audit_events", "wallet_transactions"]},
            actor_user_id=actor_user_id,
            actor_email=actor_email,
        )
        db.commit()
        db.refresh(org)
        return {
            "ok": True,
            "deletion_status": org.deletion_status,
            "retention_policy": {
                "invoices": "retained",
                "audit_events": "retained",
                "pii": "anonymized",
            },
        }

    @staticmethod
    def execute_user_deletion(
        db: Session,
        user_id: str,
        org_id: str,
        *,
        actor_user_id: str | None = None,
        actor_email: str | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        user = db.get(User, user_id)
        if user is None:
            raise AccountDeletionError("User not found")
        return AccountDeletionService.execute_org_deletion(
            db,
            org_id,
            actor_user_id=actor_user_id or user_id,
            actor_email=actor_email or user.email,
            reason=reason or "User requested account deletion",
        )
