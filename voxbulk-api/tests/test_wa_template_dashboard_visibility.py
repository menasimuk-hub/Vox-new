"""Session-text templates must stay visible on the dashboard without Meta APPROVED."""

from __future__ import annotations

from types import SimpleNamespace

from app.services.wa_template_dashboard_visibility_service import platform_template_blocks_dashboard


def test_pending_thank_you_not_blocked_for_dashboard():
    row = SimpleNamespace(
        category="UTILITY",
        status="PENDING",
        step_role="completion",
        name="was_system_thank_you_001_en",
        display_name="Thank you",
        template_id=None,
        draft_components_json=None,
        components_json='[{"type":"BODY","text":"Thanks"}]',
    )
    assert platform_template_blocks_dashboard(row) is False


def test_pending_buttoned_welcome_still_blocked():
    row = SimpleNamespace(
        category="UTILITY",
        status="PENDING",
        step_role="start",
        name="was_system_welcome_001_en",
        display_name="Welcome",
        template_id=None,
        draft_components_json=None,
        components_json=(
            '[{"type":"BODY","text":"Hi"},'
            '{"type":"BUTTONS","buttons":[{"type":"QUICK_REPLY","text":"Start survey"}]}]'
        ),
    )
    assert platform_template_blocks_dashboard(row) is True
