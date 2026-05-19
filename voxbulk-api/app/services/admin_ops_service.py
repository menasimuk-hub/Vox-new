from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.recovery_job import RecoveryJob
from app.models.webhook_event import WebhookEvent


@dataclass(frozen=True)
class AdminWebhookOverview:
    total_recent: int
    received: int
    processing: int
    processed: int
    failed: int
    latest_received_at: datetime | None


@dataclass(frozen=True)
class AdminRecoveryJobsOverview:
    total_recent: int
    queued: int
    calling: int
    messaged: int
    recovered: int
    failed: int
    skipped: int
    latest_created_at: datetime | None


class AdminOperationsService:
    @staticmethod
    def webhook_overview(db: Session, *, limit_window: int = 200) -> AdminWebhookOverview:
        # Count by status on last N events to keep it fast and bounded.
        ids = [r[0] for r in db.execute(select(WebhookEvent.id).order_by(WebhookEvent.id.desc()).limit(limit_window)).all()]
        if not ids:
            return AdminWebhookOverview(0, 0, 0, 0, 0, None)

        counts = dict(
            db.execute(select(WebhookEvent.status, func.count()).where(WebhookEvent.id.in_(ids)).group_by(WebhookEvent.status)).all()
        )
        latest = db.execute(select(func.max(WebhookEvent.received_at)).where(WebhookEvent.id.in_(ids))).scalar_one()
        return AdminWebhookOverview(
            total_recent=len(ids),
            received=int(counts.get("received", 0)),
            processing=int(counts.get("processing", 0)),
            processed=int(counts.get("processed", 0)),
            failed=int(counts.get("failed", 0)),
            latest_received_at=latest,
        )

    @staticmethod
    def recovery_jobs_overview(db: Session, *, limit_window: int = 200) -> AdminRecoveryJobsOverview:
        ids = [r[0] for r in db.execute(select(RecoveryJob.id).order_by(RecoveryJob.created_at.desc()).limit(limit_window)).all()]
        if not ids:
            return AdminRecoveryJobsOverview(0, 0, 0, 0, 0, 0, 0, None)

        counts = dict(
            db.execute(select(RecoveryJob.state, func.count()).where(RecoveryJob.id.in_(ids)).group_by(RecoveryJob.state)).all()
        )
        latest = db.execute(select(func.max(RecoveryJob.created_at)).where(RecoveryJob.id.in_(ids))).scalar_one()
        return AdminRecoveryJobsOverview(
            total_recent=len(ids),
            queued=int(counts.get("queued", 0)),
            calling=int(counts.get("calling", 0)),
            messaged=int(counts.get("messaged", 0)),
            recovered=int(counts.get("recovered", 0)),
            failed=int(counts.get("failed", 0)),
            skipped=int(counts.get("skipped", 0)),
            latest_created_at=latest,
        )

