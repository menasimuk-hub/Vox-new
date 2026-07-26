"""Silent Expo 3-day company-email signup trial."""

from __future__ import annotations

import uuid
from datetime import datetime

import pytest
from sqlalchemy import select

from app.core.database import Base, get_engine, get_sessionmaker
from app.models.expo import ExpoBooth, ExpoExhibition, ExpoPackage
from app.models.expo_signup_trial import ExpoCompanyDomainClaim, ExpoSignupEntitlement
from app.models.organisation import Organisation
from app.models.plan import Plan
from app.services.expo.booth_payment_service import ExpoBoothPaymentService
from app.services.expo.company_email import (
    extract_email_domain,
    is_company_email,
    is_free_email_domain,
)
from app.services.expo.expo_signup_trial_service import ExpoSignupTrialService
from app.services.org_enabled_services import org_service_maps


@pytest.fixture(scope="module", autouse=True)
def _prepare_db():
    import app.models  # noqa: F401

    engine = get_engine()
    # Recreate so new Expo columns/tables exist on the shared pytest SQLite file.
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_company_email_helpers():
    assert extract_email_domain("Ada@Acme.com") == "acme.com"
    assert is_free_email_domain("gmail.com")
    assert is_free_email_domain("yahoo.co.uk")
    assert is_free_email_domain("hotmail.fr")
    assert not is_free_email_domain("acme.com")
    assert is_company_email("ops@acme.com")
    assert not is_company_email("ops@gmail.com")
    assert not is_company_email("not-an-email")


def test_gmail_signup_gets_no_grant():
    Session = get_sessionmaker()
    with Session() as db:
        org = Organisation(name=f"FreeMail-{uuid.uuid4().hex[:8]}")
        db.add(org)
        db.flush()
        result = ExpoSignupTrialService.maybe_grant(
            db,
            org=org,
            user_email=f"user-{uuid.uuid4().hex[:6]}@gmail.com",
            user_id=None,
        )
        db.commit()
        assert result["granted"] is False
        assert result["reason"] == "free_or_invalid_email"
        claims = db.execute(select(ExpoCompanyDomainClaim)).scalars().all()
        assert not any(c.org_id == org.id for c in claims)
        ent = ExpoSignupTrialService.get_entitlement(db, org_id=org.id)
        assert ent is None


def test_company_email_grants_and_domain_locked():
    Session = get_sessionmaker()
    domain = f"acme-{uuid.uuid4().hex[:8]}.com"
    with Session() as db:
        org1 = Organisation(name="Acme One")
        db.add(org1)
        db.flush()
        r1 = ExpoSignupTrialService.maybe_grant(
            db,
            org=org1,
            user_email=f"alice@{domain}",
            user_id=None,
        )
        db.commit()
        assert r1["granted"] is True
        assert r1["domain"] == domain

        ent = ExpoSignupTrialService.get_entitlement(db, org_id=org1.id)
        assert ent is not None
        assert int(ent.remaining) == 1
        assert int(ent.duration_days) == 3

        allowed, enabled, visible = org_service_maps(org1, db)
        assert allowed.get("expo") is True
        assert enabled.get("expo") is True
        assert visible.get("expo") is True

        claim = db.execute(
            select(ExpoCompanyDomainClaim).where(ExpoCompanyDomainClaim.email_domain == domain)
        ).scalar_one()
        assert claim.org_id == org1.id

        org2 = Organisation(name="Acme Two")
        db.add(org2)
        db.flush()
        r2 = ExpoSignupTrialService.maybe_grant(
            db,
            org=org2,
            user_email=f"bob@{domain}",
            user_id=None,
        )
        db.commit()
        assert r2["granted"] is False
        assert r2["reason"] == "domain_already_claimed"
        assert ExpoSignupTrialService.get_entitlement(db, org_id=org2.id) is None


def _make_package(db, *, code: str, tier: str, duration_days: int, price_pence: int) -> ExpoPackage:
    now = datetime.utcnow()
    plan = Plan(
        id=str(uuid.uuid4()),
        code=code,
        name=code,
        price_gbp_pence=price_pence,
        interval="one_time",
        service_kind="expo",
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    db.add(plan)
    db.flush()
    pkg = ExpoPackage(
        id=str(uuid.uuid4()),
        plan_id=plan.id,
        market_zone="all",
        tier=tier,
        duration_days=duration_days,
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    db.add(pkg)
    db.flush()
    return pkg


def _make_booth(db, *, org_id: str, package_id: str) -> ExpoBooth:
    now = datetime.utcnow()
    exhibition = ExpoExhibition(
        id=str(uuid.uuid4()),
        org_id=org_id,
        name="Show",
        status="active",
        created_at=now,
        updated_at=now,
    )
    db.add(exhibition)
    db.flush()
    booth = ExpoBooth(
        id=str(uuid.uuid4()),
        org_id=org_id,
        exhibition_id=exhibition.id,
        name="Booth",
        company_display_name="Booth Co",
        booth_code="B1",
        qr_token=f"tok-{uuid.uuid4().hex[:10]}",
        status="active",
        package_id=package_id,
        payment_status="unpaid",
        created_at=now,
        updated_at=now,
    )
    db.add(booth)
    db.flush()
    return booth


def test_day3_checkout_consumes_entitlement_day7_pays(monkeypatch):
    Session = get_sessionmaker()
    domain = f"corp-{uuid.uuid4().hex[:8]}.io"

    monkeypatch.setattr(
        "app.services.expo.booth_payment_service.ExpoBoothService.serialize_booth",
        lambda db, booth: {"id": booth.id, "payment_status": booth.payment_status},
    )

    with Session() as db:
        org = Organisation(name="Corp Expo")
        db.add(org)
        db.flush()
        granted = ExpoSignupTrialService.maybe_grant(
            db, org=org, user_email=f"ceo@{domain}", user_id=None
        )
        assert granted["granted"] is True

        day3 = _make_package(
            db,
            code=f"expo_day3_{uuid.uuid4().hex[:6]}",
            tier="day3",
            duration_days=3,
            price_pence=9900,
        )
        day7 = _make_package(
            db,
            code=f"expo_day7_{uuid.uuid4().hex[:6]}",
            tier="day7",
            duration_days=7,
            price_pence=14900,
        )
        booth3 = _make_booth(db, org_id=org.id, package_id=day3.id)
        db.commit()

        assert ExpoBoothPaymentService.effective_amount_minor(
            db, org=org, booth=booth3, currency="GBP"
        ) == 0

        result = ExpoBoothPaymentService.create_intent(db, org=org, booth=booth3, provider="stripe")
        assert result["paid"] is True
        assert result["provider"] == "signup_trial"
        assert result["amount_minor"] == 0

        db.refresh(booth3)
        assert booth3.payment_status == "paid"
        ent = ExpoSignupTrialService.get_entitlement(db, org_id=org.id)
        assert ent is not None
        assert int(ent.remaining) == 0
        assert ent.consumed_booth_id == booth3.id

        booth7 = _make_booth(db, org_id=org.id, package_id=day7.id)
        db.commit()
        assert ExpoSignupTrialService.has_usable_trial(db, org_id=org.id, booth=booth7) is False
        amount7 = ExpoBoothPaymentService.effective_amount_minor(
            db, org=org, booth=booth7, currency="GBP"
        )
        assert amount7 == 14900
