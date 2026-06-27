"""Marketing-category WA templates — gated by FEEDBACK_MARKETING_OPT_IN_ENABLED."""

from __future__ import annotations

from typing import Any

from app.core.config import get_settings


def marketing_wa_enabled() -> bool:
    return bool(get_settings().feedback_marketing_opt_in_enabled)


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
