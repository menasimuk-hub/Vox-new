"""Platform compliance audit trail (admin-visible)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.platform_compliance_audit import PlatformComplianceAuditEvent


class UkComplianceAuditService:
    @staticmethod
    def record(
        db: Session,
        *,
        event_type: str,
        org_id: str | None = None,
        actor_user_id: str | None = None,
        order_id: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> PlatformComplianceAuditEvent:
        row = PlatformComplianceAuditEvent(
            id=str(uuid.uuid4()),
            event_type=str(event_type).strip()[:64],
            org_id=org_id,
            actor_user_id=actor_user_id,
            order_id=order_id,
            resource_type=(str(resource_type).strip()[:32] if resource_type else None),
            resource_id=(str(resource_id).strip()[:64] if resource_id else None),
            detail_json=json.dumps(detail or {}, ensure_ascii=False),
            created_at=datetime.utcnow(),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def list_recent(
        db: Session,
        *,
        limit: int = 100,
        event_type: str | None = None,
        org_id: str | None = None,
    ) -> list[dict[str, Any]]:
        q = select(PlatformComplianceAuditEvent).order_by(PlatformComplianceAuditEvent.created_at.desc())
        if event_type:
            q = q.where(PlatformComplianceAuditEvent.event_type == event_type)
        if org_id:
            q = q.where(PlatformComplianceAuditEvent.org_id == org_id)
        rows = list(db.execute(q.limit(max(1, min(500, limit)))).scalars())
        out: list[dict[str, Any]] = []
        for row in rows:
            try:
                detail = json.loads(row.detail_json or "{}")
            except Exception:
                detail = {}
            out.append(
                {
                    "id": row.id,
                    "event_type": row.event_type,
                    "org_id": row.org_id,
                    "actor_user_id": row.actor_user_id,
                    "order_id": row.order_id,
                    "resource_type": row.resource_type,
                    "resource_id": row.resource_id,
                    "detail": detail,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                }
            )
        return out
