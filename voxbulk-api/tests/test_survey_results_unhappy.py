"""Tests for unhappy respondent detection and negative feedback excerpts."""

from __future__ import annotations

import json

from app.models.service_order import ServiceOrderRecipient
from app.services.survey_results_service import (
    _collect_negative_feedback_excerpts,
    _is_unhappy_respondent,
    recipient_summary_row,
)


def _recipient(**result: dict) -> ServiceOrderRecipient:
    row = ServiceOrderRecipient(
        order_id="ord-1",
        row_number=1,
        name="Alex Morgan",
        phone="+447700900123",
        email="alex@example.com",
        status="completed",
    )
    row.id = "rec-1"
    row.result_json = json.dumps(result, ensure_ascii=False)
    return row


def test_unhappy_from_bad_answer():
    recipient = _recipient(
        wa_conversation={
            "answers": [
                {"question": "How was your visit?", "answer": "Bad", "step_role": "rating"},
            ]
        }
    )
    assert _is_unhappy_respondent(recipient) is True


def test_not_unhappy_from_good_answer():
    recipient = _recipient(
        wa_conversation={
            "answers": [
                {"question": "How was your visit?", "answer": "Good", "step_role": "rating"},
            ]
        }
    )
    assert _is_unhappy_respondent(recipient) is False


def test_recipient_summary_includes_contact_fields():
    recipient = _recipient(
        needs_follow_up=True,
        wa_conversation={"answers": [{"question": "Q", "answer": "Bad"}]},
    )
    row = recipient_summary_row(recipient, goal="Feedback", order_id="ord-1")
    assert row["phone"] == "+447700900123"
    assert row["email"] == "alex@example.com"
    assert row["is_unhappy"] is True
    assert row["needs_follow_up"] is True


def test_negative_feedback_excerpt_collection():
    recipient = _recipient(
        wa_conversation={
            "answers": [
                {"question": "How was your visit?", "answer": "Bad", "step_role": "rating"},
                {
                    "question": "Tell us more",
                    "answer": "Long wait time",
                    "step_role": "tell_us_more",
                    "reply_type": "long_text",
                },
            ]
        }
    )
    excerpts = _collect_negative_feedback_excerpts([recipient], order_id="ord-1")
    assert len(excerpts) >= 1
    assert excerpts[0]["source"] == "negative_feedback"
