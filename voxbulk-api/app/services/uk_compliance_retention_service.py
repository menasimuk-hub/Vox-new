"""Scheduled anonymisation / soft-delete for aged messaging and response data."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_sessionmaker
from app.models.organisation_ai_config import OrganisationComplianceConfig
from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.models.whatsapp_log import WhatsAppLog
from app.services.uk_compliance_audit_service import UkComplianceAuditService
from app.services.uk_compliance_constants import (
    DEFAULT_RETENTION_DAYS_MESSAGES,
    DEFAULT_RETENTION_DAYS_RECORDINGS,
    DEFAULT_RETENTION_DAYS_RESPONSES,
    DEFAULT_RETENTION_DAYS_TRANSCRIPTS,
)

logger = logging.getLogger(__name__)
ANONYMISED = "[redacted]"

_PER_ORG_LOG_LIMIT = 200
_PER_ORG_RECIPIENT_LIMIT = 150
_PER_ORG_ORDER_LIMIT = 50
_PER_ORG_MEDIA_LIMIT = 100


def _cutoff(days: int) -> datetime:
    return datetime.utcnow() - timedelta(days=max(1, days))


def _days(row: OrganisationComplianceConfig | None, field: str, default: int) -> int:
    raw = getattr(row, field, None) if row is not None else None
    try:
        value = int(raw) if raw is not None else default
    except (TypeError, ValueError):
        value = default
    return max(1, value)


class UkComplianceRetentionService:
    @staticmethod
    def _org_ids_with_data(db: Session) -> set[str]:
        ids: set[str] = set()
        ids.update(db.execute(select(OrganisationComplianceConfig.org_id)).scalars().all())
        ids.update(db.execute(select(WhatsAppLog.org_id).distinct()).scalars().all())
        ids.update(db.execute(select(ServiceOrder.org_id).distinct()).scalars().all())
        return {str(oid) for oid in ids if oid}

    @staticmethod
    def run_retention_pass(db: Session, *, dry_run: bool = False) -> dict[str, Any]:
        stats: dict[str, Any] = {
            "whatsapp_logs_anonymised": 0,
            "whatsapp_media_anonymised": 0,
            "recipient_results_anonymised": 0,
            "order_reports_anonymised": 0,
            "orgs_processed": 0,
            "per_org_retention": True,
            "dry_run": dry_run,
        }
        config_by_org = {
            str(row.org_id): row for row in db.execute(select(OrganisationComplianceConfig)).scalars()
        }

        for org_id in sorted(UkComplianceRetentionService._org_ids_with_data(db)):
            row = config_by_org.get(org_id)
            msg_cutoff = _cutoff(_days(row, "retention_days_messages", DEFAULT_RETENTION_DAYS_MESSAGES))
            resp_cutoff = _cutoff(_days(row, "retention_days_responses", DEFAULT_RETENTION_DAYS_RESPONSES))
            rec_cutoff = _cutoff(_days(row, "retention_days_recordings", DEFAULT_RETENTION_DAYS_RECORDINGS))
            trans_cutoff = _cutoff(_days(row, "retention_days_transcripts", DEFAULT_RETENTION_DAYS_TRANSCRIPTS))
            stats["orgs_processed"] += 1

            wa_logs = list(
                db.execute(
                    select(WhatsAppLog)
                    .where(
                        WhatsAppLog.org_id == org_id,
                        WhatsAppLog.created_at < msg_cutoff,
                        WhatsAppLog.body.isnot(None),
                        WhatsAppLog.body != ANONYMISED,
                    )
                    .limit(_PER_ORG_LOG_LIMIT)
                ).scalars()
            )
            for log in wa_logs:
                if not dry_run:
                    log.body = ANONYMISED
                    db.add(log)
                stats["whatsapp_logs_anonymised"] += 1

            media_logs = list(
                db.execute(
                    select(WhatsAppLog)
                    .where(
                        WhatsAppLog.org_id == org_id,
                        WhatsAppLog.created_at < rec_cutoff,
                        WhatsAppLog.media_json.isnot(None),
                        WhatsAppLog.media_json != ANONYMISED,
                    )
                    .limit(_PER_ORG_MEDIA_LIMIT)
                ).scalars()
            )
            for log in media_logs:
                if not dry_run:
                    log.media_json = ANONYMISED
                    db.add(log)
                stats["whatsapp_media_anonymised"] += 1

            recipients = list(
                db.execute(
                    select(ServiceOrderRecipient)
                    .join(ServiceOrder, ServiceOrderRecipient.order_id == ServiceOrder.id)
                    .where(
                        ServiceOrder.org_id == org_id,
                        ServiceOrderRecipient.created_at < resp_cutoff,
                        ServiceOrderRecipient.result_json.isnot(None),
                    )
                    .limit(_PER_ORG_RECIPIENT_LIMIT)
                ).scalars()
            )
            for rec in recipients:
                try:
                    data = json.loads(rec.result_json or "{}")
                except Exception:
                    data = {}
                if not isinstance(data, dict) or data.get("_retention_redacted"):
                    continue
                if not dry_run:
                    redacted = {
                        "_retention_redacted": True,
                        "redacted_at": datetime.utcnow().isoformat(),
                        "status": data.get("status") or rec.status,
                    }
                    rec.result_json = json.dumps(redacted, ensure_ascii=False)
                    if rec.cv_text:
                        rec.cv_text = None
                    db.add(rec)
                stats["recipient_results_anonymised"] += 1

            orders = list(
                db.execute(
                    select(ServiceOrder).where(
                        ServiceOrder.org_id == org_id,
                        ServiceOrder.completed_at.isnot(None),
                        ServiceOrder.completed_at < trans_cutoff,
                        ServiceOrder.report_json.isnot(None),
                    ).limit(_PER_ORG_ORDER_LIMIT)
                ).scalars()
            )
            for order in orders:
                try:
                    existing = json.loads(order.report_json or "{}")
                except Exception:
                    existing = {}
                if isinstance(existing, dict) and existing.get("_retention_redacted"):
                    continue
                if not dry_run:
                    order.report_json = json.dumps(
                        {"_retention_redacted": True, "redacted_at": datetime.utcnow().isoformat()},
                        ensure_ascii=False,
                    )
                    db.add(order)
                stats["order_reports_anonymised"] += 1

        if not dry_run and any(
            stats[k]
            for k in (
                "whatsapp_logs_anonymised",
                "whatsapp_media_anonymised",
                "recipient_results_anonymised",
                "order_reports_anonymised",
            )
        ):
            db.commit()
            UkComplianceAuditService.record(
                db,
                event_type="retention.pass",
                detail=stats,
            )
        return stats


async def uk_compliance_retention_scheduler_loop() -> None:
    """Daily retention pass (runs in main.py lifespan)."""
    from app.services.scheduler_lock import is_scheduler_leader

    await asyncio.sleep(300)
    while True:
        try:
            if is_scheduler_leader():
                with get_sessionmaker()() as db:
                    stats = UkComplianceRetentionService.run_retention_pass(db, dry_run=False)
                    logger.info("uk_compliance_retention_pass", extra=stats)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("uk_compliance_retention_failed", extra={"error": str(exc)})
        await asyncio.sleep(86400)
