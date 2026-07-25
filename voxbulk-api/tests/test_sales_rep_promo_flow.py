"""Sales rep promo offer flow — PromoOffer sync, wallet voucher redeem, customer linking."""

from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.core.security import hash_password
from app.models.billing_invoice import BillingInvoice
from app.models.membership import OrganisationMembership
from app.models.org_usage_period import OrgUsagePeriod
from app.models.organisation import Organisation
from app.models.promo_offer import PromoOffer
from app.models.sales_rep import SalesCommission, SalesCustomer, SalesRep
from app.models.user import User
from app.models.platform_services_settings import PlatformServicesSettings  # noqa: F401
from app.services.promo_offer_service import PromoOfferService
from app.services.sales_rep_service import KIND_PARTNER_CHANNEL, SalesRepService
from app.services.wallet_service import PromoWalletRestricted, WalletService


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


def _seed_rep(
    db,
    *,
    code: str = "UKTEST20",
    email: str = "rep@test.com",
    kind: str = "salesman",
    commission_pct: float = 15.0,
    company_name: str | None = None,
) -> SalesRep:
    user = User(email=email, password_hash=hash_password("pass123"), is_active=True)
    db.add(user)
    db.flush()
    rep = SalesRep(
        user_id=user.id,
        name="Test Rep",
        company_name=company_name,
        kind=kind,
        promo_code=code,
        commission_pct=commission_pct,
        is_active=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(rep)
    db.commit()
    db.refresh(rep)
    return rep


def _link_org_via_promo(db, *, rep: SalesRep, org_name: str = "Attributed Co") -> Organisation:
    org = Organisation(name=org_name)
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
    db.commit()
    db.refresh(org)
    return org


def _paid_sub_invoice(db, *, org_id: str, amount: int, ext: str) -> BillingInvoice:
    inv = BillingInvoice(
        org_id=org_id,
        provider="internal",
        external_invoice_id=ext,
        client_email="bill@test.com",
        amount_gbp_pence=amount,
        currency="GBP",
        status="paid",
        kind="subscription",
        created_at=datetime.utcnow(),
    )
    db.add(inv)
    db.commit()
    db.refresh(inv)
    return inv


def test_upsert_for_sales_rep_creates_wallet_voucher(db):
    rep = _seed_rep(db)
    promo = PromoOfferService.upsert_for_sales_rep(db, rep)
    assert promo.code == rep.promo_code
    assert promo.offer_type == "sales_wallet_voucher"
    assert int(promo.wallet_credit_pence or 0) == 2000
    assert promo.sales_rep_id == rep.id


def test_redeem_wallet_voucher_credits_promo_wallet(db):
    rep = _seed_rep(db, code="WELCOME20")
    PromoOfferService.upsert_for_sales_rep(db, rep)

    org = Organisation(name="Promo Customer Ltd")
    db.add(org)
    db.flush()
    owner = User(email="customer@test.com", password_hash=hash_password("pass123"), is_active=True)
    db.add(owner)
    db.flush()
    db.add(OrganisationMembership(org_id=org.id, user_id=owner.id, role="owner"))
    db.commit()

    cust = SalesCustomer(
        sales_rep_id=rep.id,
        full_name="Promo Customer",
        email="customer@test.com",
        status="interested",
        interested=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(cust)
    db.commit()

    PromoOfferService.redeem_for_org(db, org_id=org.id, user_id=owner.id, promo_code=rep.promo_code)
    db.refresh(org)
    db.refresh(cust)

    assert int(org.wallet_balance_pence or 0) == 2000
    assert int(org.promo_wallet_balance_pence or 0) == 2000
    assert cust.org_id == org.id
    assert cust.status == "won"


def test_promo_wallet_blocked_for_campaign_launch_debit(db):
    org = Organisation(name="Launch Block Org", wallet_balance_pence=2000, promo_wallet_balance_pence=2000)
    db.add(org)
    db.commit()
    with pytest.raises(PromoWalletRestricted):
        WalletService.debit(
            db,
            org,
            amount_minor=500,
            kind="launch_debit",
            restrict_promo_spend=True,
            commit=True,
        )


def test_link_customer_on_promo_redeem_matches_email(db):
    rep = _seed_rep(db, code="LINKTEST1")
    org = Organisation(name="Linked Co", contact_email="lead@example.com")
    db.add(org)
    db.commit()
    cust = SalesCustomer(
        sales_rep_id=rep.id,
        full_name="Lead Person",
        email="lead@example.com",
        status="interested",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(cust)
    db.commit()
    promo = PromoOffer(
        code=rep.promo_code,
        name="Test",
        offer_type="sales_wallet_voucher",
        wallet_credit_pence=2000,
        sales_rep_id=rep.id,
        max_redemptions=999,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(promo)
    db.commit()

    SalesRepService.link_customer_on_promo_redeem(
        db, promo=promo, org=org, user_email="lead@example.com"
    )
    db.refresh(cust)
    assert cust.org_id == org.id
    assert cust.status == "won"


def test_salesman_commission_applies_pct_on_second_monthly_invoice(db):
    rep = _seed_rep(db, code="SALE15PCT", commission_pct=15.0)
    org = _link_org_via_promo(db, rep=rep, org_name="Monthly Customer")
    inv1 = _paid_sub_invoice(db, org_id=org.id, amount=10000, ext="sub-m1")
    assert SalesRepService.accrue_commission_for_paid_invoice(db, inv1) is None

    inv2 = _paid_sub_invoice(db, org_id=org.id, amount=10000, ext="sub-m2")
    comm = SalesRepService.accrue_commission_for_paid_invoice(db, inv2)
    assert comm is not None
    assert comm.kind == "monthly_2nd"
    assert int(comm.amount_minor) == 1500  # 15% of £100
    assert SalesRepService.accrue_commission_for_paid_invoice(db, inv2) is None


def test_partner_channel_commission_every_paid_invoice(db):
    rep = _seed_rep(
        db,
        code="PART20",
        email="partner@test.com",
        kind=KIND_PARTNER_CHANNEL,
        commission_pct=20.0,
        company_name="Partner Co",
    )
    org = _link_org_via_promo(db, rep=rep, org_name="Partner Customer")
    inv1 = _paid_sub_invoice(db, org_id=org.id, amount=10000, ext="part-m1")
    c1 = SalesRepService.accrue_commission_for_paid_invoice(db, inv1)
    assert c1 is not None
    assert c1.kind == "partner_invoice"
    assert int(c1.amount_minor) == 2000

    inv2 = _paid_sub_invoice(db, org_id=org.id, amount=10000, ext="part-m2")
    c2 = SalesRepService.accrue_commission_for_paid_invoice(db, inv2)
    assert c2 is not None
    assert int(c2.amount_minor) == 2000
    assert c2.id != c1.id

    # Same invoice must not double-count
    assert SalesRepService.accrue_commission_for_paid_invoice(db, inv1) is None

    rows = db.execute(select(SalesCommission).where(SalesCommission.sales_rep_id == rep.id)).scalars().all()
    assert len(rows) == 2


def test_partner_channel_cannot_use_customer_crm_flag(db):
    rep = _seed_rep(
        db,
        code="PARTCRM",
        email="partner2@test.com",
        kind=KIND_PARTNER_CHANNEL,
    )
    assert SalesRepService.is_partner_channel(rep)
    assert not SalesRepService.is_salesman(rep)


def test_partner_channel_create_uses_normal_service_defaults(db):
    """Partners must not get forced all-on services; Admin Off stays hidden."""
    from app.services.org_enabled_services import (
        DEFAULT_ENABLED_SERVICES,
        SERVICE_KEYS,
        org_service_maps,
        serialize_allowed_services,
        serialize_enabled_services,
    )
    from app.services.platform_services_settings_service import ensure_row, update_platform_default_allowed

    ensure_row(db)
    # Platform grants interview+survey only; feedback explicitly Off.
    update_platform_default_allowed(
        db,
        {
            "interview": True,
            "survey": True,
            "customer_feedback": False,
            "feedback_campaigns": False,
            "expo": False,
            "appointments": False,
            "recovery": False,
            "follow_up": False,
            "campaigns": False,
        },
    )

    rep = SalesRepService.create_rep(
        db,
        email="partner-services@test.com",
        password="pass123",
        name="Partner Services",
        promo_code="PARTSVC1",
        kind=KIND_PARTNER_CHANNEL,
        company_name="Partner Services Co",
    )
    org = SalesRepService.partner_org_for_user(db, user_id=rep.user_id)
    assert org is not None
    assert org.allowed_services_json is None  # inherit platform
    allowed, enabled, visible = org_service_maps(org, db)
    assert visible["interview"] is True
    assert visible["survey"] is True
    assert visible["customer_feedback"] is False
    assert allowed["customer_feedback"] is False
    for key in SERVICE_KEYS:
        if key not in ("interview", "survey"):
            assert visible[key] is False

    # Simulate polluted force-all state, then reset.
    all_on = {key: True for key in SERVICE_KEYS}
    org.allowed_services_json = serialize_allowed_services(all_on)
    org.enabled_services_json = serialize_enabled_services(all_on)
    db.add(org)
    db.commit()
    db.refresh(org)
    _, _, polluted = org_service_maps(org, db)
    assert all(polluted[k] for k in SERVICE_KEYS)

    SalesRepService.reset_partner_org_services_to_defaults(db, org)
    db.commit()
    db.refresh(org)
    assert org.allowed_services_json is None
    _, _, cleaned = org_service_maps(org, db)
    assert cleaned["interview"] is True
    assert cleaned["survey"] is True
    assert cleaned["customer_feedback"] is False
    for key in SERVICE_KEYS:
        assert cleaned[key] == bool(DEFAULT_ENABLED_SERVICES.get(key) and allowed.get(key))
