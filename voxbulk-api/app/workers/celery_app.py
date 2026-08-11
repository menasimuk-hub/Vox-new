from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

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
    # Dedicated queue so other Redis workers (fresh@, wa-stt@) cannot steal
    # VoxBulk tasks they do not register (they share broker DB 6 / queue "celery").
    task_default_queue="voxbulk",
    task_default_exchange="voxbulk",
    task_default_routing_key="voxbulk",
    beat_schedule={
        "rollover-usage-periods-daily": {
            "task": "billing.rollover_usage_periods",
            "schedule": 86400.0,
        },
        "monthly-subscription-billing-hourly": {
            "task": "billing.process_monthly_subscriptions",
            "schedule": 3600.0,
        },
        "retry-failed-dd-hourly": {
            "task": "billing.retry_failed_dd_payments",
            "schedule": 3600.0,
        },
        "subscription-renewal-reminders-daily": {
            "task": "billing.send_renewal_reminders",
            "schedule": 86400.0,
        },
        "pending-invoice-reminders-daily": {
            "task": "billing.send_pending_invoice_reminders",
            "schedule": 86400.0,
        },
        "sales-promo-followups-daily": {
            "task": "sales.process_promo_followups",
            "schedule": 3600.0,
        },
        "sales-cleanup-expired-promos-daily": {
            "task": "sales.cleanup_expired_promos",
            "schedule": 86400.0,
        },
        "ai-team-followups-hourly": {
            "task": "ai_team.process_followups",
            "schedule": 3600.0,
        },
        "ai-team-scheduled-campaigns-1m": {
            "task": "ai_team.start_scheduled_campaigns",
            "schedule": 60.0,
        },
        "purge-voice-note-audio-daily": {
            "task": "survey.purge_voice_note_audio",
            "schedule": 86400.0,
        },
        "crm-deal-survey-automation-15m": {
            "task": "crm.poll_deal_survey_automation",
            "schedule": 900.0,
        },
        "appointment-crm-sync-30m": {
            "task": "appointments.sync_crm_appointments",
            "schedule": 1800.0,
        },
        "appointment-confirmation-scan-15m": {
            "task": "appointments.scan_confirmation_windows",
            "schedule": 900.0,
        },
        "appointment-reminder-scan-15m": {
            "task": "appointments.scan_reminder_sequences",
            "schedule": 900.0,
        },
        "appointment-post-survey-scan-15m": {
            "task": "appointments.scan_post_visit_surveys",
            "schedule": 900.0,
        },
        "wa-template-supersede-cleanup-15m": {
            "task": "survey.cleanup_superseded_wa_templates",
            "schedule": 900.0,
        },
        "wa-template-pending-sync-30m": {
            "task": "survey.sync_pending_wa_templates_if_any",
            "schedule": 1800.0,
        },
        "survey-retry-deferred-wa-starts-10m": {
            "task": "survey.retry_deferred_wa_starts",
            "schedule": 600.0,
        },
        "seo-weekly-engine-submit": {
            "task": "seo.weekly_engine_submit",
            "schedule": crontab(hour=6, minute=15, day_of_week="mon"),
        },
        "seo-keyword-ideas-weekly": {
            "task": "seo.refresh_keyword_ideas",
            "schedule": crontab(hour=6, minute=30, day_of_week="mon"),
        },
        "expo-visitor-day-summaries-hourly": {
            "task": "expo.send_visitor_day_summaries",
            "schedule": 3600.0,
        },
        "expo-purge-visitor-identities-daily": {
            "task": "expo.purge_expired_visitor_identities",
            "schedule": 86400.0,
        },
        "smart-card-renewal-reminders-daily": {
            "task": "smart_card.send_renewal_reminders",
            "schedule": 86400.0,
        },
        "smart-card-mailbox-sync-daily": {
            "task": "smart_card.sync_mailbox_to_tickets",
            "schedule": 86400.0,
        },
    },
)

celery_app.autodiscover_tasks(["app.workers"])

# Ensure task modules outside tasks.py are registered (beat + workers).
from app.workers import billing_tasks  # noqa: E402, F401
from app.workers import sales_tasks  # noqa: E402, F401
from app.workers import ai_team_tasks  # noqa: E402, F401
from app.workers import survey_wa_voice_note_tasks  # noqa: E402, F401
from app.workers import survey_wa_recommendations_tasks  # noqa: E402, F401
from app.workers import survey_wa_translation_tasks  # noqa: E402, F401
from app.workers import crm_automation_tasks  # noqa: E402, F401
from app.workers import appointment_tasks  # noqa: E402, F401
from app.workers import demo_account_tasks  # noqa: E402, F401
from app.workers import survey_wa_template_tasks  # noqa: E402, F401
from app.workers import survey_wa_dispatch_tasks  # noqa: E402, F401
from app.workers import feedback_voice_note_tasks  # noqa: E402, F401
from app.workers import expo_voice_note_tasks  # noqa: E402, F401
from app.workers import expo_summary_tasks  # noqa: E402, F401
from app.workers import expo_notify_tasks  # noqa: E402, F401
from app.workers import smart_card_renewal_tasks  # noqa: E402, F401
from app.workers import seo_tasks  # noqa: E402, F401

"""TODO: Configure queues/routing/retries in later phase."""
