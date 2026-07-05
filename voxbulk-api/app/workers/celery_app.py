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
        "wa-template-meta-status-sync-15m": {
            "task": "survey.sync_wa_template_meta_statuses",
            "schedule": 900.0,
        },
    },
)

celery_app.autodiscover_tasks(["app.workers"])

# Ensure task modules outside tasks.py are registered (beat + workers).
from app.workers import billing_tasks  # noqa: E402, F401
from app.workers import sales_tasks  # noqa: E402, F401
from app.workers import survey_wa_voice_note_tasks  # noqa: E402, F401
from app.workers import survey_wa_recommendations_tasks  # noqa: E402, F401
from app.workers import survey_wa_translation_tasks  # noqa: E402, F401
from app.workers import crm_automation_tasks  # noqa: E402, F401
from app.workers import appointment_tasks  # noqa: E402, F401
from app.workers import demo_account_tasks  # noqa: E402, F401
from app.workers import survey_wa_template_tasks  # noqa: E402, F401

"""TODO: Configure queues/routing/retries in later phase."""

