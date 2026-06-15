from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class IntentMatch:
    intent: str
    confidence: float
    service_code: str | None = None
    params: dict[str, Any] = field(default_factory=dict)


# (priority, intent, confidence, pattern, service_code)
# Higher priority = explicit user task beats ambient billing keywords.
_RULES: list[tuple[int, str, float, re.Pattern[str], str | None]] = [
    # --- Task intents (priority 10) ---
    (
        10,
        "create_template",
        0.94,
        re.compile(
            r"\b(create|make|build|design|new|customi[sz]e|set up|add)\b.*\b(custom\s+)?template\b"
            r"|\bcustom\s+template\b"
            r"|\b(wa|whatsapp)\s+template\b"
            r"|\btemplate\s+(for|on)\b.*\b(survey|whatsapp|wa)\b",
            re.I,
        ),
        "survey",
    ),
    (
        10,
        "create_ticket",
        0.91,
        re.compile(
            r"\b(create|open|raise|submit)\b.*\b(support\s+)?ticket\b"
            r"|\b(problem|issue|broken|not working|support ticket|open ticket|complaint)\b",
            re.I,
        ),
        None,
    ),
    (
        10,
        "launch_check",
        0.9,
        re.compile(r"\b(can i launch|launch|ready to (start|launch)|start campaign)\b", re.I),
        None,
    ),
    (
        10,
        "survey_results",
        0.88,
        re.compile(
            r"\b(show|view|see|my)\b.*\b(survey).*\b(result|response|nps|completion|report)s?\b"
            r"|\b(survey).*(result|response|nps|completion|report)\b"
            r"|\b(nps|responses)\b",
            re.I,
        ),
        "survey",
    ),
    (
        10,
        "interview_results",
        0.88,
        re.compile(r"\b(interview).*(result|candidate|shortlist|report)\b", re.I),
        "interview",
    ),
    (
        10,
        "create_survey",
        0.86,
        re.compile(r"\b(create|new|start|set up)\b.*\b(survey|campaign)\b", re.I),
        "survey",
    ),
    (
        10,
        "create_feedback",
        0.86,
        re.compile(r"\b(create|new|add)\b.*\b(feedback|location|qr)\b", re.I),
        "customer_feedback",
    ),
    (
        10,
        "feedback_overview",
        0.87,
        re.compile(r"\b(feedback|qr|location).*\b(result|scan|location)\b|\bcustomer feedback\b", re.I),
        "customer_feedback",
    ),
    (
        10,
        "product_compare",
        0.95,
        re.compile(r"\b(survey).*(feedback|qr)\b|\b(difference|compare|vs)\b.*\b(survey|feedback|interview)\b", re.I),
        None,
    ),
    (
        10,
        "list_surveys",
        0.8,
        re.compile(r"\b(my|list|show)\b.*\b(survey|campaign)s?\b", re.I),
        "survey",
    ),
    (
        10,
        "list_interviews",
        0.8,
        re.compile(r"\b(my|list|show)\b.*\b(interview)s?\b", re.I),
        "interview",
    ),
    # --- Billing intents (priority 5 — only when the user asks about billing) ---
    (
        5,
        "wallet_low",
        0.92,
        re.compile(r"(wallet|balance).*(low|empty|gone|depleted)|why.*(low|spent|deduct)", re.I),
        None,
    ),
    (
        5,
        "billing_overview",
        0.88,
        re.compile(r"\b(billing|invoice|subscription|mandate|payment|owe|outstanding)\b", re.I),
        None,
    ),
    (
        5,
        "usage_summary",
        0.86,
        re.compile(r"\b(usage|quota|remaining|included|allowance|minutes left|recipients left)\b", re.I),
        None,
    ),
    # --- Admin intents (priority 8) ---
    (8, "admin_tickets", 0.85, re.compile(r"\b(admin|support).*\b(ticket|inbox|queue)\b", re.I), None),
    (8, "admin_invoices", 0.85, re.compile(r"\b(admin|failed).*\b(invoice|payment)\b", re.I), None),
    (8, "admin_subscriptions", 0.85, re.compile(r"\b(admin).*\b(subscription|mandate|mrr)\b", re.I), None),
]


def classify_intent(message: str, *, is_admin: bool = False) -> IntentMatch:
    text = (message or "").strip()
    if not text:
        return IntentMatch("unknown", 0.0)

    candidates: list[tuple[int, float, str, str | None]] = []
    for priority, intent, base_conf, pattern, service_code in _RULES:
        if intent.startswith("admin_") and not is_admin:
            continue
        if pattern.search(text):
            candidates.append((priority, base_conf, intent, service_code))

    if candidates:
        priority, conf, intent, service_code = max(candidates, key=lambda row: (row[0], row[1]))
        return IntentMatch(intent=intent, confidence=conf, service_code=service_code)

    if is_admin:
        return IntentMatch("admin_general", 0.5)
    return IntentMatch("general_help", 0.45)
