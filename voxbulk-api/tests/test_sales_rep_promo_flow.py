"""Sales rep promo offer flow — PromoOffer sync, wallet voucher redeem, customer linking."""

from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.core.security import hash_password
from app.models.membership import OrganisationMembership
from app.models.organisation import Organisation
from app.models.promo_offer import PromoOffer
from app.models.sales_rep import SalesCustomer, SalesRep
from app.models.user import User
from app.services.promo_offer_service import PromoOfferService
from app.services.sales_rep_service import SalesRepService
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


def _seed_rep(db, *, code: str = "UKTEST20") -> SalesRep:
    user = User(email="rep@test.com", password_hash=hash_password("pass123"), is_active=True)
    db.add(user)
    db.flush()
    rep = SalesRep(
        user_id=user.id,
        name="Test Rep",
        promo_code=code,
        is_active=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(rep)
    db.commit()
    db.refresh(rep)
    return rep


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
