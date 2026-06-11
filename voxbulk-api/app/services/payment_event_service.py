"""Record provider and internal billing/payment events for admin audit."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.payment_event import PaymentEvent


class PaymentEventService:
    @staticmethod
    def record(
        db: Session,
        *,
        org_id: str,
        client_email: str,
        status: str,
        provider: str = "internal",
        external_event_id: str | None = None,
        event_kind: str | None = None,
        source: str | None = None,
        failure_reason: str | None = None,
        actor_user_id: str | None = None,
        subscription_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        commit: bool = True,
    ) -> PaymentEvent:
        row = PaymentEvent(
            provider=str(provider or "internal").strip()[:40],
            external_event_id=(external_event_id or str(uuid.uuid4()))[:128],
            org_id=org_id,
            client_email=(client_email or "admin@voxbulk.com")[:320],
            status=str(status or "recorded").strip()[:40],
            failure_reason=(failure_reason or "")[:500] or None,
            event_kind=(event_kind or status or "event")[:40],
            source=(source or "admin")[:40],
            metadata_json=json.dumps(metadata, ensure_ascii=False) if metadata else None,
            actor_user_id=actor_user_id,
            subscription_id=subscription_id,
            created_at=datetime.utcnow(),
        )
        db.add(row)
        if commit:
            db.commit()
            db.refresh(row)
        return row

    @staticmethod
    def record_finance(
        db: Session,
        *,
        org_id: str,
        event_kind: str,
        client_email: str,
        status: str = "succeeded",
        actor_user_id: str | None = None,
        subscription_id: str | None = None,
        source: str = "admin",
        metadata: dict[str, Any] | None = None,
        failure_reason: str | None = None,
        provider: str = "internal",
        commit: bool = True,
    ) -> PaymentEvent:
        """Record an internal admin/system billing event (non-provider webhook)."""
        return PaymentEventService.record(
            db,
            org_id=org_id,
            client_email=client_email,
            status=status,
            provider=provider,
            event_kind=event_kind,
            source=source,
            failure_reason=failure_reason,
            actor_user_id=actor_user_id,
            subscription_id=subscription_id,
            metadata=metadata,
            commit=commit,
        )

    @staticmethod
    def event_to_dict(row: PaymentEvent, *, org_name: str | None = None) -> dict[str, Any]:
        metadata = None
        if row.metadata_json:
            try:
                metadata = json.loads(row.metadata_json)
            except Exception:
                metadata = {"raw": row.metadata_json}
        return {
            "id": row.id,
            "provider": row.provider,
            "external_event_id": row.external_event_id,
            "org_id": row.org_id,
            "organisation_name": org_name,
            "client_email": row.client_email,
            "status": row.status,
            "failure_reason": row.failure_reason,
            "event_kind": row.event_kind,
            "source": row.source,
            "metadata": metadata,
            "actor_user_id": row.actor_user_id,
            "subscription_id": row.subscription_id,
            "emailed_at": row.emailed_at.isoformat() if row.emailed_at else None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
