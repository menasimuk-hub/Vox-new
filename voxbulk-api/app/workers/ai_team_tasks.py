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


@celery_app.task(
    name="ai_team.scrape_directory",
    bind=True,
    max_retries=1,
    soft_time_limit=900,
    time_limit=960,
    queue="voxbulk",
)
def scrape_directory_task(
    self,
    run_id: str,
    follow_websites: bool = True,
    max_stands: int = 500,
) -> dict:
    """Background exhibitor-directory scrape (Easyfairs / HTML). Survives API worker recycle."""
    stats = AiTeamService.run_directory_scrape_job(
        run_id,
        follow_websites=follow_websites,
        max_stands=max_stands,
    )
    logger.info("ai_team_directory_scrape_complete run_id=%s stats=%s", run_id, stats)
    return stats


@celery_app.task(
    name="ai_team.send_campaign",
    bind=True,
    max_retries=0,
    # 3 emails/min → ~180/hour; allow long cold-outreach queues
    soft_time_limit=28800,
    time_limit=28920,
    queue="voxbulk",
)
def send_campaign_task(self, campaign_id: str) -> dict:
    """Background bulk send for an AI Team campaign (paced queue)."""
    from app.services.ai_team_campaign_service import AiTeamCampaignService

    stats = AiTeamCampaignService.process_send_job(campaign_id)
    logger.info("ai_team_campaign_send_complete campaign_id=%s stats=%s", campaign_id, stats)
    return stats
