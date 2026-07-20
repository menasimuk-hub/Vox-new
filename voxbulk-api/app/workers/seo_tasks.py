from __future__ import annotations

import logging

from app.core.database import get_sessionmaker
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="seo.weekly_engine_submit")
def weekly_engine_submit_task() -> dict:
    from app.services.seo_engine_service import weekly_auto_submit_if_enabled

    with get_sessionmaker()() as db:
        result = weekly_auto_submit_if_enabled(db)
    logger.info("seo_weekly_engine_submit", extra={"result_keys": list(result.keys())})
    return result


@celery_app.task(name="seo.refresh_keyword_ideas")
def refresh_keyword_ideas_task() -> dict:
    from app.services.seo_engine_service import refresh_keyword_ideas

    with get_sessionmaker()() as db:
        result = refresh_keyword_ideas(db)
    logger.info(
        "seo_keyword_ideas_refreshed",
        extra={"suggested_count": result.get("suggested_count"), "total": len(result.get("items") or [])},
    )
    return {"suggested_count": result.get("suggested_count"), "total": len(result.get("items") or [])}
