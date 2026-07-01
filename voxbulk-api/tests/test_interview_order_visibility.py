from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy.orm import Session

from app.models.organisation import Organisation
from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.models.user import User
from app.services.interview_activity_service import InterviewActivityService
from app.services.platform_catalog_service import ServiceOrderService
from app.services.script_moderation_service import apply_script_moderation_gate, interview_script_looks_like_survey
from app.services.service_order_admin_cost_service import enrich_admin_order_costs


@pytest.fixture()
def db_session():
    from app.core.database import Base, get_engine, get_sessionmaker
    import app.models  # noqa: F401

    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    session = get_sessionmaker()()
    try:
        yield session
    finally:
        session.close()


def _seed_interview_order(db: Session, *, campaign_id: str | None = None) -> tuple[ServiceOrder, ServiceOrderRecipient]:
    suffix = uuid.uuid4().hex[:8].upper()
    campaign_id = campaign_id or f"VB-CMP-{suffix}"
    reference_id = f"VB-INT-{suffix}"
    org = Organisation(name=f"Visibility Org {suffix}", country="United Kingdom")
    user = User(email=f"vis-{suffix.lower()}@test.example", password_hash="x")
    db.add(org)
    db.add(user)
    db.flush()
    order = ServiceOrder(
        org_id=org.id,
        user_id=user.id,
        service_code="interview",
        title="Test interview",
        status="completed",
        campaign_id=campaign_id,
        reference_id=reference_id,
        quote_total_pence=305,
        quote_breakdown_json=json.dumps(
            {
                "lines": [
                    {"kind": "connection_fee", "label": "Connection fee", "amount_pence": 200, "detail": "Connection fee: 1 × £2.00"},
                    {
                        "kind": "per_minute",
                        "label": "Interview AI call — per minute",
                        "amount_pence": 105,
                        "detail": "Call minutes: 1 × 3 min × £0.35/min",
                        "duration_minutes": 3,
                    },
                ]
            }
        ),
        launch_billing_json=json.dumps(
            {
                "currency": "GBP",
                "unit_rate_minor": 35,
                "connection_fee_minor": 200,
                "duration_minutes": 3,
                "channel": "ai_call",
            }
        ),
        config_json=json.dumps({"delivery": "ai_call", "expected_duration_minutes": 3}),
    )
    db.add(order)
    db.flush()
    recipient = ServiceOrderRecipient(
        order_id=order.id,
        row_number=1,
        name="Candidate One",
        phone="+447700900000",
        email="cand@test.example",
        status="completed",
        result_json=json.dumps(
            {
                "channel": "meeting",
                "transport": "webrtc",
                "meeting_started_at": "2026-06-01T10:00:00",
                "ended_at": "2026-06-01T10:03:30",
                "duration_seconds": 210,
                "billable_minutes": 4,
                "telnyx_conversation_id": "conv-test-123",
            }
        ),
    )
    db.add(recipient)
    db.commit()
    db.refresh(order)
    db.refresh(recipient)
    return order, recipient


def test_resolve_order_ref_by_campaign_id(db_session: Session):
    order, _ = _seed_interview_order(db_session)
    found = ServiceOrderService.resolve_order_ref(db_session, order.campaign_id)
    assert found is not None
    assert found.id == order.id
    by_ref = ServiceOrderService.resolve_order_ref(db_session, order.reference_id)
    assert by_ref is not None
    assert by_ref.id == order.id
    by_uuid = ServiceOrderService.resolve_order_ref(db_session, order.id)
    assert by_uuid is not None
    assert by_uuid.id == order.id


def test_financial_summary_includes_quote_and_rates(db_session: Session):
    order, _ = _seed_interview_order(db_session)
    payload = ServiceOrderService.order_to_admin_dict(
        db_session,
        order,
        include_recipients=True,
        recipients=ServiceOrderService.get_recipients(db_session, order.id),
    )
    out = enrich_admin_order_costs(db_session, order, payload)
    fin = out["financial_summary"]
    assert fin["quote_total_minor"] == 305
    assert fin["sales_rates"]["interview_per_min_minor"] == 35
    assert fin["sales_rates"]["connection_fee_minor"] == 200
    assert len(fin["quote_breakdown"]) == 2
    assert out["recipients"][0]["retail_cost_minor"] == 340


def test_timeline_includes_web_meeting_events(db_session: Session):
    order, recipient = _seed_interview_order(db_session)
    timeline = InterviewActivityService.timeline(db_session, order, recipient)
    codes = {ev["code"] for ev in timeline["events"]}
    assert "calling" in codes
    assert "call_done" in codes
    labels = " ".join(ev["label"] for ev in timeline["events"])
    assert "Web interview" in labels


def test_interview_script_rejects_survey_nps(db_session: Session):
    assert interview_script_looks_like_survey("How likely are you to recommend us on a scale of 0 to 10?")
    patch = apply_script_moderation_gate(
        service_code="interview",
        config_patch={"approved_script": "Rate your visit with our hygienist 0-10", "script_approved": True},
        previous_cfg={},
        db=db_session,
    )
    assert patch["script_approved"] is False
    assert patch["script_moderation_status"] == "rejected"


def test_interview_script_approve_without_survey_pattern(db_session: Session):
    patch = apply_script_moderation_gate(
        service_code="interview",
        config_patch={
            "approved_script": "Tell me about your experience leading a dental reception team.",
            "script_approved": True,
        },
        previous_cfg={},
        db=db_session,
    )
    assert patch.get("script_approved") is True
