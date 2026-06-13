"""Idempotent external event logging for Abuu."""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.abuu.models.entities import AbuuExternalEvent

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ExternalEventResult:
    is_duplicate: bool
    row: AbuuExternalEvent


def payload_hash(payload: dict[str, Any] | None) -> str:
    normalized = json.dumps(payload or {}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class AbuuEventIdempotencyService:
    @staticmethod
    def begin_event(
        db: Session,
        *,
        source: str,
        event_type: str,
        idempotency_key: str,
        order_id: str | None = None,
        source_message_id: str | None = None,
        payload: dict | None = None,
    ) -> ExternalEventResult:
        p_hash = payload_hash(payload)
        existing = db.execute(
            select(AbuuExternalEvent).where(
                AbuuExternalEvent.source == source,
                AbuuExternalEvent.idempotency_key == idempotency_key,
            )
        ).scalars().first()
        if existing is not None:
            logger.info(
                "abuu_event_duplicate source=%s event_type=%s key=%s order_id=%s",
                source,
                event_type,
                idempotency_key,
                order_id,
            )
            return ExternalEventResult(is_duplicate=True, row=existing)

        row = AbuuExternalEvent(
            source=source,
            event_type=event_type,
            idempotency_key=idempotency_key,
            source_message_id=source_message_id,
            order_id=order_id,
            payload_hash=p_hash,
            status="processed",
            processed_at=datetime.utcnow(),
            created_at=datetime.utcnow(),
        )
        db.add(row)
        db.flush()
        return ExternalEventResult(is_duplicate=False, row=row)

    @staticmethod
    def mark_failed(db: Session, row: AbuuExternalEvent, *, error_detail: str) -> None:
        row.status = "failed"
        row.error_detail = error_detail[:2000]
        row.processed_at = datetime.utcnow()
        db.add(row)

    @staticmethod
    def mark_duplicate(db: Session, row: AbuuExternalEvent) -> None:
        row.status = "duplicate"
        row.processed_at = datetime.utcnow()
        db.add(row)

    @staticmethod
    def mark_ignored(db: Session, row: AbuuExternalEvent, *, reason: str) -> None:
        row.status = "ignored"
        row.error_detail = reason[:2000]
        row.processed_at = datetime.utcnow()
        db.add(row)

    @staticmethod
    def list_events(
        db: Session,
        *,
        status: str | None = None,
        event_type: str | None = None,
        order_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AbuuExternalEvent]:
        stmt = select(AbuuExternalEvent).order_by(AbuuExternalEvent.created_at.desc())
        if status:
            stmt = stmt.where(AbuuExternalEvent.status == status)
        if event_type:
            stmt = stmt.where(AbuuExternalEvent.event_type == event_type)
        if order_id:
            stmt = stmt.where(AbuuExternalEvent.order_id == order_id)
        return list(db.execute(stmt.offset(offset).limit(limit)).scalars().all())
