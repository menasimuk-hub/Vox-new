"""Tests for feedback tell-us-more session state (no DB)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

from app.services.customer_feedback.feedback_wa_session_state import (
    is_tell_us_more_pending,
    load_feedback_session_state,
    set_tell_us_more_pending,
)


def test_feedback_tell_us_more_pending_state():
    session = MagicMock()
    session.session_state_json = None
    state = load_feedback_session_state(session)
    assert not is_tell_us_more_pending(state)
    set_tell_us_more_pending(state, step_index=0, topic_key="topic_a", survey_type_id="st1")
    assert is_tell_us_more_pending(state)
    assert state["tell_us_more_step_index"] == 0
    deadline = datetime.fromisoformat(state["tell_us_more_deadline"].replace("Z", "+00:00"))
    assert deadline > datetime.now(timezone.utc)
