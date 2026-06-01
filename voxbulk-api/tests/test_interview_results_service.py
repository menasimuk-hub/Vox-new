"""Tests for interview results and Phase 3 shortlist."""

import json
import uuid

import pytest
from sqlalchemy.orm import Session

from app.models.organisation import Organisation
from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.models.user import User
from app.services.interview_results_service import InterviewResultsService
from app.services.platform_catalog_service import ServiceOrderService


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


@pytest.fixture()
def interview_order(db_session: Session):
    org = Organisation(name="Test Org")
    user = User(email=f"results-{uuid.uuid4().hex[:8]}@test.com", password_hash="x", is_active=True)
    db_session.add(org)
    db_session.add(user)
    db_session.flush()
    return ServiceOrderService.create_order(
        db_session,
        org_id=org.id,
        user_id=user.id,
        service_code="interview",
        title="Engineer screening",
        config={"role": "Senior Engineer"},
    )


def test_interview_results_without_call_shows_awaiting(db_session: Session, interview_order: ServiceOrder):
    db_session.add(
        ServiceOrderRecipient(
            order_id=interview_order.id,
            row_number=1,
            name="Alice Example",
            phone="+447700900001",
            email="alice@example.com",
            status="pending",
        )
    )
    db_session.commit()
    db_session.refresh(interview_order)

    results = InterviewResultsService.get_results(db_session, interview_order)
    assert results["is_mock"] is False
    assert len(results["candidates"]) == 1
    row = results["candidates"][0]
    assert row["has_interview_report"] is False
    assert row["score"] is None
    assert results["kpis"]["called"] == 0
    assert results["kpis"]["reached"] == 0
    assert results["kpis"]["awaiting_interview"] == 1


def test_interview_results_with_analysis(db_session: Session, interview_order: ServiceOrder):
    db_session.add(
        ServiceOrderRecipient(
            order_id=interview_order.id,
            row_number=1,
            name="Bob Example",
            phone="+447700900002",
            email="bob@example.com",
            status="completed",
            result_json=json.dumps(
                {
                    "analysis": {"score": 82, "recommendation": "Advance", "sentiment": "Positive"},
                    "analysis_saved_at": "2026-01-01T12:00:00",
                    "transcript": "Agent: Hello\nCandidate: Hi",
                    "duration_seconds": 360,
                }
            ),
        )
    )
    db_session.commit()
    db_session.refresh(interview_order)

    results = InterviewResultsService.get_results(db_session, interview_order)
    row = results["candidates"][0]
    assert row["has_interview_report"] is True
    assert row["score"] == 82
    assert results["kpis"]["reached"] == 1
