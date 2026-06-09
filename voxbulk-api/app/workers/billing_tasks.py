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
    with get_sessionmaker()() as db:
        stats = BillingLifecycleService.process_due_monthly_billing(db)
    logger.info("monthly_subscription_billing_complete", extra=stats)
    return stats


@celery_app.task(name="billing.retry_failed_dd_payments")
def retry_failed_dd_payments_task() -> dict:
    with get_sessionmaker()() as db:
        stats = BillingLifecycleService.retry_due_dd_invoices(db)
    logger.info("dd_retry_billing_complete", extra=stats)
    return stats
