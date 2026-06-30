"""Tests for usage allowance normalization."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.core.database import get_sessionmaker
from app.core.security import hash_password
from app.models.membership import OrganisationMembership
from app.models.organisation import Organisation
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.models.user import User
from app.services.gocardless_service import BillingService
from app.services.usage_allowance_service import UsageAllowanceService
from app.services.usage_wallet_service import UsageWalletService


@pytest.fixture(scope="module", autouse=True)
def _prepare_db():
    from app.core.database import Base, get_engine
    import app.models  # noqa: F401

    Base.metadata.create_all(bind=get_engine())


def _seed_org_with_plan(*, minutes: int = 500, wa: int = 200) -> str:
    with get_sessionmaker()() as db:
        BillingService.ensure_default_plans(db)
        plan = db.execute(select(Plan).where(Plan.code == "starter")).scalar_one_or_none()
        if plan is None:
            plan = db.execute(select(Plan).where(Plan.code != "payg").limit(1)).scalar_one()
        plan.calls_included = minutes
        plan.whatsapp_included = wa
        db.add(plan)
        org = Organisation(name="Allowance Org", contact_email=f"allow-{uuid.uuid4().hex[:8]}@example.com")
        db.add(org)
        db.flush()
        user = User(email=org.contact_email, password_hash=hash_password("pass123"), is_active=True)
        db.add(user)
        db.flush()
        db.add(OrganisationMembership(org_id=org.id, user_id=user.id))
        db.add(
            Subscription(
                org_id=org.id,
                plan_id=plan.id,
                status="active",
                payment_provider="gocardless",
            )
        )
        db.commit()
        return org.id


def test_build_core_allowances_includes_calls_and_whatsapp():
    org_id = _seed_org_with_plan()
    with get_sessionmaker()() as db:
        sub = BillingService.get_subscription(db, org_id)
        row = UsageWalletService.bootstrap_from_plan(db, org_id=org_id, subscription=sub)
        row.calls_used = 40
        row.whatsapp_used = 12
        db.add(row)
        db.commit()
        db.refresh(row)
        usage_payload = UsageWalletService.summary_dict(row, db, org_id)
        rows = UsageAllowanceService.build_core_allowances(usage_payload, shared_pool=False)
        keys = {r["key"] for r in rows}
        assert "calls" in keys
        assert "whatsapp" in keys
        calls = next(r for r in rows if r["key"] == "calls")
        assert calls["used"] == 40
        assert calls["included"] == usage_payload["calls"]["included"]
        assert calls["remaining"] == usage_payload["calls"]["remaining"]
        whatsapp = next(r for r in rows if r["key"] == "whatsapp")
        assert whatsapp["used"] == 12


def test_allowance_alerts_at_eighty_percent():
    rows = UsageAllowanceService.build_core_allowances(
        {
            "period_end": "2026-06-30T00:00:00",
            "calls": {"used": 400, "included": 500, "remaining": 100},
            "whatsapp": {"used": 5, "included": 200, "remaining": 195},
        },
        shared_pool=False,
    )
    alerts = UsageAllowanceService._alerts_from_allowances(rows)
    assert any(a["key"] == "calls" and a["level"] == "warning" for a in alerts)
    assert not any(a["key"] == "whatsapp" for a in alerts)
