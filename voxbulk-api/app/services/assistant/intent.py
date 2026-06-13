from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class IntentMatch:
    intent: str
    confidence: float
    service_code: str | None = None


_RULES: list[tuple[str, float, re.Pattern[str], str | None]] = [
    ("wallet_low", 0.92, re.compile(r"(wallet|balance).*(low|empty|gone|depleted)|why.*(low|spent|deduct)", re.I), None),
    ("billing_overview", 0.88, re.compile(r"\b(billing|invoice|subscription|mandate|payment|owe|outstanding)\b", re.I), None),
    ("usage_summary", 0.86, re.compile(r"\b(usage|quota|remaining|included|allowance|minutes left|recipients left)\b", re.I), None),
    ("launch_check", 0.9, re.compile(r"\b(can i launch|launch|ready to (start|launch)|start campaign)\b", re.I), None),
    ("survey_results", 0.88, re.compile(r"\b(survey).*(result|response|nps|completion|report)\b|\b(nps|responses)\b", re.I), "survey"),
    ("interview_results", 0.88, re.compile(r"\b(interview).*(result|candidate|shortlist|report)\b", re.I), "interview"),
    ("feedback_overview", 0.87, re.compile(r"\b(feedback|qr|location).*\b(result|scan|location)\b|\bcustomer feedback\b", re.I), "customer_feedback"),
    ("create_ticket", 0.84, re.compile(r"\b(problem|issue|broken|not working|support ticket|open ticket|complaint)\b", re.I), None),
    ("create_survey", 0.82, re.compile(r"\b(create|new|start|set up).*\b(survey|campaign)\b", re.I), "survey"),
    ("create_feedback", 0.82, re.compile(r"\b(create|new|add).*\b(feedback|location|qr)\b", re.I), "customer_feedback"),
    ("product_compare", 0.95, re.compile(r"\b(survey).*(feedback|qr)\b|\b(difference|compare|vs)\b.*\b(survey|feedback|interview)\b", re.I), None),
    ("list_surveys", 0.8, re.compile(r"\b(my|list|show).*\b(survey|campaign)s?\b", re.I), "survey"),
    ("list_interviews", 0.8, re.compile(r"\b(my|list|show).*\b(interview)s?\b", re.I), "interview"),
    ("admin_tickets", 0.85, re.compile(r"\b(admin|support).*\b(ticket|inbox|queue)\b", re.I), None),
    ("admin_invoices", 0.85, re.compile(r"\b(admin|failed).*\b(invoice|payment)\b", re.I), None),
    ("admin_subscriptions", 0.85, re.compile(r"\b(admin).*\b(subscription|mandate|mrr)\b", re.I), None),
]


def classify_intent(message: str, *, is_admin: bool = False) -> IntentMatch:
    text = (message or "").strip()
    if not text:
        return IntentMatch("unknown", 0.0)

    best: IntentMatch | None = None
    for intent, base_conf, pattern, service_code in _RULES:
        if intent.startswith("admin_") and not is_admin:
            continue
        if pattern.search(text):
            conf = base_conf
            if best is None or conf > best.confidence:
                best = IntentMatch(intent=intent, confidence=conf, service_code=service_code)

    if best:
        return best

    if is_admin:
        return IntentMatch("admin_general", 0.5)
    return IntentMatch("general_help", 0.45)
