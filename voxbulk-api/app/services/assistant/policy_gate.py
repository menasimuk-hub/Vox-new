from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    reason: str | None = None


_BLOCKED_PATTERNS = [
    (re.compile(r"\b(hard[- ]?delete|purge|wipe)\b.*\b(user|candidate|customer|org)\b", re.I), "Hard deletion of user or candidate data is not permitted."),
    (re.compile(r"\b(refund|chargeback)\b.*\b(without|bypass|skip)\b", re.I), "Refunds must go through the official billing review process."),
    (re.compile(r"\b(change|modify|edit)\b.*\b(whatsapp|wa)\b.*\b(template|meta)\b", re.I), "Meta-approved WhatsApp template content cannot be changed via the assistant."),
    (re.compile(r"\b(webhook|gocardless|telnyx)\b.*\b(modify|change|disable)\b|\b(modify|change|disable)\b.*\b(webhook|gocardless|telnyx)\b", re.I), "Payment and telephony integrations cannot be modified via the assistant."),
    (re.compile(r"\b(api[- ]?key|secret|password|token)\b", re.I), "Secrets and credentials cannot be shared or modified via the assistant."),
    (re.compile(r"\b(skip|bypass|hide)\b.*\b(gdpr|disclosure|consent)\b", re.I), "GDPR and AI disclosure requirements cannot be bypassed."),
]


def check_policy(message: str, *, is_mutation: bool = False) -> PolicyDecision:
    text = (message or "").strip()
    if not text:
        return PolicyDecision(False, "Message is empty.")

    for pattern, reason in _BLOCKED_PATTERNS:
        if pattern.search(text):
            return PolicyDecision(False, reason)

    if is_mutation and re.search(r"\b(pay|charge|launch|start|delete|void)\b", text, re.I):
        # Mutations always require explicit confirmation downstream.
        return PolicyDecision(True)

    return PolicyDecision(True)
