from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.models.organisation import Organisation
from app.models.service_order import ServiceOrder
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


def test_enrich_admin_order_costs_resolves_org_currency(db_session: Session):
    org = Organisation(name="Cost Test Org", country="United Kingdom")
    db_session.add(org)
    db_session.flush()

    order = ServiceOrder(
        org_id=org.id,
        user_id="00000000-0000-0000-0000-000000000001",
        service_code="survey",
        title="Test survey",
        status="completed",
    )
    db_session.add(order)
    db_session.flush()

    payload = {
        "launch_billing": {},
        "billing_settlement": {},
        "recipients": [
            {
                "id": "r1",
                "billable_minutes": 2,
                "call_control_id": None,
            }
        ],
    }

    out = enrich_admin_order_costs(db_session, order, payload)
    assert out["cost_summary"]["currency"] == "GBP"
    assert out["recipients"][0]["retail_cost_display"] == "—"


def test_enrich_admin_order_costs_with_unit_rate(db_session: Session):
    org = Organisation(name="Retail Org", country="Germany")
    db_session.add(org)
    db_session.flush()

    order = ServiceOrder(
        org_id=org.id,
        user_id="00000000-0000-0000-0000-000000000002",
        service_code="survey",
        title="Retail survey",
        status="completed",
    )
    db_session.add(order)
    db_session.flush()

    payload = {
        "launch_billing": {"currency": "EUR", "unit_rate_minor": 50, "connection_fee_minor": 10},
        "recipients": [{"id": "r1", "billable_minutes": 3}],
    }

    out = enrich_admin_order_costs(db_session, order, payload)
    row = out["recipients"][0]
    assert row["retail_cost_minor"] == 160
    assert row["retail_cost_display"] == "€1.60"
    assert out["cost_summary"]["total_retail_cost_display"] == "€1.60"
