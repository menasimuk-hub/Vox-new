"""Proactive subscription renewal reminder emails."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.org_audit_event import OrganisationAuditEvent
from app.models.organisation import Organisation
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.services.billing_refund_email_service import BillingRefundEmailService
from app.services.notification_service import NotificationService
from app.services.org_audit_service import OrgAuditService

logger = logging.getLogger(__name__)

RENEWAL_REMINDER_DAYS = (14, 7, 1)
ACTIVE_SUBSCRIPTION_STATUSES = frozenset({"active", "trial", "pending_first_payment"})


class BillingRenewalReminderService:
    @staticmethod
    def _renewal_email_already_sent(
        db: Session,
        *,
        org_id: str,
        subscription_id: str,
        days_remaining: int,
        period_end_iso: str,
    ) -> bool:
        rows = list(
            db.execute(
                select(OrganisationAuditEvent).where(
                    OrganisationAuditEvent.org_id == org_id,
                    OrganisationAuditEvent.event_type == "subscription.renewal_reminder_email",
                    OrganisationAuditEvent.entity_id == subscription_id,
                )
            )
            .scalars()
            .all()
        )
        for row in rows:
            if not row.metadata_json:
                continue
            try:
                meta = json.loads(row.metadata_json)
            except Exception:
                continue
            if int(meta.get("days") or -1) == int(days_remaining) and str(meta.get("period_end") or "") == period_end_iso:
                return True
        return False

    @staticmethod
    def process_due_renewal_reminders(db: Session, *, as_of: datetime | None = None) -> dict[str, Any]:
        now = as_of or datetime.utcnow()
        stats = {"sent": 0, "skipped": 0, "errors": 0}

        for days in RENEWAL_REMINDER_DAYS:
            target_date = (now + timedelta(days=days)).date()
            subs = list(
                db.execute(
                    select(Subscription).where(
                        Subscription.status.in_(tuple(ACTIVE_SUBSCRIPTION_STATUSES)),
                        Subscription.current_period_end.is_not(None),
                        func.date(Subscription.current_period_end) == target_date,
                    )
                )
                .scalars()
                .all()
            )
            for sub in subs:
                org = db.get(Organisation, sub.org_id)
                if org is None or sub.current_period_end is None:
                    stats["skipped"] += 1
                    continue
                period_end_iso = sub.current_period_end.date().isoformat()
                if BillingRenewalReminderService._renewal_email_already_sent(
                    db,
                    org_id=org.id,
                    subscription_id=sub.id,
                    days_remaining=days,
                    period_end_iso=period_end_iso,
                ):
                    stats["skipped"] += 1
                    continue
                plan = db.get(Plan, sub.plan_id) if sub.plan_id else None
                plan_name = getattr(plan, "name", None) if plan else None
                try:
                    sent = BillingRefundEmailService.send_renewal_reminder(
                        db,
                        org=org,
                        user_id=None,
                        service_code=sub.service_code,
                        plan_name=plan_name,
                        renewal_date=period_end_iso,
                        days_remaining=days,
                    )
                    if sent:
                        OrgAuditService.record(
                            db,
                            org_id=org.id,
                            action=f"Renewal reminder email ({days} days)",
                            event_type="subscription.renewal_reminder_email",
                            entity_type="subscription",
                            entity_id=sub.id,
                            metadata={"days": days, "period_end": period_end_iso},
                            commit=False,
                        )
                        NotificationService.notify_org_renewal_reminder(
                            db,
                            org_id=org.id,
                            subscription_id=sub.id,
                            service_code=sub.service_code,
                            plan_name=plan_name,
                            days_remaining=days,
                            period_end=sub.current_period_end,
                        )
                        stats["sent"] += 1
                    else:
                        stats["skipped"] += 1
                except Exception:
                    logger.exception(
                        "renewal_reminder_failed org_id=%s subscription_id=%s days=%s",
                        org.id,
                        sub.id,
                        days,
                    )
                    stats["errors"] += 1

        if stats["sent"]:
            db.commit()
        return stats
