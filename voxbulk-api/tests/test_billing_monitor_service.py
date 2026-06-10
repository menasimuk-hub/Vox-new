"""Billing monitor — commercial balance, capacity estimates, next actions."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.models.org_usage_period import OrgUsagePeriod
from app.models.organisation import Organisation
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.services.billing_monitor_service import BillingMonitorService
from app.services.launch_billing_service import LaunchBillingService


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
        yield session
    finally:
        session.close()


def _seed_org_with_usage(
    db,
    *,
    plan_code="starter",
    calls_used=0,
    wa_used=0,
    calls_included=429,
    wa_included=429,
    wallet_pence=0,
):
    org = Organisation(name="Monitor Org", wallet_balance_pence=wallet_pence)
    db.add(org)
    db.flush()
    plan = Plan(
        code=plan_code,
        name="Starter",
        price_gbp_pence=9900,
        interval="month",
        calls_included=calls_included,
        whatsapp_included=wa_included,
        overage_per_min_pence=20,
        is_active=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(plan)
    db.flush()
    sub = Subscription(
        org_id=org.id,
        plan_id=plan.id,
        status="active",
        current_period_end=datetime.utcnow() + timedelta(days=30),
        payment_provider="manual_cash",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(sub)
    db.flush()
    row = OrgUsagePeriod(
        org_id=org.id,
        period_start=datetime.utcnow(),
        period_end=datetime.utcnow() + timedelta(days=30),
        status="active",
        plan_code=plan.code,
        calls_included=calls_included,
        calls_used=calls_used,
        whatsapp_included=wa_included,
        whatsapp_used=wa_used,
        overage_per_min_pence=20,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(row)
    db.commit()
    return org, row


def test_package_exhausted_wallet_empty_shows_zero_estimates(db):
    org, row = _seed_org_with_usage(db, wa_used=429, calls_used=0, wallet_pence=0)
    monitor = BillingMonitorService.build_for_org(db, org, usage_row=row)
    assert monitor["commercial"]["package_remaining_pence"] == 0
    assert monitor["capacity_estimates"]["estimated_wa_surveys"] == 0
    assert monitor["capacity_estimates"]["estimated_ai_minutes"] == 0
    assert monitor["capacity_estimates"]["source"] == "none"
    assert monitor["status"]["next_action"] in {"top_up_wallet", "extra_usage_invoiced"}


def test_package_exhausted_wallet_funded_estimates_from_wallet(db):
    org, row = _seed_org_with_usage(db, wa_used=429, wallet_pence=19100)
    monitor = BillingMonitorService.build_for_org(db, org, usage_row=row)
    assert monitor["commercial"]["package_remaining_pence"] == 0
    assert monitor["commercial"]["wallet_balance_pence"] == 19100
    assert monitor["capacity_estimates"]["source"] == "wallet"
    assert monitor["capacity_estimates"]["estimated_wa_surveys"] > 0
    assert monitor["capacity_estimates"]["estimated_ai_minutes"] > 0
    assert monitor["capacity_estimates"]["label"] == "Estimated from wallet"


def test_package_active_estimates_from_plan(db):
    org, row = _seed_org_with_usage(db, wa_used=100, calls_used=50, wallet_pence=0)
    monitor = BillingMonitorService.build_for_org(db, org, usage_row=row)
    assert monitor["commercial"]["package_remaining_pence"] > 0
    assert monitor["capacity_estimates"]["source"] == "package"
    assert monitor["capacity_estimates"]["estimated_wa_surveys"] == monitor["commercial"]["package_remaining_units"]
    assert monitor["capacity_estimates"]["estimated_ai_minutes"] == monitor["commercial"]["package_remaining_units"]
    assert monitor["capacity_estimates"]["label"] == "Estimated from plan"


def test_launch_wallet_before_dd_on_subscription(db):
    org, _row = _seed_org_with_usage(db, wa_used=429, wallet_pence=5000)
    result = LaunchBillingService._allocate_payment(
        db,
        org,
        currency="GBP",
        total_minor=1000,
        collect_by_dd=True,
        base={"channel": "whatsapp"},
    )
    assert result["payment_method"] == "wallet"
    assert result["wallet_charge_minor"] == 1000
    assert result["dd_charge_minor"] == 0


def test_estimates_not_used_in_overage_calculation(db):
    org, row = _seed_org_with_usage(db, wa_used=500, calls_used=50, wallet_pence=0)
    monitor = BillingMonitorService.build_for_org(db, org, usage_row=row)
    from app.services.usage_wallet_service import UsageWalletService

    breakdown = UsageWalletService._overage_breakdown_pence(row, db, org.id)
    assert breakdown["total_overage_pence"] > 0
    assert monitor["capacity_estimates"]["estimated_wa_surveys"] == 0
    assert breakdown["total_overage_pence"] != monitor["capacity_estimates"]["estimated_wa_surveys"]
