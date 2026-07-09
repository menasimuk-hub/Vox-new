from __future__ import annotations

from app.services.interview_booking_service import (
    InterviewBookingService,
    _booking_invite_buttons,
    _buttons_from_components,
    _confirmation_buttons,
)
from app.services.sales_whatsapp_telnyx_service import build_telnyx_components
from app.services.telnyx_whatsapp_template_sync_service import full_body_preview


def test_full_body_preview_includes_header_and_body():
    components = [
        {"type": "HEADER", "text": "📅 Book your interview"},
        {"type": "BODY", "text": "Hi {{1}} 👋\n\nRole: {{2}} at {{3}}"},
        {"type": "FOOTER", "text": "Unique link · VOXBULK"},
        {
            "type": "BUTTONS",
            "buttons": [{"type": "URL", "text": "📅 Book My Interview", "url": "https://example.com/{{1}}"}],
        },
    ]
    preview = full_body_preview(components)
    assert preview is not None
    assert "📅 Book your interview" in preview
    assert "Hi {{1}} 👋" in preview
    assert "Unique link · VOXBULK" in preview


def test_buttons_from_components_reads_emoji_labels():
    components = [
        {
            "type": "BUTTONS",
            "buttons": [
                {"type": "URL", "text": "📅 Book My Interview"},
                {"type": "QUICK_REPLY", "text": "🛑 Stop"},
            ],
        }
    ]
    buttons = _buttons_from_components(components)
    assert len(buttons) == 2
    assert buttons[0]["label"].startswith("📅")
    assert buttons[1]["label"].startswith("🛑")


def test_booking_invite_buttons_default_three_actions():
    buttons = _booking_invite_buttons([])
    labels = " ".join(b["label"] for b in buttons)
    assert "Book My Interview" in labels
    assert "Reschedule" in labels
    assert "Cancel" in labels


def test_confirmation_buttons_default_two_actions():
    buttons = _confirmation_buttons([])
    labels = " ".join(b["label"] for b in buttons)
    assert "Reschedule" in labels
    assert "Cancel" in labels
    assert "Book" not in labels


def test_render_body_preview_substitutes_booking_variables():
    body = InterviewBookingService._render_body_preview(
        "Hi {{1}} — {{2}} at {{3}}",
        candidate_name="Alex Demo",
        role="Engineer",
        company_name="Acme Dental",
    )
    assert "Alex" in body
    assert "Engineer" in body
    assert "Acme Dental" in body


def test_render_body_preview_substitutes_confirmation_variables():
    body = InterviewBookingService._render_body_preview(
        "Hi {{1}}, {{2}} on {{3}} at {{4}}",
        candidate_name="Alex Demo",
        role="Engineer",
        interview_date="Mon 1 Jun 2026",
        interview_time="2:30 PM",
    )
    assert "Alex" in body
    assert "Engineer" in body
    assert "Mon 1 Jun 2026" in body
    assert "2:30 PM" in body


def test_build_telnyx_components_interview_booking():
    parts = build_telnyx_components(
        "interview_booking_invite",
        {
            "first_name": "Alex",
            "role": "Hygienist",
            "company_name": "Northwell Dental",
            "booking_token": "abc123",
        },
    )
    assert parts[0]["type"] == "body"
    assert len(parts[0]["parameters"]) == 3
    assert parts[0]["parameters"][0]["text"] == "Alex"
    assert parts[0]["parameters"][1]["text"] == "Hygienist"
    assert parts[0]["parameters"][2]["text"] == "Northwell Dental"


def test_build_telnyx_components_interview_confirm():
    parts = build_telnyx_components(
        "interview_booking_confirm",
        {
            "first_name": "Alex",
            "role": "Hygienist",
            "interview_date": "Sat 14 Jun 2026",
            "interview_time": "10:00 AM",
        },
    )
    assert len(parts[0]["parameters"]) == 4


def test_fallback_preview_email_first_notice():
    preview = InterviewBookingService._fallback_preview(
        role="Senior Engineer",
        company_name="VoxBulk",
        sync_result=None,
        sync_error="sync failed",
    )
    assert preview["is_fallback"] is True
    assert preview["name"] == "voxbulk_interview_email_sent_v2"
    assert preview["invite_mode"] == "email_first"
    assert "careers@voxbulk.com" in preview["rendered_body"]
    assert preview["buttons"] == []
    assert preview["confirmation_template_name"] == "interview_confirm_book_v4"
    assert preview["confirmation_body"]
    assert len(preview["confirmation_buttons"]) == 2
    assert preview["sync_error"] == "sync failed"


def test_interview_booking_locked_after_completion():
    import json

    from app.models.service_order import ServiceOrderRecipient
    from app.services.interview_booking_service import interview_booking_locked

    recipient = ServiceOrderRecipient(name="Done Candidate")
    recipient.status = "completed"
    assert interview_booking_locked(recipient) is not None

    recipient.status = "pending"
    recipient.result_json = json.dumps({"analysis_saved_at": "2026-05-01T12:00:00"})
    assert interview_booking_locked(recipient) is not None

    recipient.result_json = json.dumps({"booked_start_at": "2026-05-01T10:00:00"})
    assert interview_booking_locked(recipient) is None
