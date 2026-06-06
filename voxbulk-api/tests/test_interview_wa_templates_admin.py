"""Admin WA Interview template library."""

from __future__ import annotations

import pytest

from app.core.database import get_sessionmaker
from app.services.interview_whatsapp_template_service import InterviewWhatsappTemplateService


@pytest.fixture
def db():
    Session = get_sessionmaker()
    session = Session()
    try:
        yield session
    finally:
        session.close()


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
