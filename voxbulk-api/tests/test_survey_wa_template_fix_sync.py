"""Tests for single-template Fix & Sync service."""

from __future__ import annotations

from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.survey_wa_template_fix_sync_service import (
    repair_template_draft_row,
    sync_survey_template_from_sibling_meta_owner,
)


def test_repair_template_draft_row_normalizes_invalid_body_example():
    row = TelnyxWhatsappTemplate(
        name="voxbulk_survey_test_abc_123456",
        draft_components_json='[{"type":"BODY","text":"Hello","example":{"body_text":[[]]}}]',
    )
    assert repair_template_draft_row(row) is True
    assert "[[]]" not in str(row.draft_components_json)


def test_sync_from_sibling_meta_owner():
    owner = TelnyxWhatsappTemplate(
        id=100,
        name="voxbulk_survey_shared_standard",
        telnyx_record_id="meta-owner-1",
        status="APPROVED",
        category="UTILITY",
        components_json='[{"type":"BODY","text":"Owner body"}]',
        body_preview="Owner body",
    )
    sibling = TelnyxWhatsappTemplate(
        id=101,
        name="voxbulk_survey_shared_standard",
        telnyx_record_id="local-abc",
        status="APPROVED",
        category="MARKETING",
    )

    class _FakeResult:
        def scalar_one_or_none(self):
            return owner

    class _FakeDb:
        def execute(self, _stmt):
            return _FakeResult()

        def add(self, _row):
            return None

        def commit(self):
            return None

        def refresh(self, row):
            return None

    matched = sync_survey_template_from_sibling_meta_owner(_FakeDb(), sibling)
    assert matched is owner
    assert sibling.status == "APPROVED"
    assert sibling.category == "UTILITY"
    assert sibling.last_push_error is None
