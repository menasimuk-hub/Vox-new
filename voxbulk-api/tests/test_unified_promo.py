"""Unified promo offers — free usage, discounts, redeem modes, multi-org apply."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from app.core.database import Base, get_engine, get_sessionmaker
from app.models.organisation import Organisation
from app.models.plan import Plan
from app.models.promo_offer import PromoOffer, PromoPendingDiscount, PromoRedemption
from app.services.promo_discount_service import PromoDiscountService
from app.services.promo_offer_service import PromoOfferError, PromoOfferService


@pytest.fixture(scope="module", autouse=True)
def _prepare_db():
    import app.models  # noqa: F401

    engine = get_engine()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def _org(db, name: str | None = None) -> Organisation:
    org = Organisation(name=name or f"Org-{uuid.uuid4().hex[:8]}")
    db.add(org)
    db.flush()
    return org


def _starter_plan(db) -> Plan:
    existing = db.execute(select(Plan).where(Plan.code == "starter")).scalar_one_or_none()
    if existing:
        return existing
    now = datetime.utcnow()
    plan = Plan(
        id=str(uuid.uuid4()),
        code="starter",
        name="Starter",
        price_gbp_pence=4900,
        interval="monthly",
        service_kind="voxbulk",
        trial_days_default=14,
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    db.add(plan)
    db.flush()
    return plan


def test_create_survey_free_and_discount():
    Session = get_sessionmaker()
    with Session() as db:
        free = PromoOfferService.create_admin(
            db,
            {
                "service_kind": "survey",
                "benefit_kind": "free_usage",
                "usage_amount": 25,
                "max_redemptions": 5,
                "redeem_mode": "anyone",
            },
        )
        assert free.benefit_kind == "free_usage"
        assert free.service_kind == "survey"
        assert int(free.usage_amount) == 25
        assert "25" in PromoOfferService.benefit_summary(free)

        disc = PromoOfferService.create_admin(
            db,
            {
                "service_kind": "expo",
                "benefit_kind": "discount",
                "discount_type": "percent",
                "discount_value": 50,
                "max_redemptions": 3,
            },
        )
        assert disc.benefit_kind == "discount"
        assert disc.discount_type == "percent"
        assert "50%" in PromoOfferService.benefit_summary(disc)


def test_dashboard_redeem_and_admin_only():
    Session = get_sessionmaker()
    with Session() as db:
        org = _org(db)
        promo = PromoOfferService.create_admin(
            db,
            {
                "service_kind": "interview",
                "benefit_kind": "free_usage",
                "usage_amount": 2,
                "redeem_mode": "admin_only",
                "max_redemptions": 10,
            },
        )
        with pytest.raises(PromoOfferError):
            PromoOfferService.redeem_for_org(
                db, org_id=org.id, user_id=None, promo_code=promo.code, source="dashboard"
            )
        PromoOfferService.redeem_for_org(
            db, org_id=org.id, user_id=None, promo_code=promo.code, source="admin"
        )
        db.refresh(org)
        assert int(org.interview_credits_balance or 0) == 2


def test_multi_org_apply_and_domain_once_per_org():
    Session = get_sessionmaker()
    with Session() as db:
        a = _org(db, "A")
        b = _org(db, "B")
        promo = PromoOfferService.create_admin(
            db,
            {
                "service_kind": "survey",
                "benefit_kind": "free_usage",
                "usage_amount": 5,
                "max_redemptions": 10,
                "redeem_mode": "anyone",
            },
        )
        result = PromoOfferService.apply_to_orgs(db, promo_id=promo.id, org_ids=[a.id, b.id, a.id])
        assert result["applied"] == 2
        assert result["failed"] == 1
        db.refresh(a)
        db.refresh(b)
        assert int(a.survey_credits_balance or 0) == 5
        assert int(b.survey_credits_balance or 0) == 5


def test_discount_pending_consumed_once():
    Session = get_sessionmaker()
    with Session() as db:
        org = _org(db)
        promo = PromoOfferService.create_admin(
            db,
            {
                "service_kind": "expo",
                "benefit_kind": "discount",
                "discount_type": "fixed_minor",
                "discount_value": 2000,
                "max_redemptions": 5,
            },
        )
        PromoOfferService.redeem_for_org(
            db, org_id=org.id, user_id=None, promo_code=promo.code, source="dashboard"
        )
        pending = PromoDiscountService.get_pending(db, org_id=org.id, service_kind="expo")
        assert pending is not None
        first = PromoDiscountService.apply_and_consume(
            db, org_id=org.id, service_kind="expo", amount_minor=9900
        )
        assert first["discount_applied"] is True
        assert first["amount_minor"] == 7900
        second = PromoDiscountService.apply_and_consume(
            db, org_id=org.id, service_kind="expo", amount_minor=9900
        )
        assert second["discount_applied"] is False
        assert second["amount_minor"] == 9900


def test_signup_only_blocks_dashboard():
    Session = get_sessionmaker()
    with Session() as db:
        _starter_plan(db)
        org = _org(db)
        promo = PromoOfferService.create_admin(
            db,
            {
                "service_kind": "voxbulk",
                "benefit_kind": "free_usage",
                "plan_code": "starter",
                "trial_days": 7,
                "redeem_mode": "signup_only",
                "max_redemptions": 5,
            },
        )
        with pytest.raises(PromoOfferError):
            PromoOfferService.redeem_for_org(
                db, org_id=org.id, user_id=None, promo_code=promo.code, source="dashboard"
            )
        PromoOfferService.redeem_for_org(
            db, org_id=org.id, user_id=None, promo_code=promo.code, source="signup"
        )
        redemptions = db.execute(select(PromoRedemption)).scalars().all()
        assert any(r.org_id == org.id and r.promo_offer_id == promo.id for r in redemptions)


def test_feedback_free_units():
    Session = get_sessionmaker()
    with Session() as db:
        org = _org(db)
        promo = PromoOfferService.create_admin(
            db,
            {
                "service_kind": "customer_feedback",
                "benefit_kind": "free_usage",
                "usage_amount": 12,
                "max_redemptions": 2,
            },
        )
        PromoOfferService.redeem_for_org(
            db, org_id=org.id, user_id=None, promo_code=promo.code, source="dashboard"
        )
        db.refresh(org)
        assert int(org.feedback_credits_balance or 0) == 12
