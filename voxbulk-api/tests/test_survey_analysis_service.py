from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta

import pytest

from app.core.database import get_sessionmaker
from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.services.platform_catalog_service import PlatformCatalogService
from app.services.survey_analysis_service import (
    ANALYSIS_VERSION,
    SurveyAnalysisService,
    _normalize_analysis,
    build_order_analysis_report,
    ensure_survey_transcript,
    extract_survey_analysis,
    run_survey_analysis_if_needed,
)


@pytest.fixture()
def db():
    with get_sessionmaker()() as session:
        PlatformCatalogService.ensure_defaults(session)
        yield session


def _survey_order(**kwargs) -> ServiceOrder:
    config = {
        "survey_channel": "ai_call",
        "channels": ["call"],
        "script_approved": True,
        "approved_script": "QUESTIONS\n1. How was your visit?\n2. Would you recommend us?",
        "goal": "Patient satisfaction",
        "organisation_name": "Acme Clinic",
    }
    row = ServiceOrder(
        id=kwargs.pop("id", str(uuid.uuid4())),
        org_id="org-1",
        user_id="user-1",
        service_code="survey",
        title="Test survey",
        status=kwargs.pop("status", "running"),
        payment_status="approved",
        recipient_count=1,
        quote_total_pence=2900,
        config_json=json.dumps(config),
        run_mode="scheduled",
        scheduled_start_at=datetime.utcnow() - timedelta(hours=1),
        scheduled_end_at=datetime.utcnow() + timedelta(hours=2),
        started_at=datetime.utcnow() - timedelta(minutes=30),
    )
    for key, value in kwargs.items():
        setattr(row, key, value)
    return row


def test_normalize_analysis_parses_scores():
    raw = {
        "short_summary": "Good call.",
        "sentiment": "positive",
        "satisfaction_score": 8,
        "recommend_score": 9,
        "answers": [{"question": "Q1", "answer": "Great", "confidence": "high"}],
        "issues": ["Wait time"],
        "tags": ["Staff"],
        "completion_quality": "complete",
        "key_themes": ["service"],
    }
    out = _normalize_analysis(raw)
    assert out["satisfaction_score"] == 8.0
    assert out["recommend_score"] == 9.0
    assert out["sentiment"] == "positive"
    assert len(out["answers"]) == 1


def test_ensure_transcript_idempotent(db):
    order = _survey_order()
    db.add(order)
    db.flush()
    recipient = ServiceOrderRecipient(
        order_id=order.id,
        row_number=1,
        name="Jane Doe",
        phone="+447700900123",
        status="completed",
        result_json=json.dumps(
            {
                "call_control_id": "cc-1",
                "transcript": "User: Fine thanks.\nAgent: Thank you.",
                "transcript_saved_at": "2026-01-01T12:00:00",
            }
        ),
    )
    db.add(recipient)
    db.commit()

    result = ensure_survey_transcript(db, order=order, recipient=recipient)
    assert result["transcript"].startswith("User:")
    db.refresh(recipient)
    stored = json.loads(recipient.result_json or "{}")
    assert stored["transcript_saved_at"] == "2026-01-01T12:00:00"


def test_run_analysis_skips_when_already_saved(db, monkeypatch):
    order = _survey_order()
    db.add(order)
    db.flush()
    recipient = ServiceOrderRecipient(
        order_id=order.id,
        row_number=1,
        name="Jane Doe",
        phone="+447700900123",
        status="completed",
        result_json=json.dumps(
            {
                "transcript": "User: Good.\nAgent: Thanks.",
                "transcript_saved_at": datetime.utcnow().isoformat(),
                "analysis_saved_at": datetime.utcnow().isoformat(),
                "analysis_version": ANALYSIS_VERSION,
                "analysis": {"short_summary": "Done", "sentiment": "positive"},
            }
        ),
    )
    db.add(recipient)
    db.commit()

    monkeypatch.setattr(
        "app.services.survey_analysis_service.extract_survey_analysis",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not call DeepSeek")),
    )
    out = run_survey_analysis_if_needed(db, order=order, recipient=recipient)
    assert out["analysis"]["short_summary"] == "Done"


def test_extract_survey_analysis_calls_deepseek(db, monkeypatch):
    order = _survey_order()
    recipient = ServiceOrderRecipient(
        order_id=order.id,
        row_number=1,
        name="Jane Doe",
        phone="+447700900123",
        status="completed",
    )

    class FakeResponse:
        assistant_text = json.dumps(
            {
                "short_summary": "Patient was happy.",
                "sentiment": "positive",
                "satisfaction_score": 9,
                "recommend_score": 10,
                "answers": [{"question": "How was visit?", "answer": "Excellent", "confidence": "high"}],
                "issues": [],
                "tags": ["care"],
                "completion_quality": "complete",
                "key_themes": ["quality"],
            }
        )

    monkeypatch.setattr(
        "app.services.survey_analysis_service.OpenAIProviderService.complete",
        lambda *args, **kwargs: FakeResponse(),
    )
    analysis = extract_survey_analysis(
        db,
        order=order,
        recipient=recipient,
        transcript="User: Excellent visit.\nAgent: Glad to hear it.",
        config=json.loads(order.config_json),
    )
    assert analysis["satisfaction_score"] == 9.0
    assert analysis["recommend_score"] == 10.0


def test_build_order_analysis_report_aggregates():
    recipients = [
        ServiceOrderRecipient(
            order_id="o1",
            row_number=1,
            name="A",
            phone="+1",
            status="completed",
            result_json=json.dumps(
                {
                    "analysis_saved_at": "t",
                    "analysis_version": ANALYSIS_VERSION,
                    "analysis": {
                        "sentiment": "positive",
                        "satisfaction_score": 8,
                        "recommend_score": 9,
                        "issues": ["wait time"],
                        "tags": ["booking"],
                    },
                }
            ),
        ),
        ServiceOrderRecipient(
            order_id="o1",
            row_number=2,
            name="B",
            phone="+2",
            status="completed",
            result_json=json.dumps(
                {
                    "analysis_saved_at": "t",
                    "analysis_version": ANALYSIS_VERSION,
                    "analysis": {
                        "sentiment": "negative",
                        "satisfaction_score": 4,
                        "recommend_score": 3,
                        "issues": ["wait time"],
                        "tags": ["staff"],
                    },
                }
            ),
        ),
    ]
    report = build_order_analysis_report(recipients)
    assert report["analyzed_count"] == 2
    assert report["average_satisfaction"] == 6.0
    assert report["nps"]["promoters"] == 1
    assert report["nps"]["detractors"] == 1
    assert report["top_issues"][0]["label"] == "wait time"
    assert report["sentiment_counts"]["positive"] == 1


def test_process_recipient_post_call_completed(db, monkeypatch):
    order = _survey_order()
    db.add(order)
    db.flush()
    recipient = ServiceOrderRecipient(
        order_id=order.id,
        row_number=1,
        name="Jane Doe",
        phone="+447700900123",
        status="completed",
        result_json=json.dumps({"call_control_id": "cc-1"}),
    )
    db.add(recipient)
    db.commit()

    monkeypatch.setattr(
        "app.services.survey_analysis_service.ensure_survey_transcript",
        lambda db, **kwargs: {
            "transcript": "User: Good.\nAgent: Thanks for your time.",
            "transcript_saved_at": datetime.utcnow().isoformat(),
        },
    )
    monkeypatch.setattr(
        "app.services.survey_analysis_service.run_survey_analysis_if_needed",
        lambda db, **kwargs: {
            "analysis_saved_at": datetime.utcnow().isoformat(),
            "analysis": {"short_summary": "OK", "sentiment": "neutral"},
        },
    )
    monkeypatch.setattr(
        "app.services.survey_analysis_service.refresh_order_survey_report",
        lambda db, order: None,
    )

    SurveyAnalysisService.process_recipient_post_call(
        db,
        order=order,
        recipient=recipient,
        terminal_status="completed",
        hangup_extra={"call_control_id": "cc-1"},
    )
