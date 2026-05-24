from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta

import pytest

from app.core.database import get_sessionmaker
from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.services.platform_catalog_service import PlatformCatalogService
from app.services.survey_results_service import (
    SurveyResultsService,
    derive_survey_recommendations,
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
        "goal": "Patient satisfaction",
        "approved_script": "How was your visit?",
    }
    report = {
        "total": 2,
        "completed": 2,
        "analysis": {
            "analyzed_count": 2,
            "average_satisfaction": 8.0,
            "average_recommend_score": 8.5,
            "nps": {"score": 50.0, "promoters": 1, "passives": 1, "detractors": 0, "responses": 2},
            "sentiment_counts": {"positive": 2},
            "top_issues": [{"label": "wait time", "count": 2}],
            "top_tags": [{"label": "booking", "count": 1}],
        },
    }
    row = ServiceOrder(
        id=str(uuid.uuid4()),
        org_id="org-1",
        user_id="user-1",
        service_code="survey",
        title="May satisfaction survey",
        status="completed",
        payment_status="approved",
        recipient_count=2,
        quote_total_pence=2900,
        config_json=json.dumps(config),
        report_json=json.dumps(report),
        started_at=datetime.utcnow() - timedelta(hours=2),
        completed_at=datetime.utcnow() - timedelta(hours=1),
    )
    for key, value in kwargs.items():
        setattr(row, key, value)
    return row


def test_derive_recommendations_from_issues():
    recs = derive_survey_recommendations(
        top_issues=[{"label": "wait time", "count": 3}],
        top_tags=[{"label": "parking", "count": 2}],
        completed_count=5,
    )
    assert recs
    assert "wait time" in recs[0]["text"].lower()


def test_build_survey_results_payload(db):
    order = _survey_order()
    db.add(order)
    db.flush()
    r1 = ServiceOrderRecipient(
        order_id=order.id,
        row_number=1,
        name="Jane Doe",
        phone="+447700900123",
        status="completed",
        result_json=json.dumps(
            {
                "duration_seconds": 185,
                "transcript": "User: Good visit.",
                "analysis_saved_at": "t",
                "analysis": {
                    "short_summary": "Positive call",
                    "sentiment": "positive",
                    "satisfaction_score": 8,
                    "recommend_score": 9,
                },
            }
        ),
    )
    r2 = ServiceOrderRecipient(
        order_id=order.id,
        row_number=2,
        name="John Smith",
        phone="+447700900124",
        status="no_answer",
        result_json=json.dumps({}),
    )
    db.add_all([r1, r2])
    db.commit()

    payload = SurveyResultsService.get_results(db, order)
    assert payload["ok"] is True
    assert payload["order"]["title"] == "May satisfaction survey"
    assert payload["summary"]["completed_count"] == 2
    assert payload["summary"]["average_satisfaction_5"] == 4.0
    assert len(payload["respondents"]) == 2
    assert payload["respondents"][0]["has_transcript"] is True
    assert payload["recommendations"]


def test_recipient_detail_payload(db):
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
                "transcript": "User: Fine.\nAgent: Thanks.",
                "analysis": {
                    "answers": [{"question": "Rating?", "answer": "Good", "confidence": "high"}],
                    "issues": ["wait"],
                    "tags": ["staff"],
                },
            }
        ),
    )
    db.add(recipient)
    db.commit()

    detail = SurveyResultsService.get_recipient_detail(db, order, recipient)
    assert detail["recipient"]["transcript"].startswith("User:")
    assert detail["recipient"]["extracted_answers"][0]["answer"] == "Good"
