from __future__ import annotations

import logging

from app.core.database import get_sessionmaker
from app.services.billing_lifecycle_service import BillingLifecycleService
from app.services.usage_wallet_service import UsageWalletService
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="billing.rollover_usage_periods")
def rollover_usage_periods_task() -> dict:
    with get_sessionmaker()() as db:
        stats = UsageWalletService.rollover_due_periods(db)
    logger.info("usage_period_rollover_complete", extra=stats)
    return stats


@celery_app.task(name="billing.process_monthly_subscriptions")
def process_monthly_subscriptions_task() -> dict:
    from app.services.subscription_cancellation_service import SubscriptionCancellationService

    with get_sessionmaker()() as db:
        stats = BillingLifecycleService.process_due_monthly_billing(db)
        cancel_stats = SubscriptionCancellationService.finalize_due_scheduled_cancellations(db)
        stats = {**stats, **{f"cancellation_{k}": v for k, v in cancel_stats.items()}}
    logger.info("monthly_subscription_billing_complete", extra=stats)
    return stats


@celery_app.task(name="billing.send_renewal_reminders")
def send_renewal_reminders_task() -> dict:
    from app.services.billing_renewal_reminder_service import BillingRenewalReminderService

    with get_sessionmaker()() as db:
        stats = BillingRenewalReminderService.process_due_renewal_reminders(db)
    logger.info("renewal_reminder_complete", extra=stats)
    return stats


@celery_app.task(name="billing.send_pending_invoice_reminders")
def send_pending_invoice_reminders_task() -> dict:
    from app.services.billing_pending_invoice_reminder_service import BillingPendingInvoiceReminderService

    with get_sessionmaker()() as db:
        stats = BillingPendingInvoiceReminderService.process_due_reminders(db)
    logger.info("pending_invoice_reminder_complete", extra=stats)
    return stats


@celery_app.task(name="billing.retry_failed_dd_payments")
def retry_failed_dd_payments_task() -> dict:
    with get_sessionmaker()() as db:
        stats = BillingLifecycleService.retry_due_dd_invoices(db)
    logger.info("dd_retry_billing_complete", extra=stats)
    return stats


@celery_app.task(name="billing.retry_campaign_settlement", bind=True, max_retries=3, default_retry_delay=120)
def retry_campaign_settlement(self, order_id: str, trigger: str = "completion") -> dict:
    from app.models.service_order import ServiceOrder
    from app.services.campaign_billing_settlement_service import CampaignBillingSettlementService

    with get_sessionmaker()() as db:
        order = db.get(ServiceOrder, order_id)
        if order is None:
            return {"ok": False, "reason": "order_not_found"}
        try:
            result = CampaignBillingSettlementService.settle_order(db, order, trigger=trigger)
            return {"ok": True, "settled": result is not None}
        except Exception as exc:
            logger.exception("campaign_settlement_retry_failed order_id=%s", order_id)
            if self.request.retries < self.max_retries:
                raise self.retry(exc=exc)
            return {"ok": False, "reason": str(exc)}
