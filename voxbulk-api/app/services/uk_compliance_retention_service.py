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


def _cutoff(days: int) -> datetime:
    return datetime.utcnow() - timedelta(days=max(1, days))


class UkComplianceRetentionService:
    @staticmethod
    def run_retention_pass(db: Session, *, dry_run: bool = False) -> dict[str, Any]:
        stats = {
            "whatsapp_logs_anonymised": 0,
            "recipient_results_anonymised": 0,
            "order_reports_anonymised": 0,
            "dry_run": dry_run,
        }
        org_rows = list(db.execute(select(OrganisationComplianceConfig)).scalars())
        default_days_msg = DEFAULT_RETENTION_DAYS_MESSAGES
        default_days_resp = DEFAULT_RETENTION_DAYS_RESPONSES

        msg_cutoff = _cutoff(default_days_msg)
        resp_cutoff = _cutoff(default_days_resp)

        wa_logs = list(
            db.execute(
                select(WhatsAppLog).where(
                    WhatsAppLog.created_at < msg_cutoff,
                    WhatsAppLog.body.isnot(None),
                    WhatsAppLog.body != ANONYMISED,
                ).limit(500)
            ).scalars()
        )
        for log in wa_logs:
            if not dry_run:
                log.body = ANONYMISED
                db.add(log)
            stats["whatsapp_logs_anonymised"] += 1

        recipients = list(
            db.execute(
                select(ServiceOrderRecipient).where(
                    ServiceOrderRecipient.created_at < resp_cutoff,
                    ServiceOrderRecipient.result_json.isnot(None),
                ).limit(300)
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
                    ServiceOrder.completed_at.isnot(None),
                    ServiceOrder.completed_at < _cutoff(DEFAULT_RETENTION_DAYS_TRANSCRIPTS),
                    ServiceOrder.report_json.isnot(None),
                ).limit(100)
            ).scalars()
        )
        for order in orders:
            if not dry_run:
                order.report_json = json.dumps(
                    {"_retention_redacted": True, "redacted_at": datetime.utcnow().isoformat()},
                    ensure_ascii=False,
                )
                db.add(order)
            stats["order_reports_anonymised"] += 1

        if not dry_run and any(
            stats[k] for k in ("whatsapp_logs_anonymised", "recipient_results_anonymised", "order_reports_anonymised")
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
    await asyncio.sleep(300)
    while True:
        try:
            with get_sessionmaker()() as db:
                stats = UkComplianceRetentionService.run_retention_pass(db, dry_run=False)
                logger.info("uk_compliance_retention_pass", extra=stats)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("uk_compliance_retention_failed", extra={"error": str(exc)})
        await asyncio.sleep(86400)
