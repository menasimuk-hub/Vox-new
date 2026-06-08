from __future__ import annotations

from celery import Celery

from app.core.config import get_settings


settings = get_settings()

celery_app = Celery(
    "retover",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        "rollover-usage-periods-daily": {
            "task": "billing.rollover_usage_periods",
            "schedule": 86400.0,
        },
        "sales-promo-followups-daily": {
            "task": "sales.process_promo_followups",
            "schedule": 3600.0,
        },
        "purge-voice-note-audio-daily": {
            "task": "survey.purge_voice_note_audio",
            "schedule": 86400.0,
        },
    },
)

celery_app.autodiscover_tasks(["app.workers"])

# Ensure task modules outside tasks.py are registered (beat + workers).
from app.workers import billing_tasks  # noqa: E402, F401
from app.workers import sales_tasks  # noqa: E402, F401
from app.workers import survey_wa_voice_note_tasks  # noqa: E402, F401
from app.workers import survey_wa_translation_tasks  # noqa: E402, F401

"""TODO: Configure queues/routing/retries in later phase."""

