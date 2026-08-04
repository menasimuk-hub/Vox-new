"""Commission months 1–6 + one-time bonus modes; hub invoice email uses sales sender."""

from __future__ import annotations

import json
from datetime import datetime
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.core.security import hash_password
from app.models.billing_invoice import BillingInvoice
from app.models.organisation import Organisation
from app.models.platform_sender_email import PlatformSenderEmail  # noqa: F401
from app.models.sales_hub_invoice import SalesHubInvoice, SalesHubInvoiceItem  # noqa: F401
from app.models.sales_rep import SalesCommission, SalesCustomer, SalesRep
from app.models.user import User
from app.models.platform_services_settings import PlatformServicesSettings  # noqa: F401
from app.services.platform_sender_email_service import PlatformSenderEmailService
from app.services.sales_hub_invoice_service import SalesHubInvoiceService, SalesRepError
from app.services.sales_rep_service import SalesRepService


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


def _seed_salesman(db, *, tiers=None, mode="commission_only", bonus=0) -> tuple[SalesRep, Organisation]:
    user = User(email="s1@test.com", password_hash=hash_password("pass123"), is_active=True)
    db.add(user)
    db.flush()
    org = Organisation(name="Cust Co")
    db.add(org)
    db.flush()
    default_tiers = [
        {"month": m, "enabled": m in (1, 6), "kind": "percent", "value": 10 if m == 1 else 5}
        for m in range(1, 7)
    ]
    rep = SalesRep(
        user_id=user.id,
        name="Sam",
        kind="salesman",
        promo_code="SAM10",
        commission_pct=10,
        commission_type="month2",
        commission_tiers_json=json.dumps(tiers or default_tiers),
        commission_mode=mode,
        one_time_bonus_minor=bonus,
        currency="GBP",
        country="GB",
        is_active=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(rep)
    db.flush()
    link = SalesCustomer(
        sales_rep_id=rep.id,
        org_id=org.id,
        full_name="Cust Co",
        company_name="Cust Co",
        status="won",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(link)
    db.commit()
    db.refresh(rep)
    return rep, org


def _paid_sub(db, org_id: str, *, amount=10000, inv_id=None) -> BillingInvoice:
    iid = inv_id or f"inv-{datetime.utcnow().timestamp()}"
    inv = BillingInvoice(
        id=iid,
        org_id=org_id,
        kind="subscription",
        status="paid",
        amount_gbp_pence=amount,
        currency="GBP",
        provider="internal",
        external_invoice_id=iid,
        client_email="billing@example.com",
        created_at=datetime.utcnow(),
    )
    db.add(inv)
    db.commit()
    db.refresh(inv)
    return inv


def test_accrue_month_1_and_month_6(db):
    rep, org = _seed_salesman(db)
    inv1 = _paid_sub(db, org.id, inv_id="sub-1")
    c1 = SalesRepService.accrue_commission_for_paid_invoice(db, inv1)
    assert c1 is not None
    assert c1.kind == "monthly_1st"
    assert c1.amount_minor == 1000  # 10% of 10000

    # months 2–5 disabled → no accrual
    for i in range(2, 6):
        inv = _paid_sub(db, org.id, inv_id=f"sub-{i}")
        assert SalesRepService.accrue_commission_for_paid_invoice(db, inv) is None

    inv6 = _paid_sub(db, org.id, inv_id="sub-6")
    c6 = SalesRepService.accrue_commission_for_paid_invoice(db, inv6)
    assert c6 is not None
    assert c6.kind == "monthly_6th"
    assert c6.amount_minor == 500  # 5%


def test_one_time_only_once(db):
    rep, org = _seed_salesman(db, mode="one_time_only", bonus=5000)
    inv1 = _paid_sub(db, org.id, inv_id="ot-1")
    c1 = SalesRepService.accrue_commission_for_paid_invoice(db, inv1)
    assert c1 is not None
    assert c1.kind == "one_time_bonus"
    assert c1.amount_minor == 5000
    inv2 = _paid_sub(db, org.id, inv_id="ot-2")
    assert SalesRepService.accrue_commission_for_paid_invoice(db, inv2) is None


def test_one_time_plus_commission(db):
    tiers = [{"month": m, "enabled": m == 1, "kind": "percent", "value": 10} for m in range(1, 7)]
    rep, org = _seed_salesman(db, tiers=tiers, mode="one_time_plus_commission", bonus=2500)
    inv1 = _paid_sub(db, org.id, inv_id="plus-1")
    c1 = SalesRepService.accrue_commission_for_paid_invoice(db, inv1)
    assert c1 is not None
    assert c1.kind == "monthly_1st"
    bonuses = (
        db.execute(
            select(SalesCommission).where(
                SalesCommission.sales_rep_id == rep.id,
                SalesCommission.kind == "one_time_bonus",
            )
        )
        .scalars()
        .all()
    )
    assert len(bonuses) == 1
    assert bonuses[0].amount_minor == 2500


def test_hub_invoice_send_uses_sales_sender(db):
    PlatformSenderEmailService.create(db, local_part="sales", from_name="Sales", purpose="sales", password="spw")
    user = User(email="rep@test.com", password_hash=hash_password("x"), is_active=True)
    db.add(user)
    db.flush()
    rep = SalesRep(
        user_id=user.id,
        name="R",
        kind="salesman",
        promo_code="R1",
        is_active=True,
        currency="GBP",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(rep)
    db.commit()
    inv = SalesHubInvoiceService.create(
        db,
        rep=rep,
        payload={
            "sales_rep_id": rep.id,
            "kind": "commission",
            "customer": "Acme",
            "customer_email": "buyer@example.com",
            "currency": "GBP",
            "items": [{"description": "Sales commission", "quantity": 1, "unit_price_minor": 5000}],
        },
    )
    with patch("app.services.smtp_mailer_service.SmtpMailerService.send_html") as send:
        send.return_value = None
        with patch.object(SalesHubInvoiceService, "render_pdf_bytes", return_value=b"%PDF-1.4 fake"):
            with patch(
                "app.services.transactional_email_service.TransactionalEmailService.load_template_fields",
                return_value=("Invoice {{invoice_number}}", "<p>{{customer_name}}</p>", True),
            ):
                SalesHubInvoiceService.send_email(db, inv=inv, reminder=False)
        assert send.called
        kwargs = send.call_args.kwargs
        assert kwargs["from_email"] == "sales@voxbulk.com"
        assert kwargs["to_addr"] == "buyer@example.com"
        assert kwargs["smtp_password"] == "spw"


def test_hub_invoice_send_falls_back_to_rep_email(db):
    PlatformSenderEmailService.create(db, local_part="sales", from_name="Sales", purpose="sales")
    user = User(email="rep-fallback@test.com", password_hash=hash_password("x"), is_active=True)
    db.add(user)
    db.flush()
    rep = SalesRep(
        user_id=user.id,
        name="R3",
        kind="salesman",
        promo_code="R3",
        is_active=True,
        currency="GBP",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(rep)
    db.commit()
    inv = SalesHubInvoiceService.create(
        db,
        rep=rep,
        payload={
            "sales_rep_id": rep.id,
            "customer": "",
            "customer_email": None,
            "currency": "GBP",
            "items": [{"description": "Sales commission", "quantity": 1, "unit_price_minor": 1000}],
        },
    )
    assert inv.customer_email == "rep-fallback@test.com"
    with patch("app.services.smtp_mailer_service.SmtpMailerService.send_html") as send:
        send.return_value = None
        with patch.object(SalesHubInvoiceService, "render_pdf_bytes", return_value=b"%PDF"):
            with patch(
                "app.services.transactional_email_service.TransactionalEmailService.load_template_fields",
                return_value=("Subj", "<p>x</p>", True),
            ):
                SalesHubInvoiceService.send_email(db, inv=inv, reminder=False)
        assert send.call_args.kwargs["to_addr"] == "rep-fallback@test.com"


def test_hub_invoice_render_html_uses_get_settings(db):
    user = User(email="rep4@test.com", password_hash=hash_password("x"), is_active=True)
    db.add(user)
    db.flush()
    rep = SalesRep(
        user_id=user.id,
        name="R4",
        kind="salesman",
        promo_code="R4",
        is_active=True,
        currency="GBP",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(rep)
    db.commit()
    inv = SalesHubInvoiceService.create(
        db,
        rep=rep,
        payload={
            "customer": "Acme",
            "currency": "GBP",
            "items": [{"description": "Sales commission", "quantity": 1, "unit_price_minor": 100}],
        },
    )
    html = SalesHubInvoiceService.render_html(db, inv)
    assert "Invoice" in html
    assert inv.number in html


def test_hub_invoice_send_requires_sales_sender(db):
    user = User(email="rep2@test.com", password_hash=hash_password("x"), is_active=True)
    db.add(user)
    db.flush()
    rep = SalesRep(
        user_id=user.id,
        name="R2",
        kind="salesman",
        promo_code="R2",
        is_active=True,
        currency="GBP",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(rep)
    db.commit()
    inv = SalesHubInvoiceService.create(
        db,
        rep=rep,
        payload={
            "sales_rep_id": rep.id,
            "customer": "Acme",
            "customer_email": "buyer@example.com",
            "currency": "GBP",
            "items": [{"description": "Sales commission", "quantity": 1, "unit_price_minor": 1000}],
        },
    )
    with pytest.raises(SalesRepError, match="Configure sales@"):
        SalesHubInvoiceService.send_email(db, inv=inv, reminder=False)
