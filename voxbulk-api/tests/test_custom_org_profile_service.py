"""Tests for Custom Org / WA Profiles service — plan picker options."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models.custom_org_profile import CustomOrgProfile
from app.models.plan import Plan
from app.services.gocardless_service import BillingService
from app.services.custom_org_profile_service import CustomOrgProfileService


@pytest.fixture()
def db():
    from app.core.database import Base, get_engine, get_sessionmaker
    import app.models  # noqa: F401

    engine = get_engine()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    session = get_sessionmaker()()
    BillingService.ensure_default_plans(session)
    session.commit()
    try:
        yield session
    finally:
        session.close()


def test_options_plans_use_products_hub_metadata(db):
    opts = CustomOrgProfileService.options(db)
    plans = opts["plans"]
    assert plans
    sample = plans[0]
    assert "id" in sample
    assert "name" in sample
    assert "picker_label" in sample
    assert "product_line" in sample
    assert "group_label" in sample
    assert "currency" in sample or sample.get("product_line") == "voxbulk"
    assert "region" in sample


def test_options_plans_core_before_feedback(db):
    plans = CustomOrgProfileService.options(db)["plans"]
    lines = [p.get("product_line") for p in plans]
    if "voxbulk" in lines and "customer_feedback" in lines:
        assert lines.index("voxbulk") < lines.index("customer_feedback")


def test_serialize_row_includes_plan_service_and_currency(db):
    plan = db.execute(
        select(Plan).where(Plan.code == "starter").limit(1)
    ).scalar_one_or_none()
    if plan is None:
        plan = db.execute(select(Plan).limit(1)).scalar_one()
    row = CustomOrgProfile(name="WA test", plan_id=plan.id, status="setup")
    db.add(row)
    db.commit()
    data = CustomOrgProfileService._serialize_row(db, row)
    assert data["plan_id"] == plan.id
    assert data["plan_code"] == plan.code
    assert data["plan_name"] == plan.name
    if str(getattr(plan, "service_kind", "") or "") != "dental":
        assert data["plan_service"]
        assert data["plan_currency"] or data["plan_region"]
