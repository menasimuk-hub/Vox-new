"""Celery — Smart Card QR renewal reminder emails."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select

from app.core.database import get_sessionmaker
from app.models.organisation import Organisation
from app.models.smart_card import SMART_CARD_SERVICE_CODE, SmartCardRenewalReminderSend
from app.models.subscription import Subscription
from app.models.user import User
from app.models.membership import OrganisationMembership
from app.services.smart_card.email_service import SmartCardEmailService
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

WINDOWS = (
    ("30d", 30),
    ("14d", 14),
    ("7d", 7),
    ("1d", 1),
)


def _owner_emails(db, org_id: str) -> list[str]:
    emails: list[str] = []
    rows = (
        db.execute(
            select(OrganisationMembership).where(OrganisationMembership.org_id == org_id).limit(20)
        )
        .scalars()
        .all()
    )
    for m in rows:
        role = str(m.role or "").lower()
        if role not in {"owner", "manager", "", "sales"}:
            continue
        user = db.get(User, m.user_id)
        if user and user.email:
            emails.append(str(user.email).strip().lower())
    return list(dict.fromkeys(emails))


@celery_app.task(name="smart_card.send_renewal_reminders")
def send_renewal_reminders() -> dict[str, Any]:
    sent = 0
    expired = 0
    now = datetime.utcnow()
    with get_sessionmaker()() as db:
        subs = (
            db.execute(
                select(Subscription).where(
                    Subscription.service_code == SMART_CARD_SERVICE_CODE,
                    Subscription.current_period_end.is_not(None),
                )
            )
            .scalars()
            .all()
        )
        for sub in subs:
            end = sub.current_period_end
            if end is None:
                continue
            org = db.get(Organisation, sub.org_id)
            org_name = (org.name if org else "your organisation") or "your organisation"
            seats = int(sub.seat_quantity or 0)
            emails = _owner_emails(db, sub.org_id)
            if not emails:
                continue

            # Expired notice
            if end < now:
                already = db.execute(
                    select(SmartCardRenewalReminderSend).where(
                        SmartCardRenewalReminderSend.subscription_id == sub.id,
                        SmartCardRenewalReminderSend.window_key == "expired",
                        SmartCardRenewalReminderSend.period_end == end,
                    )
                ).scalar_one_or_none()
                if already is None:
                    for em in emails:
                        SmartCardEmailService.send_renewal_reminder(
                            db,
                            to_email=em,
                            window_key="expired",
                            org_name=org_name,
                            period_end=end.isoformat(),
                            seats=seats,
                        )
                    db.add(
                        SmartCardRenewalReminderSend(
                            id=str(uuid.uuid4()),
                            org_id=sub.org_id,
                            subscription_id=sub.id,
                            window_key="expired",
                            period_end=end,
                            sent_at=now,
                        )
                    )
                    expired += 1
                continue

            days_left = (end.date() - now.date()).days
            for key, days in WINDOWS:
                if days_left != days:
                    continue
                already = db.execute(
                    select(SmartCardRenewalReminderSend).where(
                        SmartCardRenewalReminderSend.subscription_id == sub.id,
                        SmartCardRenewalReminderSend.window_key == key,
                        SmartCardRenewalReminderSend.period_end == end,
                    )
                ).scalar_one_or_none()
                if already is not None:
                    continue
                for em in emails:
                    SmartCardEmailService.send_renewal_reminder(
                        db,
                        to_email=em,
                        window_key=key,
                        org_name=org_name,
                        period_end=end.date().isoformat(),
                        seats=seats,
                    )
                db.add(
                    SmartCardRenewalReminderSend(
                        id=str(uuid.uuid4()),
                        org_id=sub.org_id,
                        subscription_id=sub.id,
                        window_key=key,
                        period_end=end,
                        sent_at=now,
                    )
                )
                sent += 1
        db.commit()
    return {"ok": True, "reminders_sent": sent, "expired_notices": expired}
