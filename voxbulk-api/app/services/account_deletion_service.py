"""Account deletion — request, cancel, admin complete; soft archive, retain billing/audit."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.account_deletion_request import AccountDeletionRequest
from app.models.membership import OrganisationMembership
from app.models.org_audit_event import OrganisationAuditEvent
from app.models.organisation import Organisation
from app.models.user import User
from app.services.org_audit_service import OrgAuditService

DELETION_STATUSES = frozenset({"active", "pending", "cancelled", "archived"})
DELETION_LABELS = {
    "active": "Not requested",
    "pending": "Pending deletion",
    "cancelled": "Cancelled",
    "archived": "Deleted",
}

AUDIT_REQUESTED = "account.deletion_requested"
AUDIT_CANCELLED = "account.deletion_cancelled"
AUDIT_APPROVED = "account.deletion_approved"
AUDIT_COMPLETED = "account.deletion_completed"
AUDIT_EMAIL_SENT = "account.deletion_email_sent"


class AccountDeletionError(ValueError):
    pass


class AccountDeletionService:
    @staticmethod
    def _status_label(status: str | None) -> str:
        return DELETION_LABELS.get(str(status or "active"), str(status or "active"))

    @staticmethod
    def can_request_deletion(db: Session, *, user_id: str, org_id: str) -> tuple[bool, str | None]:
        mem = db.execute(
            select(OrganisationMembership).where(
                OrganisationMembership.user_id == user_id,
                OrganisationMembership.org_id == org_id,
            )
        ).scalar_one_or_none()
        if mem is None:
            return False, "Tenant access denied"
        member_count = int(
            db.execute(
                select(func.count()).select_from(OrganisationMembership).where(OrganisationMembership.org_id == org_id)
            ).scalar_one()
            or 0
        )
        role = str(mem.role or "owner").strip().lower()
        if member_count == 1:
            return True, None
        if role == "owner":
            return True, None
        return False, "Only the organisation owner can request account deletion. Contact your owner or support."

    @staticmethod
    def _active_pending_request(db: Session, org_id: str) -> AccountDeletionRequest | None:
        return db.execute(
            select(AccountDeletionRequest)
            .where(
                AccountDeletionRequest.org_id == org_id,
                AccountDeletionRequest.status == "pending",
            )
            .order_by(AccountDeletionRequest.requested_at.desc())
            .limit(1)
        ).scalar_one_or_none()

    @staticmethod
    def get_status(db: Session, *, user: User, org_id: str) -> dict[str, Any]:
        org = db.get(Organisation, org_id)
        req = AccountDeletionService._active_pending_request(db, org_id)
        if req is None and str(getattr(user, "deletion_status", "active") or "active") == "pending":
            req = db.execute(
                select(AccountDeletionRequest)
                .where(AccountDeletionRequest.org_id == org_id, AccountDeletionRequest.requested_by_user_id == user.id)
                .order_by(AccountDeletionRequest.requested_at.desc())
                .limit(1)
            ).scalar_one_or_none()
        status = str(getattr(user, "deletion_status", "active") or "active")
        if org is not None and status == "active":
            org_status = str(getattr(org, "deletion_status", "active") or "active")
            if org_status != "active":
                status = org_status
        return {
            "deletion_status": status,
            "deletion_label": AccountDeletionService._status_label(status),
            "deletion_requested_at": getattr(user, "deletion_requested_at", None),
            "deletion_request_id": req.id if req else None,
            "can_cancel": status == "pending" and req is not None and req.status == "pending",
            "can_request": status in ("active", "cancelled"),
            "sla_message": "This may take up to 2 working days.",
            "pending_message": "You have requested account deletion.",
        }

    @staticmethod
    def request_user_deletion(db: Session, user: User, *, org_id: str, reason: str | None = None) -> dict[str, Any]:
        status = str(getattr(user, "deletion_status", "active") or "active")
        if status not in ("active", "cancelled"):
            raise AccountDeletionError("Account deletion is already in progress or completed")
        ok, err = AccountDeletionService.can_request_deletion(db, user_id=user.id, org_id=org_id)
        if not ok:
            raise AccountDeletionError(err or "Not allowed to request deletion")

        org = db.get(Organisation, org_id)
        if org is None:
            raise AccountDeletionError("Organisation not found")
        if str(getattr(org, "deletion_status", "active") or "active") not in ("active", "cancelled"):
            raise AccountDeletionError("Organisation deletion is already in progress or completed")

        existing = AccountDeletionService._active_pending_request(db, org_id)
        if existing is not None:
            raise AccountDeletionError("A deletion request is already pending for this organisation")

        now = datetime.utcnow()
        req = AccountDeletionRequest(
            org_id=org_id,
            requested_by_user_id=user.id,
            requested_by_email=str(user.email),
            status="pending",
            reason=(str(reason).strip()[:2000] if reason else None),
            requested_at=now,
        )
        db.add(req)

        user.deletion_status = "pending"
        user.deletion_requested_at = now
        user.is_active = False
        db.add(user)

        org.deletion_status = "pending"
        org.deletion_requested_at = now
        db.add(org)

        OrgAuditService.record_admin(
            db,
            org_id=org_id,
            event_type=AUDIT_REQUESTED,
            action="Account deletion requested by user",
            entity_type="user",
            entity_id=user.id,
            detail=reason,
            actor_user_id=user.id,
            actor_email=user.email,
            metadata={"request_id": req.id},
            commit=False,
        )
        db.commit()
        db.refresh(user)
        db.refresh(req)
        return {
            "ok": True,
            "deletion_status": user.deletion_status,
            "deletion_label": AccountDeletionService._status_label(user.deletion_status),
            "request_id": req.id,
            "message": "You have requested account deletion.",
            "sla_message": "This may take up to 2 working days.",
        }

    @staticmethod
    def cancel_user_deletion(db: Session, user: User, *, org_id: str) -> dict[str, Any]:
        if str(getattr(user, "deletion_status", "active") or "active") != "pending":
            raise AccountDeletionError("No pending deletion request to cancel")

        req = AccountDeletionService._active_pending_request(db, org_id)
        if req is None or req.requested_by_user_id != user.id:
            raise AccountDeletionError("No pending deletion request found for your account")

        now = datetime.utcnow()
        req.status = "cancelled"
        req.cancelled_at = now
        req.updated_at = now
        db.add(req)

        user.deletion_status = "cancelled"
        user.is_active = True
        db.add(user)

        org = db.get(Organisation, org_id)
        if org is not None and str(getattr(org, "deletion_status", "active") or "active") == "pending":
            org.deletion_status = "cancelled"
            db.add(org)

        OrgAuditService.record_admin(
            db,
            org_id=org_id,
            event_type=AUDIT_CANCELLED,
            action="Account deletion request cancelled by user",
            entity_type="user",
            entity_id=user.id,
            actor_user_id=user.id,
            actor_email=user.email,
            metadata={"request_id": req.id},
            commit=False,
        )
        db.commit()
        db.refresh(user)
        return {
            "ok": True,
            "deletion_status": "cancelled",
            "deletion_label": AccountDeletionService._status_label("cancelled"),
        }

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
    def _send_completion_email(
        db: Session,
        *,
        org_id: str,
        to_email: str,
        organisation_name: str,
        deleted_at: datetime,
        actor_user_id: str | None,
        actor_email: str | None,
    ) -> tuple[bool, str | None]:
        from app.services.product_email_triggers import ProductEmailTriggers

        ok, err = ProductEmailTriggers.send_account_deletion_completed(
            db,
            to_email=to_email,
            organisation_name=organisation_name,
            deleted_at=deleted_at,
        )
        OrgAuditService.record_admin(
            db,
            org_id=org_id,
            event_type=AUDIT_EMAIL_SENT,
            action="Account deletion confirmation email sent" if ok else "Account deletion confirmation email skipped",
            detail=err,
            actor_user_id=actor_user_id,
            actor_email=actor_email,
            metadata={"to_email": to_email, "ok": ok},
            commit=False,
        )
        return ok, err

    @staticmethod
    def approve_and_complete(
        db: Session,
        org_id: str,
        *,
        actor_user_id: str | None = None,
        actor_email: str | None = None,
        reason: str | None = None,
        admin_notes: str | None = None,
        request_id: str | None = None,
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

        req: AccountDeletionRequest | None = None
        if request_id:
            req = db.get(AccountDeletionRequest, request_id)
            if req is None or req.org_id != org_id:
                raise AccountDeletionError("Deletion request not found")
        else:
            req = AccountDeletionService._active_pending_request(db, org_id)

        memberships = list(
            db.execute(select(OrganisationMembership).where(OrganisationMembership.org_id == org_id)).scalars().all()
        )

        notify_email: str | None = None
        notify_name = org.name or ""
        if req is not None:
            notify_email = str(req.requested_by_email or "").strip() or None
        if not notify_email:
            for m in memberships:
                u = db.get(User, m.user_id)
                if u and "@" in str(u.email):
                    notify_email = str(u.email)
                    break

        OrgAuditService.record_admin(
            db,
            org_id=org_id,
            event_type=AUDIT_APPROVED,
            action="Account deletion approved by admin",
            entity_type="organisation",
            entity_id=org_id,
            detail=reason or admin_notes,
            actor_user_id=actor_user_id,
            actor_email=actor_email,
            metadata={"request_id": req.id if req else None},
            commit=False,
        )

        deleted_at = datetime.utcnow()
        if notify_email:
            AccountDeletionService._send_completion_email(
                db,
                org_id=org_id,
                to_email=notify_email,
                organisation_name=notify_name,
                deleted_at=deleted_at,
                actor_user_id=actor_user_id,
                actor_email=actor_email,
            )

        AccountDeletionService._anonymize_org(db, org)
        for m in memberships:
            user = db.get(User, m.user_id)
            if user is not None:
                AccountDeletionService._anonymize_user(db, user)

        if req is not None:
            req.status = "completed"
            req.completed_at = deleted_at
            req.completed_by_admin_user_id = actor_user_id
            req.completed_by_admin_email = actor_email
            if admin_notes:
                req.admin_notes = str(admin_notes).strip()[:2000]
            req.updated_at = deleted_at
            db.add(req)

        OrgAuditService.record_admin(
            db,
            org_id=org_id,
            event_type=AUDIT_COMPLETED,
            action="Organisation archived — PII anonymized; invoices and audit retained",
            entity_type="organisation",
            entity_id=org_id,
            detail=reason,
            metadata={
                "retained": ["billing_invoices", "organisation_audit_events", "wallet_transactions"],
                "request_id": req.id if req else None,
            },
            actor_user_id=actor_user_id,
            actor_email=actor_email,
            commit=False,
        )
        db.commit()
        db.refresh(org)
        return {
            "ok": True,
            "deletion_status": org.deletion_status,
            "request_id": req.id if req else None,
            "retention_policy": {
                "invoices": "retained",
                "audit_events": "retained",
                "pii": "anonymized",
            },
        }

    @staticmethod
    def execute_org_deletion(
        db: Session,
        org_id: str,
        *,
        actor_user_id: str | None = None,
        actor_email: str | None = None,
        reason: str | None = None,
        admin_notes: str | None = None,
    ) -> dict[str, Any]:
        return AccountDeletionService.approve_and_complete(
            db,
            org_id,
            actor_user_id=actor_user_id,
            actor_email=actor_email,
            reason=reason,
            admin_notes=admin_notes,
        )

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
        return AccountDeletionService.approve_and_complete(
            db,
            org_id,
            actor_user_id=actor_user_id or user_id,
            actor_email=actor_email or user.email,
            reason=reason or "User requested account deletion",
        )

    @staticmethod
    def _request_to_dict(db: Session, req: AccountDeletionRequest) -> dict[str, Any]:
        org = db.get(Organisation, req.org_id)
        return {
            "id": req.id,
            "org_id": req.org_id,
            "org_name": org.name if org else None,
            "requested_by_user_id": req.requested_by_user_id,
            "requested_by_email": req.requested_by_email,
            "status": req.status,
            "reason": req.reason,
            "admin_notes": req.admin_notes,
            "requested_at": req.requested_at,
            "cancelled_at": req.cancelled_at,
            "completed_at": req.completed_at,
            "completed_by_admin_user_id": req.completed_by_admin_user_id,
            "completed_by_admin_email": req.completed_by_admin_email,
            "support_ticket_id": req.support_ticket_id,
            "org_deletion_status": getattr(org, "deletion_status", None) if org else None,
        }

    @staticmethod
    def list_admin_queue(
        db: Session,
        *,
        status_filter: str | None = "pending",
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        stmt = select(AccountDeletionRequest).order_by(AccountDeletionRequest.requested_at.desc()).limit(
            max(1, min(int(limit or 100), 500))
        )
        sf = str(status_filter or "all").strip().lower()
        if sf and sf != "all":
            stmt = stmt.where(AccountDeletionRequest.status == sf)
        rows = list(db.execute(stmt).scalars().all())
        return [AccountDeletionService._request_to_dict(db, r) for r in rows]

    @staticmethod
    def get_admin_request(db: Session, request_id: str) -> dict[str, Any] | None:
        req = db.get(AccountDeletionRequest, request_id)
        if req is None:
            return None
        data = AccountDeletionService._request_to_dict(db, req)
        data["activity"] = AccountDeletionService.list_deletion_activity(db, req.org_id, limit=50)
        return data

    @staticmethod
    def list_deletion_activity(db: Session, org_id: str, *, limit: int = 100) -> list[dict[str, Any]]:
        prefix = "account.deletion"
        rows = list(
            db.execute(
                select(OrganisationAuditEvent)
                .where(
                    OrganisationAuditEvent.org_id == org_id,
                    OrganisationAuditEvent.event_type.like(f"{prefix}%"),
                )
                .order_by(OrganisationAuditEvent.created_at.desc())
                .limit(max(1, min(int(limit or 100), 500)))
            )
            .scalars()
            .all()
        )
        from app.services.org_audit_service import _event_dict

        return [_event_dict(r) for r in rows]

    @staticmethod
    def pending_count(db: Session) -> int:
        return int(
            db.execute(
                select(func.count()).select_from(AccountDeletionRequest).where(AccountDeletionRequest.status == "pending")
            ).scalar_one()
            or 0
        )
