"""Platform service keys for per-organisation agent assignment."""

from __future__ import annotations

# Fixed catalogue (extend with migration if new keys need DB enforcement)
SERVICE_FRONTPAGE_TALK_TO_US = "frontpage_talk_to_us"
SERVICE_OUTBOUND_VOICE = "outbound_voice"
SERVICE_ORG_DEFAULT = "org_default"
SERVICE_SURVEY = "survey"
SERVICE_INTERVIEW = "interview"
SERVICE_LEAD_SALES = "lead_sales"
SERVICE_APPOINTMENTS = "appointments"

AGENT_SERVICE_KEYS: tuple[str, ...] = (
    SERVICE_FRONTPAGE_TALK_TO_US,
    SERVICE_OUTBOUND_VOICE,
    SERVICE_ORG_DEFAULT,
    SERVICE_SURVEY,
    SERVICE_INTERVIEW,
    SERVICE_LEAD_SALES,
    SERVICE_APPOINTMENTS,
)

AGENT_SERVICE_LABELS: dict[str, str] = {
    SERVICE_FRONTPAGE_TALK_TO_US: "Web agent (Talk to us / lead capture)",
    SERVICE_OUTBOUND_VOICE: "Outbound voice",
    SERVICE_ORG_DEFAULT: "Organisation default voice",
    SERVICE_SURVEY: "Survey AI calls",
    SERVICE_INTERVIEW: "Interview AI calls",
    SERVICE_LEAD_SALES: "Lead / Sales AI calls",
    SERVICE_APPOINTMENTS: "Appointment confirmation AI calls",
}


def normalize_service_key(raw: str) -> str:
    key = str(raw or "").strip().lower().replace("-", "_")
    if key not in AGENT_SERVICE_KEYS:
        raise ValueError(f"Unknown service key. Allowed: {', '.join(AGENT_SERVICE_KEYS)}")
    return key
