"""Block assistant intents for dashboard modules the org has disabled."""

from __future__ import annotations

from app.schemas.assistant import AssistantChatOut
from app.services.assistant.highlights import build_out, nav_action

# Dashboard ServiceKey values (dashboard-web/src/lib/services.tsx).
_SERVICE_LABELS: dict[str, str] = {
    "surveys": "Surveys",
    "interviews": "Interviews",
    "feedback": "Customer feedback",
    "appointments": "Appointments",
    "recovery": "Recovery",
    "followup": "Follow up",
    "campaigns": "Campaigns",
}

# Intents that require a specific enabled module (everything else is always allowed).
_INTENT_SERVICE: dict[str, str] = {
    "survey_results": "surveys",
    "list_surveys": "surveys",
    "create_survey": "surveys",
    "create_template": "surveys",
    "survey_reports": "surveys",
    "interview_results": "interviews",
    "list_interviews": "interviews",
    "create_interview": "interviews",
    "interview_reports": "interviews",
    "feedback_overview": "feedback",
    "create_feedback": "feedback",
    "feedback_subscription": "feedback",
    "recovery_overview": "recovery",
    "followup_overview": "followup",
}

_SERVICE_CODE_MAP: dict[str, str] = {
    "survey": "surveys",
    "interview": "interviews",
    "feedback": "feedback",
}


def _enabled_set(enabled_services: list[str] | None) -> set[str]:
    if not enabled_services:
        return set(_SERVICE_LABELS.keys())
    return {str(s).strip().lower() for s in enabled_services if str(s).strip()}


def required_service_for_intent(intent: str, *, service_code: str | None = None) -> str | None:
    key = _INTENT_SERVICE.get(intent)
    if key:
        return key
    if intent == "launch_check" and service_code:
        return _SERVICE_CODE_MAP.get(str(service_code).strip().lower())
    if intent == "campaign_detail" and service_code:
        return _SERVICE_CODE_MAP.get(str(service_code).strip().lower())
    return None


def service_enabled(required: str | None, enabled_services: list[str] | None) -> bool:
    if not required:
        return True
    return required in _enabled_set(enabled_services)


def disabled_services_list(enabled_services: list[str] | None) -> list[str]:
    enabled = _enabled_set(enabled_services)
    return [key for key in _SERVICE_LABELS if key not in enabled]


def service_gate_refusal(
    *,
    intent: str,
    required_service: str,
    enabled_services: list[str] | None = None,
) -> AssistantChatOut:
    label = _SERVICE_LABELS.get(required_service, required_service.replace("_", " ").title())
    enabled = _enabled_set(enabled_services)
    hints: list[str] = []
    if enabled:
        hints.append("You can still ask about: " + ", ".join(_SERVICE_LABELS[k] for k in sorted(enabled) if k in _SERVICE_LABELS) + ".")
    return build_out(
        primary_message=(
            f"**{label}** isn't enabled on your account, so I can't help with that here. "
            "Only your account manager can add a module to your account. "
            "If you're an owner or manager, check **Settings → Services** to show modules you've already been granted."
            + (f" {hints[0]}" if hints else "")
        ),
        confidence=0.95,
        intent=intent,
        blocking_reason=f"service_disabled:{required_service}",
        next_actions=[
            nav_action("services", "Open Services settings", "/settings/services"),
            nav_action("support", "Contact support", "/account/support"),
        ],
        suggested_prompts=[
            "Show my billing",
            "What's my usage?",
            "Open support",
        ],
    )


def check_intent_service_gate(
    intent: str,
    *,
    enabled_services: list[str] | None,
    service_code: str | None = None,
) -> AssistantChatOut | None:
    required = required_service_for_intent(intent, service_code=service_code)
    if required and not service_enabled(required, enabled_services):
        return service_gate_refusal(intent=intent, required_service=required, enabled_services=enabled_services)
    return None
