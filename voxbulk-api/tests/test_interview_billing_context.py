"""CV email collection access by plan tier."""

from __future__ import annotations

import uuid

from app.core.database import get_sessionmaker
from app.core.security import hash_password
from app.models.membership import OrganisationMembership
from app.models.organisation import Organisation
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.models.org_usage_period import OrgUsagePeriod
from app.models.user import User
from app.services.interview_billing_context import org_interview_billing_context, plan_allows_cv_email


def _seed_org(db):
    org = Organisation(name="Billing Org")
    db.add(org)
    db.flush()
    user = User(email=f"billing-{uuid.uuid4().hex[:8]}@test.com", password_hash=hash_password("pass123"), is_active=True)
    db.add(user)
    db.flush()
    db.add(OrganisationMembership(org_id=org.id, user_id=user.id, role="owner"))
    return org


from sqlalchemy import select


def _plan(db, *, code: str, name: str | None = None, price: int = 12900) -> Plan:
    existing = db.execute(select(Plan).where(Plan.code == code)).scalar_one_or_none()
    if existing is not None:
        return existing
    row = Plan(
        id=str(uuid.uuid4()),
        code=code,
        name=name or code.title(),
        price_gbp_pence=price,
        interval="monthly",
        service_kind="voxbulk",
    )
    db.add(row)
    db.flush()
    return row


def test_plan_allows_cv_email_pro_not_payg():
    pro = Plan(code="pro", name="Pro", price_gbp_pence=12900, interval="monthly")
    payg = Plan(code="payg", name="Pay as you go", price_gbp_pence=0, interval="monthly")
    free = Plan(code="free", name="Free", price_gbp_pence=0, interval="monthly")
    assert plan_allows_cv_email(pro) is True
    assert plan_allows_cv_email(payg) is False
    assert plan_allows_cv_email(free) is False


def test_pro_plan_via_usage_wallet_allows_cv_email_without_subscription_row():
    with get_sessionmaker()() as db:
        org = _seed_org(db)
        _plan(db, code="pro", name="Pro")
        now = __import__("datetime").datetime.utcnow()
        db.add(
            OrgUsagePeriod(
                org_id=org.id,
                period_start=now,
                period_end=now + __import__("datetime").timedelta(days=30),
                status="active",
                plan_code="pro",
            )
        )
        db.commit()

        ctx = org_interview_billing_context(db, org)
        assert ctx["cv_email_allowed"] is True
        assert ctx["plan_code"] == "pro"


def test_payg_subscription_blocks_cv_email():
    with get_sessionmaker()() as db:
        org = _seed_org(db)
        payg = _plan(db, code="payg", name="Pay as you go", price=0)
        db.add(
            Subscription(
                org_id=org.id,
                plan_id=payg.id,
                status="active",
                payment_provider="payg",
            )
        )
        db.commit()

        ctx = org_interview_billing_context(db, org)
        assert ctx["cv_email_allowed"] is False
        assert "Pay as you go" in str(ctx["cv_email_block_reason"])


def test_active_pro_subscription_allows_cv_email():
    with get_sessionmaker()() as db:
        org = _seed_org(db)
        pro = _plan(db, code="pro", name="Pro")
        db.add(
            Subscription(
                org_id=org.id,
                plan_id=pro.id,
                status="active",
                payment_provider="gocardless",
            )
        )
        db.commit()

        ctx = org_interview_billing_context(db, org)
        assert ctx["cv_email_allowed"] is True
        assert ctx["has_active_subscription"] is True
