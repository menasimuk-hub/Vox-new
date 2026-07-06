"""Service codes routed through connection profiles."""

from __future__ import annotations

SERVICE_AI_INTERVIEW = "ai_interview"
SERVICE_SURVEY = "survey"
SERVICE_CUSTOMER_FEEDBACK = "customer_feedback"
SERVICE_BOOKING = "booking"
SERVICE_MARKETING = "marketing"

ALL_SERVICE_CODES: tuple[str, ...] = (
    SERVICE_AI_INTERVIEW,
    SERVICE_SURVEY,
    SERVICE_CUSTOMER_FEEDBACK,
    SERVICE_BOOKING,
    SERVICE_MARKETING,
)

_SERVICE_ALIASES: dict[str, str] = {
    "interview": SERVICE_AI_INTERVIEW,
    "ai-interview": SERVICE_AI_INTERVIEW,
    "feedback": SERVICE_CUSTOMER_FEEDBACK,
    "customer-feedback": SERVICE_CUSTOMER_FEEDBACK,
    "appointments": SERVICE_BOOKING,
    "appointment": SERVICE_BOOKING,
}


def normalize_service_code(raw: str | None) -> str | None:
    code = str(raw or "").strip().lower().replace("-", "_")
    if not code:
        return None
    return _SERVICE_ALIASES.get(code, code)
