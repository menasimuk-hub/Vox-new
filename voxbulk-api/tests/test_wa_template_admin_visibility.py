"""Admin-hidden WA templates must not be auto re-enabled."""

from __future__ import annotations

from types import SimpleNamespace

from app.services.wa_template_admin_visibility_service import (
    apply_admin_survey_visibility,
    is_admin_hidden_from_survey,
    may_auto_enable_for_survey,
)


def test_apply_admin_visibility_locks_until_admin_clears():
    row = SimpleNamespace(
        active_for_survey=True,
        admin_hidden_from_survey=False,
        outcome_variables_json=None,
    )
    apply_admin_survey_visibility(row, visible=False)
    assert row.active_for_survey is False
    assert row.admin_hidden_from_survey is True
    assert is_admin_hidden_from_survey(row) is True
    assert may_auto_enable_for_survey(row) is False

    apply_admin_survey_visibility(row, visible=True)
    assert row.active_for_survey is True
    assert row.admin_hidden_from_survey is False
    assert may_auto_enable_for_survey(row) is True


def test_outcome_variables_fallback_for_legacy_rows():
    row = SimpleNamespace(
        active_for_survey=False,
        admin_hidden_from_survey=False,
        outcome_variables_json='{"admin_hidden_from_survey": true}',
    )
    assert is_admin_hidden_from_survey(row) is True
    assert may_auto_enable_for_survey(row) is False
