"""Subscription renewal reminder emails."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from unittest.mock import patch

from sqlalchemy import select

from app.core.database import get_sessionmaker
from app.core.security import hash_password
from app.models.membership import OrganisationMembership
from app.models.organisation import Organisation
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.models.user import User
from app.services.billing_renewal_reminder_service import BillingRenewalReminderService
from app.services.platform_catalog_service import PlatformCatalogService


def _seed_org_with_sub(*, days_until_renewal: int) -> tuple[str, str]:
    with get_sessionmaker()() as db:
        from app.services.gocardless_service import BillingService

        PlatformCatalogService.ensure_defaults(db)
        BillingService.ensure_default_plans(db)
        org = Organisation(name="Renewal Org", contact_email="renewal@example.com")
        db.add(org)
        db.flush()
        user = User(
            email=f"renewal-{uuid.uuid4().hex[:8]}@example.com",
            password_hash=hash_password("pass123"),
            is_active=True,
        )
        db.add(user)
        db.flush()
        db.add(OrganisationMembership(org_id=org.id, user_id=user.id))
        plan = db.execute(select(Plan).where(Plan.service_kind == "voxbulk").limit(1)).scalar_one()
        period_end = datetime.utcnow() + timedelta(days=days_until_renewal)
        sub = Subscription(
            org_id=org.id,
            plan_id=plan.id,
            service_code="voxbulk",
            status="active",
            current_period_end=period_end,
        )
        db.add(sub)
        db.commit()
        return org.id, sub.id


def test_renewal_reminder_sends_for_matching_day_window():
    org_id, sub_id = _seed_org_with_sub(days_until_renewal=7)
    with get_sessionmaker()() as db, patch(
        "app.services.billing_refund_email_service.BillingRefundEmailService.send_renewal_reminder",
        return_value=True,
    ) as send_mock:
        stats = BillingRenewalReminderService.process_due_renewal_reminders(db)
        assert stats["sent"] == 1
        send_mock.assert_called_once()
        kwargs = send_mock.call_args.kwargs
        assert kwargs["org"].id == org_id
        assert kwargs["days_remaining"] == 7

    with get_sessionmaker()() as db, patch(
        "app.services.billing_refund_email_service.BillingRefundEmailService.send_renewal_reminder",
        return_value=True,
    ) as send_mock:
        stats = BillingRenewalReminderService.process_due_renewal_reminders(db)
        assert stats["sent"] == 0
        assert stats["skipped"] >= 1
        send_mock.assert_not_called()


def test_finalize_cancellation_notifies_subscription_ended():
    from app.services.subscription_cancellation_service import (
        CANCELLATION_SCHEDULED,
        SubscriptionCancellationService,
    )

    org_id, sub_id = _seed_org_with_sub(days_until_renewal=30)
    with get_sessionmaker()() as db:
        sub = db.get(Subscription, sub_id)
        sub.cancellation_status = CANCELLATION_SCHEDULED
        sub.cancellation_effective_at = datetime.utcnow() - timedelta(hours=1)
        db.add(sub)
        db.commit()

    with get_sessionmaker()() as db, patch.object(
        SubscriptionCancellationService,
        "_notify_subscription_ended",
    ) as notify_mock:
        stats = SubscriptionCancellationService.finalize_due_scheduled_cancellations(db)
        assert stats["finalized"] == 1
        notify_mock.assert_called_once()
