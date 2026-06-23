"""Marketing-category WA templates are disabled platform-wide (billing / Meta category)."""

from __future__ import annotations

from typing import Any

# When True, marketing opt-in steps and marketing-category templates are excluded everywhere.
MARKETING_WA_TEMPLATES_DISABLED = True


def marketing_wa_enabled() -> bool:
    return not MARKETING_WA_TEMPLATES_DISABLED


def is_marketing_wa_template(row: Any) -> bool:
    cat = str(getattr(row, "meta_category", None) or "").strip().lower()
    key = str(getattr(row, "template_key", None) or "").strip().lower()
    step_role = str(getattr(row, "step_role", None) or "").strip().lower()
    return cat == "marketing" or key == "marketing_opt_in" or step_role == "marketing_opt_in"


def is_marketing_survey_step(step: dict[str, Any]) -> bool:
    kind = str(step.get("kind") or "").strip().lower()
    key = str(step.get("template_key") or "").strip().lower()
    return kind == "marketing_opt_in" or key == "marketing_opt_in"


def filter_survey_steps(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if marketing_wa_enabled():
        return steps
    return [step for step in steps if not is_marketing_survey_step(step)]


def effective_marketing_opt_in_enabled(flag: bool | None) -> bool:
    if not marketing_wa_enabled():
        return False
    return bool(flag)
