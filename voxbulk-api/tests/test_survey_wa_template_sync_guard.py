"""Tests for WA template sync guards, batching, and clone-push."""

from __future__ import annotations

import json

import pytest
from sqlalchemy.orm import Session

from app.core.database import get_sessionmaker
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.survey_wa_template_fix_sync_service import fix_and_sync_survey_template
from app.services.survey_wa_template_guard_service import should_skip_utility_rewrite
from app.services.wa_template_closeout_service import WaTemplateCloseoutService
from app.services.wa_template_push_batch_service import run_batched_push


@pytest.fixture()
def db_session() -> Session:
    SessionLocal = get_sessionmaker()
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_repair_all_survey_content_disabled(db_session):
    result = WaTemplateCloseoutService.repair_all_survey_content(db_session, force_rejected=True)
    assert result["repaired"] == 0
    assert result.get("skipped") == "content_repair_disabled"


def test_regenerate_all_feedback_disabled(db_session):
    result = WaTemplateCloseoutService.regenerate_all_feedback_templates(db_session)
    assert result["regenerated"] == 0
    assert result.get("skipped") == "content_repair_disabled"


def test_run_batched_push_respects_limit_and_has_more():
    items = list(range(12))

    def push_one(item: int) -> dict:
        return {"ok": True, "value": item}

    first = run_batched_push(items, offset=0, limit=5, push_one=push_one, item_label=str)
    assert first["pushed"] == 5
    assert first["has_more"] is True
    assert first["next_offset"] == 5

    third = run_batched_push(items, offset=10, limit=5, push_one=push_one, item_label=str)
    assert third["pushed"] == 2
    assert third["has_more"] is False


def test_should_skip_utility_rewrite_for_welcome_step_role(db_session):
    row = TelnyxWhatsappTemplate(
        telnyx_record_id="local-test",
        template_id="local-test",
        name="voxbulk_survey_welcome_templates_standard",
        language="en_GB",
        status="APPROVED",
        step_role="welcome",
        draft_components_json=json.dumps([{"type": "BODY", "text": "Hi"}]),
    )
    db_session.add(row)
    db_session.commit()
    assert should_skip_utility_rewrite(db_session, row) is True


def test_fix_and_sync_skips_utility_rewrite_by_default(db_session, monkeypatch):
    row = TelnyxWhatsappTemplate(
        telnyx_record_id="local-test2",
        template_id="local-test2",
        name="voxbulk_survey_general_q1",
        language="en_GB",
        status="LOCAL_DRAFT",
        category="UTILITY",
        draft_components_json=json.dumps(
            [
                {"type": "BODY", "text": "How was your visit?"},
                {
                    "type": "BUTTONS",
                    "buttons": [{"type": "QUICK_REPLY", "text": "Good"}],
                },
            ]
        ),
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)

    rewrite_called = {"value": False}

    def fake_rewrite(*args, **kwargs):
        rewrite_called["value"] = True

    monkeypatch.setattr(
        "app.services.survey_wa_template_fix_sync_service.apply_utility_rewrite_to_row",
        fake_rewrite,
    )
    monkeypatch.setattr(
        "app.services.survey_wa_template_fix_sync_service.SurveyWhatsappTemplateService.push_to_telnyx",
        lambda *a, **k: {"ok": True, "message": "pushed"},
    )

    result = fix_and_sync_survey_template(db_session, row)
    assert result["ok"] is True
    assert rewrite_called["value"] is False
    assert "utility_rewrite" not in (result.get("steps") or [])
