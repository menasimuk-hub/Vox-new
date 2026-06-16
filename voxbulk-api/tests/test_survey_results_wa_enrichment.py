"""WA survey results payload — voice metadata, sentiment breakdown, NPS."""

from __future__ import annotations

import json
import uuid

import pytest

from app.models.organisation import Organisation
from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.services.platform_catalog_service import PlatformCatalogService
from app.services.survey_results_service import (
    build_answer_aggregates,
    build_whatsapp_survey_results_payload,
    recipient_summary_row,
)


@pytest.fixture()
def db():
    from app.core.database import Base, get_engine, get_sessionmaker
    import app.models  # noqa: F401

    engine = get_engine()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    SessionLocal = get_sessionmaker()
    session = SessionLocal()
    try:
        PlatformCatalogService.ensure_defaults(session)
        yield session
    finally:
        session.close()


def _seed_wa_order(db, *, answers: list[dict]):
    org = Organisation(name="Results Org")
    db.add(org)
    db.commit()
    order = ServiceOrder(
        id=str(uuid.uuid4()),
        org_id=org.id,
        user_id="user-1",
        service_code="survey",
        title="WA results test",
        status="running",
        payment_status="approved",
        recipient_count=1,
        config_json=json.dumps({"delivery": "whatsapp", "survey_channel": "whatsapp", "channels": ["whatsapp"]}),
    )
    db.add(order)
    recipient = ServiceOrderRecipient(
        order_id=order.id,
        row_number=1,
        name="Alex",
        phone="+447700900123",
        status="completed",
        result_json=json.dumps({"wa_conversation": {"answers": answers}}),
    )
    db.add(recipient)
    db.commit()
    return order, recipient


def test_wa_results_include_nps_and_sentiment_breakdown(db):
    order, _ = _seed_wa_order(
        db,
        answers=[
            {"step_role": "rating", "question": "Recommend us", "answer": "9", "reply_type": "choice"},
            {
                "step_role": "reason",
                "question": "Tell us more",
                "answer": "Wait time was long",
                "answer_text": "Wait time was long",
                "reply_type": "long_text",
            },
        ],
    )
    payload = build_whatsapp_survey_results_payload(db, order)
    summary = payload["summary"]
    assert summary["nps_promoters"] == 1
    assert summary["nps_score"] is not None
    assert summary["sentiment_counts"]["positive"] == 1
    aggregates = payload["aggregates"]
    rating_block = next(a for a in aggregates if a["question"] == "Recommend us")
    assert rating_block["visualization"] == "sentiment_breakdown"
    assert len(rating_block["breakdown"]) == 3


def test_wa_nps_reads_answer_text_when_answer_empty(db):
    order, _ = _seed_wa_order(
        db,
        answers=[
            {"step_role": "rating", "question": "Recommend us", "answer": "", "answer_text": "8", "reply_type": "choice"},
        ],
    )
    payload = build_whatsapp_survey_results_payload(db, order)
    assert payload["summary"]["nps_score"] is not None
    assert payload["summary"]["nps_passives"] == 1


def test_recipient_summary_surfaces_voice_transcript(db):
    order, recipient = _seed_wa_order(
        db,
        answers=[
            {
                "step_role": "reason",
                "question": "Tell us more",
                "answer": "Parking is difficult",
                "answer_text": "Parking is difficult",
                "answer_source": "voice_note",
                "transcription_status": "completed",
                "voice_note_job_id": "job-123",
                "reply_type": "long_text",
            }
        ],
    )
    row = recipient_summary_row(recipient, goal="Survey", order_id=order.id)
    assert row["open_feedback"][0]["answer_source"] == "voice"
    assert row["open_feedback"][0]["transcript"] == "Parking is difficult"
    assert row["open_feedback"][0]["audio_url"].endswith("/survey-voice-notes/job-123/audio")
    assert row["voice_responses"]


def test_build_answer_aggregates_includes_pending_voice_note(db):
    order, recipient = _seed_wa_order(
        db,
        answers=[
            {
                "step_role": "reason",
                "question": "Tell us more",
                "answer": "",
                "answer_source": "voice_note",
                "transcription_status": "pending",
                "voice_note_job_id": "job-pending-1",
                "reply_type": "long_text",
            }
        ],
    )
    aggregates = build_answer_aggregates([recipient])
    assert len(aggregates) == 1
    assert aggregates[0]["question"] == "Tell us more"
    assert aggregates[0]["responses"][0]["answer"] == "[Voice note — transcription pending]"


def test_collect_open_feedback_includes_pending_voice(db):
    order, recipient = _seed_wa_order(
        db,
        answers=[
            {
                "step_role": "final_feedback_text",
                "question": "Share more",
                "answer": "",
                "answer_source": "voice_note",
                "transcription_status": "pending",
                "voice_note_job_id": "job-pending-2",
                "reply_type": "long_text",
            }
        ],
    )
    from app.services.survey_results_service import _collect_open_feedback

    rows = _collect_open_feedback(recipient, order_id=order.id)
    assert len(rows) == 1
    assert rows[0]["answer_source"] == "voice"
    assert rows[0]["transcription_status"] == "pending"
    assert "pending" in str(rows[0]["transcript"]).lower()


def test_wa_complete_via_conversation_marker_without_terminal_status(db):
    from app.services.survey_results_service import (
        build_whatsapp_survey_results_payload,
        is_wa_survey_response_complete,
    )

    order, recipient = _seed_wa_order(db, answers=[{"question": "Rate us", "answer": "5"}])
    recipient.status = "in_progress"
    recipient.result_json = json.dumps(
        {"wa_conversation": {"answers": [{"question": "Rate us", "answer": "5"}], "completed_at": "2026-06-14T12:00:00"}}
    )
    db.add(recipient)
    db.commit()

    assert is_wa_survey_response_complete(recipient) is True
    payload = build_whatsapp_survey_results_payload(db, order)
    assert payload["summary"]["completed_count"] == 1


def test_ensure_action_recommendations_uses_fallback_not_sync_ai(db):
    from unittest.mock import patch

    from app.services.survey_results_service import ensure_action_recommendations

    order, recipient = _seed_wa_order(
        db,
        answers=[{"step_role": "rating", "question": "Recommend us", "answer": "9", "reply_type": "choice"}],
    )
    summary = {"completed_count": 1, "nps_label": "Good"}
    aggregates = build_answer_aggregates([recipient])

    with patch("app.services.survey_action_recommendations.generate_ai_action_recommendations") as mock_ai:
        recs = ensure_action_recommendations(
            db,
            order,
            goal="Test",
            org_name="Org",
            summary=summary,
            aggregates=aggregates,
        )
        mock_ai.assert_not_called()
    assert recs

