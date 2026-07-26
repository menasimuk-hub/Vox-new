from __future__ import annotations

import logging

from app.core.database import get_sessionmaker
from app.services.ai_team_service import AiTeamService
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="ai_team.process_followups")
def process_ai_team_followups_task() -> dict:
    with get_sessionmaker()() as db:
        stats = AiTeamService.process_due_followups(db)
    logger.info("ai_team_followups_complete", extra=stats)
    return stats
