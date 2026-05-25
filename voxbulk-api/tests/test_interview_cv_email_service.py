"""Tests for per-task CV email collection window."""

import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.models.organisation import Organisation
from app.models.service_order import ServiceOrder
from app.models.user import User
from app.services.interview_cv_email_service import cv_email_window_state
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


def _order_with_cv_window(db: Session, *, enabled: bool, start: datetime, end: datetime) -> ServiceOrder:
    org = Organisation(name="CV Email Org")
    user = User(email=f"cv-{uuid.uuid4().hex[:8]}@test.com", password_hash="x", is_active=True)
    db.add(org)
    db.add(user)
    db.flush()
    order = ServiceOrderService.create_order(
        db,
        org_id=org.id,
        user_id=user.id,
        service_code="interview",
        title="Engineer",
        config={
            "cv_email_enabled": enabled,
            "cv_email_start_at": start.isoformat(),
            "cv_email_end_at": end.isoformat(),
        },
    )
    db.commit()
    db.refresh(order)
    return order


def test_cv_email_window_disabled(db_session: Session):
    now = datetime.utcnow()
    order = _order_with_cv_window(db_session, enabled=False, start=now - timedelta(hours=1), end=now + timedelta(hours=1))
    assert cv_email_window_state(order, now=now) == "disabled"


def test_cv_email_window_open_and_closed(db_session: Session):
    now = datetime.utcnow()
    order = _order_with_cv_window(db_session, enabled=True, start=now - timedelta(hours=1), end=now + timedelta(hours=1))
    assert cv_email_window_state(order, now=now) == "open"
    assert cv_email_window_state(order, now=now + timedelta(hours=2)) == "after"
    assert cv_email_window_state(order, now=now - timedelta(hours=2)) == "before"
