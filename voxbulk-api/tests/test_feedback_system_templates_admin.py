"""Tests for Customer Feedback system template admin API."""

from __future__ import annotations

from app.core.database import get_sessionmaker
from app.models.customer_feedback import FeedbackWaTemplate
from app.services.customer_feedback.feedback_system_template_service import FeedbackSystemTemplateService


def test_list_grouped_system_templates():
    db = get_sessionmaker()()
    try:
        row = FeedbackWaTemplate(
            id="sys-thank-you-test",
            template_key="thank_you",
            body_text="Thanks for your feedback.",
            language="en_GB",
            is_active=True,
            industry_id=None,
            survey_type_id=None,
        )
        db.add(row)
        db.commit()

        result = FeedbackSystemTemplateService.list_grouped_admin(db)
        assert result["ok"] is True
        thank = next(k for k in result["kinds"] if k["key"] == "thank_you")
        assert thank["count"] >= 1
        assert any(t["id"] == row.id for t in thank["templates"])
    finally:
        db.close()
