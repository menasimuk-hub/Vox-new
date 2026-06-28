"""UK GDPR / PECR / DPA 2018 baseline constants (not legal advice)."""

from __future__ import annotations

LAWFUL_BASES = frozenset({"consent", "contract", "legitimate_interests", "legal_obligation"})

MESSAGE_PURPOSES = frozenset({"transactional", "survey", "interview", "direct_marketing"})

ARTICLE9_CONDITIONS = frozenset(
    {
        "explicit_consent",
        "employment_safeguard",
        "vital_interests",
        "legal_claims",
        "substantial_public_interest",
        "health_social_care",
        "public_health",
        "archiving_research",
    }
)

DEFAULT_RETENTION_DAYS_MESSAGES = 365
DEFAULT_RETENTION_DAYS_RESPONSES = 730
DEFAULT_RETENTION_DAYS_RECORDINGS = 90
DEFAULT_RETENTION_DAYS_TRANSCRIPTS = 365

DEFAULT_PRIVACY_NOTICE_URL = "https://www.voxbulk.com/privacy"
DEFAULT_COMPLIANCE_CONTACT_EMAIL = "Data.Pro@voxbulk.com"
DEFAULT_LAWFUL_BASIS = "legitimate_interests"

# Outbound email templates checked for UK compliance before interview/survey launch.
LAUNCH_OUTBOUND_EMAIL_TEMPLATE_KEYS: tuple[str, ...] = (
    "interview_scheduling_invite",
    "interview_booking_invite",
    "interview_booking_confirm",
    "interview_booking_reminder",
    "interview_booking_cancel",
    "interview_campaign_cancelled",
    "interview_meeting_missed",
    "interview_missed_call_followup",
    "general_notification",
    "sales_offer",
)

PRIMARY_LAUNCH_EMAIL_TEMPLATE_KEY: dict[str, str] = {
    "interview": "interview_booking_invite",
    "survey": "general_notification",
}
