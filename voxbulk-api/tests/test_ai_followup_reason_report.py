"""Tests for AI follow-up reason report builder."""

from __future__ import annotations

from app.services.ai_followup_report_service import (
    build_followup_reason_report,
    describe_call_findings,
    extract_customer_lines_from_transcript,
    extract_wa_written_feedback,
)


def test_extract_wa_written_feedback_skips_ratings():
    answers = [
        {"question": "Work quality", "answer": "Below standard"},
        {"step_role": "tell_us_more", "question": "Tell us more", "answer_text": "Took too long"},
    ]
    written = extract_wa_written_feedback(answers)
    assert len(written) == 1
    assert written[0]["text"] == "Took too long"


def test_build_reason_report_no_survey_reason_completed_short_call():
    report = build_followup_reason_report(
        session_summary={
            "poor_answers": [{"question": "Work quality", "answer": "Below standard"}],
            "written_feedback": [],
        },
        outcome={"duration_seconds": 0, "hangup_cause": "normal_clearing"},
        status="completed",
    )
    assert "Below standard" in report["narrative"]
    assert "did not explain why" in report["narrative"].lower()
    assert report["call_findings"]
    assert "almost immediately" in report["call_findings"].lower()


def test_extract_customer_lines_from_transcript():
    text = "Assistant: Hello\nUser: The MOT took forever and staff were rude"
    assert "MOT took forever" in (extract_customer_lines_from_transcript(text) or "")


def test_describe_call_findings_from_transcript():
    msg = describe_call_findings(
        transcript="User: Waiting area was dirty",
        transcript_excerpt=None,
        duration_seconds=45,
        status="completed",
    )
    assert msg == "Waiting area was dirty"
