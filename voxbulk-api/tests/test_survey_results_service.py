from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from app.core.database import get_sessionmaker
from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.services.platform_catalog_service import PlatformCatalogService
from app.services.survey_action_recommendations import fallback_action_recommendations
from app.services.survey_results_service import (
    SurveyResultsService,
    build_answer_aggregates,
    build_survey_results_html,
    normalize_nps_display,
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


def test_normalize_nps_display():
    assert normalize_nps_display(50)["score"] == 75
    assert normalize_nps_display(50)["label"] == "Good"
    assert normalize_nps_display(-19)["score"] == 40
    assert normalize_nps_display(-19)["label"] == "Unhappy"


def test_fallback_recommendations_from_aggregates():
    recs = fallback_action_recommendations(
        summary={"completed_count": 5, "nps_label": "Unhappy"},
        aggregates=[
            {
                "question": "What could we improve?",
                "total": 5,
                "responses": [{"answer": "Faster booking", "count": 3}],
            }
        ],
    )
    assert recs
    assert any("booking" in rec["title"].lower() or "booking" in rec["text"].lower() for rec in recs)


@patch(
    "app.services.survey_action_recommendations.generate_ai_action_recommendations",
    return_value=[{"title": "Improve support", "text": "Several responses flagged support wait times."}],
)
def test_build_survey_results_payload(mock_ai, db):
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
    assert payload["summary"]["nps_score"] == 75
    assert payload["summary"]["nps_label"] == "Good"
    assert len(payload["respondents"]) == 2
    assert payload["respondents"][0]["has_transcript"] is True
    assert payload["recommendations"][0]["title"] == "Improve support"
    mock_ai.assert_called_once()


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


def test_build_answer_aggregates_anonymous():
    recipients = [
        ServiceOrderRecipient(
            order_id="o1",
            row_number=1,
            name="Jane",
            phone="+441",
            status="completed",
            result_json=json.dumps(
                {
                    "analysis": {
                        "extracted_answers": [
                            {"question": "Rating?", "answer": "Good"},
                            {"question": "Rating?", "answer": "Fair"},
                        ]
                    }
                }
            ),
        )
    ]
    aggregates = build_answer_aggregates(recipients)
    assert aggregates[0]["question"] == "Rating?"
    assert aggregates[0]["total"] == 2


def test_build_survey_results_html():
    html = build_survey_results_html(
        {
            "order": {"title": "May survey", "goal": "Satisfaction"},
            "summary": {
                "completed_count": 3,
                "response_rate_pct": 75,
                "average_satisfaction_5": 4.2,
                "nps_score": 41,
                "nps_label": "Unhappy",
                "nps_promoters_pct": 40,
                "nps_passives_pct": 30,
                "nps_detractors_pct": 30,
            },
            "aggregates": [{"question": "Rating?", "total": 2, "responses": [{"answer": "Good", "count": 2}]}],
            "recommendations": [{"title": "Improve support", "text": "Review wait times."}],
        }
    )
    assert "May survey" in html
    assert "Answer summary" in html
    assert "Rating?" in html
