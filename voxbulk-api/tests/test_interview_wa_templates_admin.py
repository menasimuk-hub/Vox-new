"""Admin WA Interview template library."""

from __future__ import annotations

import re

import pytest

from app.core.database import get_sessionmaker
from app.data.interview_booking_whatsapp_defaults import INTERVIEW_EMAIL_SENT_BODY
from app.services.interview_whatsapp_template_service import InterviewWhatsappTemplateService
from app.services.survey_whatsapp_template_service import validate_meta_variable_order


@pytest.fixture
def db():
    Session = get_sessionmaker()
    session = Session()
    try:
        yield session
    finally:
        session.close()


def test_interview_email_sent_body_variables_are_sequential_in_text():
    var_ids = [int(m.group(1)) for m in re.finditer(r"\{\{(\d+)\}\}", INTERVIEW_EMAIL_SENT_BODY)]
    assert var_ids == [1, 2, 3, 4]


def test_validate_meta_variable_order_rejects_out_of_order_body():
    components = [
        {
            "type": "BODY",
            "text": "Dear {{1}}, email from {{4}} about {{2}} at {{3}}",
            "example": {"body_text": [["James", "accountant", "menasim", "careers@voxbulk.com"]]},
        }
    ]
    err = validate_meta_variable_order(components)
    assert err is not None
    assert "ascending order" in err.lower()


def test_interview_template_catalog_seeds_four_templates(db):
    rows = InterviewWhatsappTemplateService.ensure_catalog_seeded(db)
    assert len(rows) == 4
    listed = InterviewWhatsappTemplateService.list_templates(db)
    assert len(listed) == 4
    keys = {item["sales_template_key"] for item in listed}
    assert keys == {
        "interview_email_sent",
        "interview_booking_confirm",
        "interview_booking_cancel",
        "interview_job_closed",
    }


def test_interview_template_hide_and_unhide(db):
    InterviewWhatsappTemplateService.ensure_catalog_seeded(db)
    listed = InterviewWhatsappTemplateService.list_templates(db)
    row_id = listed[0]["id"]
    row = InterviewWhatsappTemplateService.get_template(db, row_id)
    assert row is not None

    InterviewWhatsappTemplateService.save_draft(db, row, {"active_for_interview": False})
    hidden = InterviewWhatsappTemplateService.get_template_detail(db, row_id)
    assert hidden is not None
    assert hidden["active_for_interview"] is False

    row = InterviewWhatsappTemplateService.get_template(db, row_id)
    assert row is not None
    InterviewWhatsappTemplateService.save_draft(db, row, {"active_for_interview": True})
    visible = InterviewWhatsappTemplateService.get_template_detail(db, row_id)
    assert visible is not None
    assert visible["active_for_interview"] is True


def test_admin_wa_interview_list_api(app_client):
    from tests.test_agent_architecture import _headers

    headers, _org_id, _category_id = _headers(app_client)
    res = app_client.get("/admin/wa-interview/templates", headers=headers)
    assert res.status_code == 200
    body = res.json()
    assert body.get("ok") is True
    assert len(body.get("templates") or []) == 4
