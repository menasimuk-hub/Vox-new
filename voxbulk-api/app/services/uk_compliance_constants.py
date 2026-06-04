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
