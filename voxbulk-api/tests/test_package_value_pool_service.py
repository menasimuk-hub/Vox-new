"""Tests for value-pool allowance metering and DD soft cap."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.models.org_usage_period import OrgUsagePeriod
from app.models.organisation import Organisation
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.services.package_value_pool_service import PackageValuePoolService
from app.services.usage_wallet_service import UsageWalletService


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


def _seed_subscriber(db, *, included_minor: int = 10000, used_minor: int = 0):
    org = Organisation(name="Pool Org", billing_currency="GBP")
    db.add(org)
    db.flush()
    plan = Plan(
        code="starter",
        name="Starter",
        price_gbp_pence=included_minor,
        interval="month",
        calls_included=500,
        whatsapp_included=200,
        overage_per_min_pence=35,
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
        payment_provider="gocardless",
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
        calls_included=500,
        whatsapp_included=200,
        allowance_value_included_minor=included_minor,
        allowance_value_used_minor=used_minor,
        overage_per_min_pence=35,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(row)
    db.commit()
    return org, row, plan


def test_check_soft_cap_allows_under_included(db):
    org, row, _plan = _seed_subscriber(db, included_minor=10000, used_minor=5000)
    cap = PackageValuePoolService.check_soft_cap(row, 4000, wa_unit_minor=50, per_min_minor=35)
    assert cap["allowed"] is True
    assert cap["in_grace"] is False


def test_check_soft_cap_grace_between_100_and_110(db):
    _org, row, _plan = _seed_subscriber(db, included_minor=10000, used_minor=9500)
    cap = PackageValuePoolService.check_soft_cap(row, 800, wa_unit_minor=50, per_min_minor=35)
    assert cap["allowed"] is True
    assert cap["in_grace"] is True


def test_check_soft_cap_blocks_above_110(db):
    _org, row, _plan = _seed_subscriber(db, included_minor=10000, used_minor=10000)
    cap = PackageValuePoolService.check_soft_cap(row, 1100, wa_unit_minor=50, per_min_minor=35)
    assert cap["allowed"] is False


def test_apply_wa_burn_increments_value_used(db):
    _org, row, _plan = _seed_subscriber(db)
    burn = PackageValuePoolService.apply_wa_burn(row, units=3, wa_unit_minor=50)
    assert burn == 150
    assert row.allowance_value_used_minor == 150


def test_rollover_seeds_value_pool(db):
    org, row, plan = _seed_subscriber(db, included_minor=9900)
    row.period_end = datetime.utcnow() - timedelta(hours=1)
    db.add(row)
    db.commit()
    stats = UsageWalletService.rollover_due_periods(db)
    assert stats["opened"] == 1
    new_row = UsageWalletService.get_current(db, org.id)
    assert new_row is not None
    assert int(new_row.allowance_value_included_minor or 0) == 9900
    assert int(new_row.allowance_value_used_minor or 0) == 0


def test_adjust_whatsapp_updates_value_pool(db):
    org, row, _plan = _seed_subscriber(db)
    UsageWalletService.adjust_whatsapp_usage(db, org_id=org.id, delta=2, commit=True)
    db.refresh(row)
    assert int(row.whatsapp_used or 0) == 2
    assert int(row.allowance_value_used_minor or 0) > 0


def test_value_pool_overage_breakdown(db):
    org, row, _plan = _seed_subscriber(db, included_minor=1000, used_minor=1200)
    row.allowance_value_used_minor = 1200
    db.add(row)
    db.commit()
    breakdown = UsageWalletService._overage_breakdown_pence(row, db, org.id)
    assert breakdown["total_overage_pence"] == 200
    assert breakdown.get("value_pool_overage_pence") == 200
