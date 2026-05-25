"""Tests for interview batch reports (Phase 4)."""

import uuid
from datetime import datetime

import pytest
from sqlalchemy.orm import Session

from app.models.organisation import Organisation
from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.models.user import User
from app.services.interview_report_service import InterviewReportService
from app.services.platform_catalog_service import ServiceOrderService


@pytest.fixture()
def db_session():
    from app.core.database import Base, get_engine, get_sessionmaker
    import app.models  # noqa: F401

    engine = get_engine()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    session = get_sessionmaker()()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def org_user(db_session: Session):
    org = Organisation(name="Report Org")
    user = User(email=f"rep-{uuid.uuid4().hex[:8]}@test.com", password_hash="x", is_active=True)
    db_session.add(org)
    db_session.add(user)
    db_session.flush()
    return org, user


def _completed_interview(db: Session, org_id: str, user_id: str, *, title: str) -> ServiceOrder:
    order = ServiceOrderService.create_order(
        db,
        org_id=org_id,
        user_id=user_id,
        service_code="interview",
        title=title,
        config={"role": "Engineer"},
    )
    db.add(
        ServiceOrderRecipient(
            order_id=order.id,
            row_number=1,
            name="Alice Example",
            phone="+447700900001",
            email="alice@example.com",
            status="completed",
        )
    )
    db.add(
        ServiceOrderRecipient(
            order_id=order.id,
            row_number=2,
            name="Bob Example",
            phone="+447700900002",
            status="completed",
        )
    )
    order.recipient_count = 2
    order.status = "completed"
    order.completed_at = datetime.utcnow()
    order.quote_total_pence = 5000
    db.commit()
    db.refresh(order)
    return order


def test_list_batches_month_overview(db_session: Session, org_user):
    org, user = org_user
    _completed_interview(db_session, org.id, user.id, title="Batch A")
    payload = InterviewReportService.list_batches(db_session, org.id, period="month")
    assert payload["period"] == "month"
    assert payload["overview"]["batch_count"] == 1
    assert payload["overview"]["candidate_count"] == 2
    assert len(payload["batches"]) == 1
    assert payload["batches"][0]["title"] == "Batch A"
    assert payload["batches"][0]["advance_count"] >= 0


def test_batch_detail_and_csv(db_session: Session, org_user):
    org, user = org_user
    order = _completed_interview(db_session, org.id, user.id, title="Batch B")
    detail = InterviewReportService.batch_detail(db_session, order)
    assert detail["summary"]["order_id"] == order.id
    assert len(detail["candidates"]) == 2
    csv_text = InterviewReportService.export_batch_csv(detail)
    assert "Alice Example" in csv_text
    assert "Bob Example" in csv_text

    list_payload = InterviewReportService.list_batches(db_session, org.id, period="all")
    export = InterviewReportService.export_batches_csv(list_payload)
    assert "Batch B" in export
    assert "Advance" in export or "Candidates" in export
