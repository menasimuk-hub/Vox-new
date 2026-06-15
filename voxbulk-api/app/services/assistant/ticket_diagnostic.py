"""Plain-text assistant diagnostics for support tickets — never JSON in customer-visible bodies."""

from __future__ import annotations

import re
from typing import Any


def _line(label: str, value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return f"{label}: {text}"


def _format_history(recent_history: list[Any]) -> list[str]:
    lines: list[str] = []
    for item in recent_history or []:
        if isinstance(item, dict):
            role = str(item.get("role") or "user").strip().capitalize()
            text = str(item.get("text") or "").strip()
        else:
            role = str(getattr(item, "role", "user") or "user").strip().capitalize()
            text = str(getattr(item, "text", "") or "").strip()
        if text:
            lines.append(f"  - {role}: {text}")
    return lines


def format_assistant_diagnostic_plain_text(diagnostic: dict[str, Any]) -> str:
    """Admin-only note: readable prose, no JSON blocks."""
    if not diagnostic:
        return ""

    lines: list[str] = ["Assistant diagnostic (internal — not shown to customer)"]
    for key, label in (
        ("user_message", "Customer request"),
        ("intent", "Classified intent"),
        ("category", "Suggested category"),
        ("current_route", "Dashboard page"),
        ("org_name", "Organisation"),
        ("org_id", "Organisation ID"),
        ("user_email", "User email"),
        ("user_id", "User ID"),
        ("timestamp", "Submitted at"),
    ):
        row = _line(label, diagnostic.get(key))
        if row:
            lines.append(row)

    history = diagnostic.get("recent_history")
    if not history and isinstance(diagnostic.get("context"), dict):
        history = diagnostic["context"].get("recent_history")
    history_lines = _format_history(history if isinstance(history, list) else [])
    if history_lines:
        lines.append("Recent chat:")
        lines.extend(history_lines)

    enabled = None
    ctx = diagnostic.get("context")
    if isinstance(ctx, dict):
        enabled = ctx.get("enabled_services")
    if isinstance(enabled, list) and enabled:
        lines.append(f"Enabled modules: {', '.join(str(s) for s in enabled)}")

    return "\n".join(lines).strip()


def compose_customer_ticket_message(*, user_message: str, diagnostic: dict[str, Any] | None = None) -> str:
    """Customer-visible ticket body — never includes raw diagnostic JSON or code blocks."""
    text = str(user_message or "").strip()
    if text and not _looks_like_meta_only_request(text):
        return text
    return _default_customer_request_text(text, diagnostic or {})


def derive_ticket_fields(message: str) -> tuple[str, str, str]:
    """Return subject, customer-visible message, and category."""
    text = (message or "").strip()
    category = "technical"
    if re.search(r"\b(invoice|bill|payment|refund)\b", text, re.I):
        category = "invoices"
    elif re.search(r"\b(upgrade|pricing|plan|package|subscription|sales|demo)\b", text, re.I):
        category = "pre-sale"

    wants_ticket = bool(re.search(r"\b(tickt|ticket|tcket|tikcet)\b", text, re.I))
    wants_upgrade = bool(re.search(r"\b(upgrade|package|plan|pricing)\b", text, re.I))

    if wants_ticket and wants_upgrade:
        return (
            "Package upgrade request",
            "I would like to upgrade my package. Please contact me with available options.",
            "pre-sale",
        )

    if wants_ticket and _looks_like_meta_only_request(text):
        return (
            "Support request",
            "I need help from the support team. Please review my account and follow up.",
            category,
        )

    subject = text[:200] if len(text) <= 200 else text[:197] + "..."
    customer_message = compose_customer_ticket_message(user_message=text)
    return subject, customer_message, category


def _looks_like_meta_only_request(text: str) -> bool:
    lowered = text.lower()
    if re.search(r"\b(open|create|raise|submit)\b.*\b(tickt|ticket|tcket|tikcet)\b", lowered):
        stripped = re.sub(
            r"\b(please|can you|could you|for me|open|create|raise|submit|a|an|the|support|ticket|tickt|tcket|tikcet)\b",
            " ",
            lowered,
        )
        return len(stripped.strip()) < 12
    return False


def _default_customer_request_text(raw_message: str, diagnostic: dict[str, Any]) -> str:
    raw = str(raw_message or "").strip()
    if re.search(r"\b(upgrade|package|plan|pricing)\b", raw, re.I):
        return "I would like to upgrade my package. Please contact me with available options."
    if raw:
        return raw
    return "Support request submitted via the dashboard assistant."
