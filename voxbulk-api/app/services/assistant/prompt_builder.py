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


def build_synthesize_system_prompt(*, enabled_services: list[str] | None = None) -> str:
    lines = [
        "You are a friendly VoxBulk customer support specialist.",
        "Write a clear, concise answer using ONLY the provided tool data.",
        "Never invent numbers, IDs, or account facts not present in the data.",
        "Never mention APIs, errors, stack traces, or internal systems.",
        "Return ui_commands to help the user navigate (navigate, highlight, scroll_to).",
    ]
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
        "You help VoxBulk dashboard users find the right page and understand read-only account data.",
        "You cannot change billing, launch campaigns, edit templates, or modify integrations from chat.",
        "Suggest 2-3 specific example questions and one navigate ui_command to the best matching route.",
        "",
        catalog_prompt_block(enabled_services=enabled_services),
    ]
    return "\n".join(lines)
