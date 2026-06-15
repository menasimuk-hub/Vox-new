from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    reason: str | None = None
    suggested_prompts: tuple[str, ...] = field(default_factory=tuple)
    nav_route: str | None = None


_BLOCKED_PATTERNS: list[tuple[re.Pattern[str], str, tuple[str, ...], str | None]] = [
    (
        re.compile(r"\b(hard[- ]?delete|purge|wipe)\b.*\b(user|candidate|customer|org)\b", re.I),
        "Hard deletion of user or candidate data is not permitted.",
        ("List my support tickets", "Show my billing"),
        "/account/support/tickets",
    ),
    (
        re.compile(r"\b(refund|chargeback)\b.*\b(without|bypass|skip)\b", re.I),
        "Refunds must go through the official billing review process.",
        ("Show my billing", "Open a support ticket about a refund"),
        "/account/billing",
    ),
    (
        re.compile(r"\b(change|modify|edit)\b.*\b(whatsapp|wa)\b.*\b(template|meta)\b", re.I),
        "Meta-approved WhatsApp template content cannot be changed via the assistant. Edit templates in the survey wizard.",
        ("Create a custom WhatsApp template", "Show my surveys"),
        "/surveys/new?channel=whatsapp",
    ),
    (
        re.compile(r"\b(webhook|gocardless|telnyx)\b.*\b(modify|change|disable)\b|\b(modify|change|disable)\b.*\b(webhook|gocardless|telnyx)\b", re.I),
        "Payment and telephony integrations cannot be modified via the assistant.",
        ("Open integrations settings", "Show my billing"),
        "/settings/integrations",
    ),
    (
        re.compile(r"\b(api[- ]?key|secret|password|token)\b", re.I),
        "Secrets and credentials cannot be shared or modified via the assistant.",
        ("Open integrations settings", "Open profile settings"),
        "/settings/integrations",
    ),
    (
        re.compile(r"\b(skip|bypass|hide)\b.*\b(gdpr|disclosure|consent)\b", re.I),
        "GDPR and AI disclosure requirements cannot be bypassed.",
        ("Show my usage", "Open audit log"),
        "/settings/audit",
    ),
    (
        re.compile(
            r"\b(void|waive|forgive|skip)\b.*\b(invoice|billing|payment|mandate)\b|\b(modify|change|override)\b.*\b(billing|subscription|wallet)\b",
            re.I,
        ),
        "Billing changes must go through the official billing screens, not the assistant.",
        ("Show my billing", "What's my usage?", "Explain this invoice"),
        "/account/billing",
    ),
]


def check_policy(message: str, *, is_mutation: bool = False) -> PolicyDecision:
    text = (message or "").strip()
    if not text:
        return PolicyDecision(False, "Message is empty.", ("Show my billing", "What can you help with?"), "/")

    for pattern, reason, suggestions, nav_route in _BLOCKED_PATTERNS:
        if pattern.search(text):
            return PolicyDecision(False, reason, suggestions, nav_route)

    if is_mutation and re.search(r"\b(pay|charge|launch|start|delete|void)\b", text, re.I):
        return PolicyDecision(True)

    return PolicyDecision(True)
