"""Build helpful policy-refusal responses with suggested rephrases and navigation."""

from __future__ import annotations

from app.schemas.assistant import AssistantChatOut, AssistantUiCommand
from app.services.assistant.highlights import build_out, nav_action


def build_policy_refusal_response(*, reason: str, suggested_prompts: list[str], nav_route: str | None) -> AssistantChatOut:
    prompts = [p for p in suggested_prompts if str(p).strip()]
    prompt_block = ""
    if prompts:
        prompt_block = " You can ask me instead: " + "; ".join(f'"{p}"' for p in prompts[:3]) + "."

    ui_commands: list[AssistantUiCommand] = []
    next_actions = []
    if nav_route:
        label = "Open the right page"
        if "billing" in nav_route:
            label = "Open billing"
        elif "integrations" in nav_route:
            label = "Open integrations"
        elif "support" in nav_route:
            label = "Open support"
        ui_commands.append(AssistantUiCommand(id="policy_nav", kind="navigate", route=nav_route, label=label))
        next_actions.append(nav_action("policy_nav", label, nav_route))

    return build_out(
        primary_message=f"{reason}{prompt_block}",
        confidence=1.0,
        intent="policy_refused",
        policy_refused=True,
        blocking_reason=reason,
        next_actions=next_actions,
        ui_commands=ui_commands,
        suggested_prompts=prompts,
    )
