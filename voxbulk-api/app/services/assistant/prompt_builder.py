"""Build LLM system prompts from the static assistant service registry."""

from __future__ import annotations

from app.services.assistant.service_registry import INTENT_REGISTRY, registry_intent_names


DASHBOARD_SECTIONS = """
Dashboard sections:
- Home (/)
- Surveys (/surveys) — AI call and WhatsApp campaigns
- Interviews (/interviews) — AI screening campaigns
- Feedback (/feedback) — QR customer feedback locations
- Account → Billing (/account/billing) — wallet, invoices, subscription
- Account → Usage (/account/usage) — plan allowance meters
- Account → Support (/account/support) — tickets and live help
- Settings (/settings/profile) — profile and team
"""


def build_classify_system_prompt() -> str:
    lines = [
        "You are the intent classifier for VoxBulk dashboard support.",
        "Pick exactly one intent from the allowed list and extract parameters.",
        "Never invent intents. Never choose HTTP endpoints — only intent names.",
        "If unsure, use general_help with low confidence.",
        "",
        "Allowed intents:",
    ]
    for name in registry_intent_names():
        spec = INTENT_REGISTRY[name]
        params = f" Params: {', '.join(spec.param_keys)}" if spec.param_keys else ""
        lines.append(f"- {name}: {spec.description}.{params}")
    lines.append(DASHBOARD_SECTIONS)
    return "\n".join(lines)


def build_synthesize_system_prompt() -> str:
    lines = [
        "You are a friendly VoxBulk customer support specialist.",
        "Write a clear, concise answer using ONLY the provided tool data.",
        "Never invent numbers, IDs, or account facts not present in the data.",
        "Never mention APIs, errors, stack traces, or internal systems.",
        "Also return ui_commands to help the user on the page (navigate, highlight, scroll_to).",
        "",
        "ui_commands kinds: navigate, highlight, scroll_to, open_panel",
        "highlight_type values: invoice, service_order, ticket, usage, wallet_transaction, survey_result, interview_result, feedback_location",
        DASHBOARD_SECTIONS,
    ]
    return "\n".join(lines)


def build_registry_catalog_for_prompt() -> str:
    rows: list[str] = []
    for name in registry_intent_names():
        spec = INTENT_REGISTRY[name]
        tool = spec.tool_name or "navigation only"
        rows.append(f"- {name} → {tool} ({spec.endpoint_label}) — {spec.dashboard_section}")
    return "Intent registry (runtime uses this mapping, not the model):\n" + "\n".join(rows)
