from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.org_audit_event import OrganisationAuditEvent
from app.models.user import User


def _event_dict(r: OrganisationAuditEvent) -> dict[str, Any]:
    metadata = None
    if r.metadata_json:
        try:
            metadata = json.loads(r.metadata_json)
        except Exception:
            metadata = {"raw": r.metadata_json}
    return {
        "id": r.id,
        "org_id": r.org_id,
        "action": r.action,
        "detail": r.detail,
        "event_type": r.event_type or r.action,
        "entity_type": r.entity_type,
        "entity_id": r.entity_id,
        "metadata": metadata,
        "actor_email": r.actor_email,
        "actor_user_id": r.actor_user_id,
        "created_at": r.created_at,
    }


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
        event_type: str | None = None,
        entity_type: str | None = None,
        entity_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        commit: bool = True,
    ) -> OrganisationAuditEvent:
        row = OrganisationAuditEvent(
            org_id=org_id,
            actor_user_id=actor_user_id,
            actor_email=actor_email,
            action=str(action).strip()[:120],
            detail=(str(detail).strip()[:4000] if detail else None),
            event_type=(str(event_type or action).strip()[:80] if (event_type or action) else None),
            entity_type=(str(entity_type).strip()[:40] if entity_type else None),
            entity_id=(str(entity_id).strip()[:36] if entity_id else None),
            metadata_json=json.dumps(metadata, ensure_ascii=False) if metadata else None,
            created_at=datetime.utcnow(),
        )
        db.add(row)
        if commit:
            db.commit()
            db.refresh(row)
        return row

    @staticmethod
    def record_admin(
        db: Session,
        *,
        org_id: str,
        event_type: str,
        action: str,
        entity_type: str | None = None,
        entity_id: str | None = None,
        detail: str | None = None,
        metadata: dict[str, Any] | None = None,
        actor_user_id: str | None = None,
        actor_email: str | None = None,
        commit: bool = True,
    ) -> OrganisationAuditEvent:
        return OrgAuditService.record(
            db,
            org_id=org_id,
            action=action,
            detail=detail,
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            metadata=metadata,
            actor_user_id=actor_user_id,
            actor_email=actor_email,
            commit=commit,
        )

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
        return [_event_dict(r) for r in rows]

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
        return [_event_dict(r) for r in rows]
