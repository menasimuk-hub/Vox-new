"""Phase 8: promo unique redeem, Airwallex minor units, launch charge CAS."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.core.database import Base, get_engine, get_sessionmaker
from app.models.organisation import Organisation
from app.models.promo_offer import PromoRedemption
from app.models.service_order import ServiceOrder
from app.services.billing_currency import major_amount_to_minor
from app.services.launch_billing_service import LaunchBillingService
from app.services.platform_catalog_service import ServiceOrderService
from app.services.promo_offer_service import PromoOfferError, PromoOfferService


@pytest.fixture(scope="module", autouse=True)
def _prepare_db():
    import app.models  # noqa: F401

    engine = get_engine()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_major_amount_to_minor_uses_decimal_not_float():
    assert major_amount_to_minor("10.50") == 1050
    assert major_amount_to_minor(10.5) == 1050
    assert major_amount_to_minor("0.29") == 29
    assert major_amount_to_minor(0) == 0
    assert major_amount_to_minor(None) == 0
    assert major_amount_to_minor("") == 0
    # Classic float pitfall: 1.005 * 100 can be 100.499… → round to 100; Decimal → 101.
    assert major_amount_to_minor("1.005") == 101
    assert major_amount_to_minor(12) == 1200


def test_promo_redeem_rejects_second_org_redeem():
    Session = get_sessionmaker()
    with Session() as db:
        org = Organisation(name=f"Promo-{uuid.uuid4().hex[:8]}")
        db.add(org)
        db.flush()
        promo = PromoOfferService.create_admin(
            db,
            {
                "service_kind": "survey",
                "benefit_kind": "free_usage",
                "usage_amount": 3,
                "max_redemptions": 10,
                "redeem_mode": "anyone",
            },
        )
        PromoOfferService.redeem_for_org(
            db, org_id=org.id, user_id=None, promo_code=promo.code, source="dashboard"
        )
        with pytest.raises(PromoOfferError, match="already redeemed"):
            PromoOfferService.redeem_for_org(
                db, org_id=org.id, user_id=None, promo_code=promo.code, source="dashboard"
            )
        rows = db.execute(
            select(PromoRedemption).where(
                PromoRedemption.promo_offer_id == promo.id,
                PromoRedemption.org_id == org.id,
            )
        ).scalars().all()
        assert len(rows) == 1


def test_charge_launch_is_idempotent_single_debit():
    Session = get_sessionmaker()
    with Session() as db:
        org = Organisation(
            name=f"Launch-{uuid.uuid4().hex[:8]}",
            wallet_balance_pence=50_000,
            contact_email="launch@example.com",
        )
        db.add(org)
        db.flush()
        order = ServiceOrder(
            org_id=org.id,
            user_id=str(uuid.uuid4()),
            service_code="survey",
            title="CAS launch",
            status="draft",
            payment_status="unpaid",
            recipient_count=1,
        )
        db.add(order)
        db.commit()
        db.refresh(order)
        db.refresh(org)

        breakdown = {
            "can_launch": True,
            "currency": "GBP",
            "payment_method": "wallet",
            "wallet_charge_minor": 2500,
            "dd_charge_minor": 0,
            "channel": "whatsapp",
            "units_billable": 1,
        }
        first = LaunchBillingService.charge_launch(db, order, org, breakdown)
        assert first.get("already_charged") is not True
        assert int(first.get("wallet_charged_minor") or 0) == 2500
        db.refresh(org)
        balance_after = int(org.wallet_balance_pence or 0)
        assert balance_after == 47_500

        db.refresh(order)
        second = LaunchBillingService.charge_launch(db, order, org, breakdown)
        assert second.get("already_charged") is True
        db.refresh(org)
        assert int(org.wallet_balance_pence or 0) == balance_after


def test_complete_order_rejects_second_complete():
    Session = get_sessionmaker()
    with Session() as db:
        org = Organisation(name=f"Done-{uuid.uuid4().hex[:8]}")
        db.add(org)
        db.flush()
        order = ServiceOrder(
            org_id=org.id,
            user_id=str(uuid.uuid4()),
            service_code="survey",
            title="Complete CAS",
            status="running",
            payment_status="approved",
        )
        db.add(order)
        db.commit()
        db.refresh(order)

        done = ServiceOrderService.complete_order(db, order)
        assert done.status == "completed"
        with pytest.raises(ValueError, match="Only running"):
            ServiceOrderService.complete_order(db, done)
