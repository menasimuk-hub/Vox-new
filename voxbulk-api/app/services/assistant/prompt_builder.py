"""Build LLM system prompts from the static assistant service registry and dashboard catalog."""

from __future__ import annotations

from app.services.assistant.dashboard_catalog import catalog_prompt_block
from app.services.assistant.service_gate import disabled_services_list
from app.services.assistant.service_registry import INTENT_REGISTRY, registry_intent_names


def build_classify_system_prompt(*, enabled_services: list[str] | None = None) -> str:
    lines = [
        "You are the intent classifier for VoxBulk dashboard support.",
        "Pick exactly one intent from the allowed list and extract parameters (order_id, invoice_id, ticket_id when mentioned).",
        "Never invent intents. If unsure, use general_help with low confidence.",
        "create_ticket is allowed when the user wants to open a support ticket.",
    ]
    disabled = disabled_services_list(enabled_services)
    if disabled:
        lines.append(
            "Do NOT classify into intents for disabled modules ("
            + ", ".join(disabled)
            + "). Use general_help and explain the module is not enabled on this account."
        )
    lines.extend(["", "Allowed intents:"])
    names = list(registry_intent_names())
    if "create_ticket" not in names:
        names.append("create_ticket")
    for name in sorted(set(names)):
        spec = INTENT_REGISTRY.get(name)
        if spec is None:
            if name == "create_ticket":
                lines.append("- create_ticket: User wants to open or create a support ticket.")
            continue
        params = f" Params: {', '.join(spec.param_keys)}" if spec.param_keys else ""
        lines.append(f"- {name}: {spec.description}.{params}")
    lines.append("")
    lines.append(catalog_prompt_block(enabled_services=enabled_services))
    return "\n".join(lines)


def build_synthesize_system_prompt(*, enabled_services: list[str] | None = None, has_kb_context: bool = False) -> str:
    lines = [
        "You are a friendly VoxBulk customer support specialist.",
        "Write a clear, concise answer using ONLY the provided tool data and Help Centre context.",
        "Never invent numbers, IDs, or account facts not present in the data.",
        "Never mention APIs, errors, stack traces, or internal systems.",
        "Return JSON with primary_message and ui_commands to help the user navigate (navigate, highlight, scroll_to).",
    ]
    if has_kb_context:
        lines.append(
            "Ground your answer in the Help Centre context. Answer the user's question directly in plain language "
            "(2–5 short paragraphs or a short numbered list). Do NOT paste article titles/snippets verbatim as the answer. "
            "If context is weak or irrelevant, say so briefly and suggest Support or the FAQ page."
        )
    disabled = disabled_services_list(enabled_services)
    if disabled:
        lines.append(
            "These modules are DISABLED on this account — do not guide the user into them: "
            + ", ".join(disabled)
            + ". Direct them to Settings → Services or support instead."
        )
    lines.extend(["", catalog_prompt_block(enabled_services=enabled_services)])
    return "\n".join(lines)


def build_general_help_system_prompt(*, enabled_services: list[str] | None = None) -> str:
    lines = [
        "You are a friendly VoxBulk dashboard assistant answering how-to / product questions.",
        "Use the Help Centre excerpts when provided. Answer the user's question directly — do not dump raw excerpts.",
        "You cannot change billing, launch campaigns, edit templates, or modify integrations from chat.",
        "Return JSON: {\"primary_message\": \"...\", \"ui_commands\": [{\"id\": \"...\", \"kind\": \"navigate\", \"route\": \"...\", \"label\": \"...\"}]}",
        "Include 1–3 ui_commands pointing to the most useful dashboard routes.",
        "",
        catalog_prompt_block(enabled_services=enabled_services),
    ]
    return "\n".join(lines)
