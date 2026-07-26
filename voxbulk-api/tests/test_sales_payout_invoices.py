"""Sales payout invoices: available balance cap, reserve/pay/reject, commission types."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.core.security import hash_password
from app.models.billing_invoice import BillingInvoice
from app.models.org_usage_period import OrgUsagePeriod
from app.models.organisation import Organisation
from app.models.sales_rep import SalesCommission, SalesPayoutInvoice, SalesRep
from app.models.user import User
from app.models.platform_services_settings import PlatformServicesSettings  # noqa: F401
from app.services.sales_payout_service import SalesPayoutService
from app.services.sales_rep_service import SalesRepError, SalesRepService


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


def _seed_rep(db, *, kind="salesman", commission_type="month2", commission_pct=10.0, fixed=0) -> SalesRep:
    user = User(email=f"{kind}-{commission_type}@test.com", password_hash=hash_password("pass123"), is_active=True)
    db.add(user)
    db.flush()
    rep = SalesRep(
        user_id=user.id,
        name="Rep",
        kind=kind,
        promo_code=f"CODE{commission_type[:3].upper()}{kind[:1].upper()}",
        commission_pct=commission_pct,
        commission_type=commission_type,
        commission_fixed_minor=fixed,
        payout_method="bank",
        bank_holder_name="Rep Holder",
        bank_name="Barclays",
        bank_sort_code="20-00-00",
        bank_account_number="12345678",
        bank_address="1 High Street",
        is_active=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(rep)
    db.commit()
    db.refresh(rep)
    return rep


def _add_pending(db, *, rep: SalesRep, amount: int, org_id: str | None = None) -> SalesCommission:
    if org_id is None:
        org = Organisation(name="Co")
        db.add(org)
        db.flush()
        org_id = org.id
    row = SalesCommission(
        sales_rep_id=rep.id,
        org_id=org_id,
        amount_minor=amount,
        currency="GBP",
        kind="percent_invoice",
        status="pending",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def test_invoice_cannot_exceed_available(db):
    rep = _seed_rep(db)
    _add_pending(db, rep=rep, amount=5000)
    with pytest.raises(SalesRepError, match="cannot exceed"):
        SalesPayoutService.create_invoice(db, rep=rep, amount_minor=5001)


def test_create_invoice_reserves_and_pay_releases_to_paid(db):
    rep = _seed_rep(db)
    _add_pending(db, rep=rep, amount=3000)
    _add_pending(db, rep=rep, amount=2000)

    with patch.object(SalesPayoutService, "_send_email"):
        inv = SalesPayoutService.create_invoice(db, rep=rep, amount_minor=4000, notes="Withdraw")

    assert inv.status == "submitted"
    assert SalesPayoutService.available_minor(db, rep_id=rep.id) == 1000
    requested = db.execute(
        select(SalesCommission).where(SalesCommission.status == "requested")
    ).scalars().all()
    assert sum(int(c.amount_minor) for c in requested) == 4000

    with patch.object(SalesPayoutService, "_send_email"):
        paid = SalesPayoutService.approve_and_pay(db, invoice=inv, admin_id="admin-1")
    assert paid.status == "paid"
    totals = SalesPayoutService.wallet_totals(db, rep_id=rep.id)
    assert totals["paid_minor"] == 4000
    assert totals["available_minor"] == 1000
    assert totals["requested_minor"] == 0


def test_reject_invoice_frees_balance(db):
    rep = _seed_rep(db)
    _add_pending(db, rep=rep, amount=8000)
    with patch.object(SalesPayoutService, "_send_email"):
        inv = SalesPayoutService.create_invoice(db, rep=rep, amount_minor=2500)
    assert SalesPayoutService.available_minor(db, rep_id=rep.id) == 5500
    SalesPayoutService.reject_invoice(db, invoice=inv, reason="Wrong amount")
    assert SalesPayoutService.available_minor(db, rep_id=rep.id) == 8000
    row = db.get(SalesPayoutInvoice, inv.id)
    assert row is not None and row.status == "rejected"


def test_requires_payout_details(db):
    rep = _seed_rep(db)
    rep.bank_account_number = None
    db.commit()
    _add_pending(db, rep=rep, amount=1000)
    with pytest.raises(SalesRepError, match="bank payout details"):
        SalesPayoutService.create_invoice(db, rep=rep, amount_minor=500)


def test_fixed_commission_accrual(db):
    rep = _seed_rep(db, kind="partner_channel", commission_type="fixed", fixed=2500)
    org = Organisation(name="Fixed Co")
    db.add(org)
    db.flush()
    db.add(
        OrgUsagePeriod(
            org_id=org.id,
            period_start=datetime.utcnow(),
            period_end=datetime.utcnow(),
            status="active",
            promo_code=rep.promo_code,
        )
    )
    inv = BillingInvoice(
        org_id=org.id,
        provider="internal",
        external_invoice_id="fix-fixed-1",
        client_email="a@test.com",
        amount_gbp_pence=10000,
        currency="GBP",
        status="paid",
        kind="subscription",
        created_at=datetime.utcnow(),
    )
    db.add(inv)
    db.commit()
    db.refresh(inv)

    comm = SalesRepService.accrue_commission_for_paid_invoice(db, inv)
    assert comm is not None
    assert int(comm.amount_minor) == 2500
    assert comm.kind == "fixed_invoice"


def test_percent_on_pay_for_salesman(db):
    rep = _seed_rep(db, kind="salesman", commission_type="percent", commission_pct=20)
    org = Organisation(name="Pct Co")
    db.add(org)
    db.flush()
    db.add(
        OrgUsagePeriod(
            org_id=org.id,
            period_start=datetime.utcnow(),
            period_end=datetime.utcnow(),
            status="active",
            promo_code=rep.promo_code,
        )
    )
    inv = BillingInvoice(
        org_id=org.id,
        provider="internal",
        external_invoice_id="fix-pct-1",
        client_email="a@test.com",
        amount_gbp_pence=10000,
        currency="GBP",
        status="paid",
        kind="subscription",
        created_at=datetime.utcnow(),
    )
    db.add(inv)
    db.commit()
    db.refresh(inv)
    comm = SalesRepService.accrue_commission_for_paid_invoice(db, inv)
    assert comm is not None
    assert int(comm.amount_minor) == 2000
