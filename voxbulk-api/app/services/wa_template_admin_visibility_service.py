"""Admin hide/show for WA templates — stays off until admin re-enables."""

from __future__ import annotations

import json
from typing import Any

ADMIN_HIDDEN_SURVEY_KEY = "admin_hidden_from_survey"


def _load_outcome_vars(row: Any) -> dict[str, Any]:
    raw = getattr(row, "outcome_variables_json", None)
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return dict(parsed) if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _save_outcome_vars(row: Any, data: dict[str, Any]) -> None:
    row.outcome_variables_json = json.dumps(data, ensure_ascii=False)


def is_admin_hidden_from_survey(row: Any) -> bool:
    if row is None:
        return False
    if bool(getattr(row, "admin_hidden_from_survey", False)):
        return True
    meta = _load_outcome_vars(row)
    return bool(meta.get(ADMIN_HIDDEN_SURVEY_KEY))


def apply_admin_survey_visibility(row: Any, *, visible: bool) -> None:
    """Admin toggle only — visible=False hides until admin sets visible=True."""
    if hasattr(row, "active_for_survey"):
        row.active_for_survey = bool(visible)
    if hasattr(row, "is_active"):
        row.is_active = bool(visible)
    if hasattr(row, "admin_hidden_from_survey"):
        row.admin_hidden_from_survey = not bool(visible)
    if hasattr(row, "outcome_variables_json"):
        meta = _load_outcome_vars(row)
        if visible:
            meta.pop(ADMIN_HIDDEN_SURVEY_KEY, None)
        else:
            meta[ADMIN_HIDDEN_SURVEY_KEY] = True
        _save_outcome_vars(row, meta)


def may_auto_enable_for_survey(row: Any) -> bool:
    """False when admin hid the topic — seed/sync/repair must not re-enable."""
    return not is_admin_hidden_from_survey(row)
