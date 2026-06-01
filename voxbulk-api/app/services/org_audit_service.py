from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.org_audit_event import OrganisationAuditEvent
from app.models.user import User


class OrgAuditService:
    @staticmethod
    def record(
        db: Session,
        *,
        org_id: str,
        action: str,
        detail: str | None = None,
        actor_user_id: str | None = None,
        actor_email: str | None = None,
        commit: bool = True,
    ) -> OrganisationAuditEvent:
        row = OrganisationAuditEvent(
            org_id=org_id,
            actor_user_id=actor_user_id,
            actor_email=actor_email,
            action=str(action).strip()[:120],
            detail=(str(detail).strip()[:4000] if detail else None),
            created_at=datetime.utcnow(),
        )
        db.add(row)
        if commit:
            db.commit()
            db.refresh(row)
        return row

    @staticmethod
    def record_for_user(
        db: Session,
        *,
        org_id: str,
        user: User | None,
        action: str,
        detail: str | None = None,
        commit: bool = True,
    ) -> OrganisationAuditEvent:
        return OrgAuditService.record(
            db,
            org_id=org_id,
            action=action,
            detail=detail,
            actor_user_id=getattr(user, "id", None),
            actor_email=getattr(user, "email", None),
            commit=commit,
        )

    @staticmethod
    def list_events_for_user(
        db: Session,
        org_id: str,
        user_id: str,
        *,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        rows = list(
            db.execute(
                select(OrganisationAuditEvent)
                .where(
                    OrganisationAuditEvent.org_id == org_id,
                    OrganisationAuditEvent.actor_user_id == user_id,
                )
                .order_by(OrganisationAuditEvent.created_at.desc())
                .limit(max(1, min(limit, 500)))
            )
            .scalars()
            .all()
        )
        return [
            {
                "id": r.id,
                "action": r.action,
                "detail": r.detail,
                "actor_email": r.actor_email,
                "actor_user_id": r.actor_user_id,
                "created_at": r.created_at,
            }
            for r in rows
        ]

    @staticmethod
    def list_events(db: Session, org_id: str, *, limit: int = 100) -> list[dict[str, Any]]:
        rows = list(
            db.execute(
                select(OrganisationAuditEvent)
                .where(OrganisationAuditEvent.org_id == org_id)
                .order_by(OrganisationAuditEvent.created_at.desc())
                .limit(max(1, min(limit, 500)))
            )
            .scalars()
            .all()
        )
        return [
            {
                "id": r.id,
                "action": r.action,
                "detail": r.detail,
                "actor_email": r.actor_email,
                "actor_user_id": r.actor_user_id,
                "created_at": r.created_at,
            }
            for r in rows
        ]
