from __future__ import annotations

import logging

from app.core.database import get_sessionmaker
from app.services.demo_account_seed_service import DemoAccountSeedService
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="demo.seed_sales_account", bind=True, max_retries=1, default_retry_delay=120)
def seed_demo_sales_account_task(self, org_id: str, user_id: str) -> dict:
    """Background demo data for a newly created salesman workspace."""
    try:
        with get_sessionmaker()() as db:
            result = DemoAccountSeedService.seed_for_org(db, org_id=str(org_id), user_id=str(user_id))
        logger.info("demo_seed_sales_account_complete", extra={"org_id": org_id, **result})
        return result
    except Exception as exc:
        logger.exception("demo_seed_sales_account_failed", extra={"org_id": org_id, "error": str(exc)})
        raise self.retry(exc=exc)
