"""JSON session state for Customer Feedback WA/web tell-us-more flows."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from app.services.survey_wa_flow_constants import OPEN_TEXT_TIMEOUT_SEC

KEY_TUM_PENDING = "tell_us_more_pending"
KEY_TUM_DEADLINE = "tell_us_more_deadline"
KEY_TUM_STEP_INDEX = "tell_us_more_step_index"
KEY_TUM_TOPIC_KEY = "tell_us_more_topic_key"
KEY_TUM_SURVEY_TYPE_ID = "tell_us_more_survey_type_id"


def load_feedback_session_state(session) -> dict[str, Any]:
    raw = str(getattr(session, "session_state_json", None) or "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def save_feedback_session_state(session, state: dict[str, Any]) -> None:
    session.session_state_json = json.dumps(state) if state else None


def is_tell_us_more_pending(state: dict[str, Any]) -> bool:
    return bool(state.get(KEY_TUM_PENDING))


def set_tell_us_more_pending(
    state: dict[str, Any],
    *,
    step_index: int,
    topic_key: str,
    survey_type_id: str,
) -> None:
    now = datetime.now(timezone.utc)
    deadline = now + timedelta(seconds=OPEN_TEXT_TIMEOUT_SEC)
    state[KEY_TUM_PENDING] = True
    state[KEY_TUM_STEP_INDEX] = int(step_index)
    state[KEY_TUM_TOPIC_KEY] = str(topic_key or "")
    state[KEY_TUM_SURVEY_TYPE_ID] = str(survey_type_id or "")
    state[KEY_TUM_DEADLINE] = deadline.isoformat()


def clear_tell_us_more_pending(state: dict[str, Any]) -> None:
    for key in (
        KEY_TUM_PENDING,
        KEY_TUM_DEADLINE,
        KEY_TUM_STEP_INDEX,
        KEY_TUM_TOPIC_KEY,
        KEY_TUM_SURVEY_TYPE_ID,
    ):
        state.pop(key, None)


def parse_deadline(state: dict[str, Any]) -> datetime | None:
    raw = state.get(KEY_TUM_DEADLINE)
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (TypeError, ValueError):
        return None
