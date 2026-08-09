"""Customer Feedback unpaid save uses preview status + org-wide 20 demo scans."""

from __future__ import annotations

import uuid
from datetime import datetime
from unittest.mock import patch

import pytest
from sqlalchemy import select

from app.core.database import get_sessionmaker
from app.core.security import hash_password
from app.models.customer_feedback import (
    FEEDBACK_PREVIEW_TESTS_LIMIT,
    FEEDBACK_SERVICE_CODE,
    FeedbackIndustry,
    FeedbackLocation,
    FeedbackPackage,
    FeedbackSurveyType,
    FeedbackUsagePeriod,
)
from app.models.membership import OrganisationMembership
from app.models.organisation import Organisation
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.models.user import User
from app.services.customer_feedback.billing_service import FeedbackBillingService
from app.services.customer_feedback.location_service import FeedbackLocationService
from app.services.customer_feedback.seed_service import FeedbackSeedService


@pytest.fixture(scope="module", autouse=True)
def _prepare_db():
    from app.core.database import Base, get_engine
    import app.models  # noqa: F401

    engine = get_engine()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def _seed_org() -> str:
    with get_sessionmaker()() as db:
        email = f"cf-sub-{uuid.uuid4().hex[:8]}@example.com"
        org = Organisation(
            name="CF Sub Org",
            contact_email=email,
            allowed_services_json='{"customer_feedback": true}',
        )
        db.add(org)
        db.flush()
        user = User(email=email, password_hash=hash_password("pass123"), is_active=True)
        db.add(user)
        db.flush()
        db.add(OrganisationMembership(org_id=org.id, user_id=user.id))
        db.commit()
        return org.id


def _industry_and_type(db) -> tuple[str, str]:
    FeedbackSeedService.ensure_seeded(db)
    industry = db.execute(select(FeedbackIndustry).where(FeedbackIndustry.slug == "restaurant")).scalar_one()
    survey_type = db.execute(
        select(FeedbackSurveyType)
        .where(FeedbackSurveyType.industry_id == industry.id)
        .order_by(FeedbackSurveyType.sort_order)
        .limit(1)
    ).scalar_one()
    return industry.id, survey_type.id


def test_entitlement_preview_without_subscription():
    org_id = _seed_org()
    with get_sessionmaker()() as db:
        assert FeedbackBillingService.access_mode(db, org_id) == "preview"
        payload = FeedbackBillingService.entitlement_payload(db, org_id)
        assert payload["mode"] == "preview"
        assert payload["preview_tests_limit"] == FEEDBACK_PREVIEW_TESTS_LIMIT
        assert payload["preview_tests_used"] == 0
        assert payload["preview_tests_remaining"] == FEEDBACK_PREVIEW_TESTS_LIMIT


def test_create_location_without_subscription_saves_preview():
    org_id = _seed_org()
    with get_sessionmaker()() as db:
        industry_id, type_id = _industry_and_type(db)
        with (
            patch(
                "app.services.customer_feedback.location_service.validate_feedback_survey_templates_ready",
                return_value=[],
            ),
            patch(
                "app.services.customer_feedback.location_service.resolve_feedback_wa_phone_for_qr",
                return_value="+447700900099",
            ),
        ):
            item = FeedbackLocationService.create_location(
                db,
                org_id,
                {
                    "industry_id": industry_id,
                    "selected_survey_type_ids": [type_id],
                    "name": "Main branch",
                    "open_question_enabled": False,
                    "marketing_opt_in_enabled": False,
                },
            )
        assert item["status"] == "preview"
        mode, err = FeedbackLocationService.gate_session_start(db, db.get(FeedbackLocation, item["id"]))
        assert mode == "preview"
        assert err is None


def test_preview_gate_blocks_after_demo_limit():
    org_id = _seed_org()
    with get_sessionmaker()() as db:
        industry_id, type_id = _industry_and_type(db)
        org = db.get(Organisation, org_id)
        org.feedback_preview_tests_used = FEEDBACK_PREVIEW_TESTS_LIMIT
        db.add(org)
        now = datetime.utcnow()
        loc = FeedbackLocation(
            id=str(uuid.uuid4()),
            org_id=org_id,
            industry_id=industry_id,
            survey_type_id=type_id,
            name="QR",
            qr_token=f"gate-{uuid.uuid4().hex[:12]}",
            wa_sender_country="gb",
            status="preview",
            created_at=now,
            updated_at=now,
        )
        db.add(loc)
        db.commit()
        mode, err = FeedbackLocationService.gate_session_start(db, loc)
        assert mode is None
        assert err and "Demo testing limit" in err
        db.refresh(loc)
        assert loc.status == "preview_exhausted"


def test_gate_blocks_active_without_live_subscription():
    org_id = _seed_org()
    with get_sessionmaker()() as db:
        industry_id, type_id = _industry_and_type(db)
        now = datetime.utcnow()
        loc = FeedbackLocation(
            id=str(uuid.uuid4()),
            org_id=org_id,
            industry_id=industry_id,
            survey_type_id=type_id,
            name="QR",
            qr_token=f"gate-{uuid.uuid4().hex[:12]}",
            wa_sender_country="gb",
            status="active",
            created_at=now,
            updated_at=now,
        )
        db.add(loc)
        db.commit()
        mode, err = FeedbackLocationService.gate_session_start(db, loc)
        assert mode is None
        assert err and "Subscribe" in err


def test_live_subscription_consumes_units():
    org_id = _seed_org()
    with get_sessionmaker()() as db:
        FeedbackSeedService.ensure_seeded(db)
        industry_id, type_id = _industry_and_type(db)
        plan = db.execute(
            select(Plan).where(Plan.code == "cf_starter_gb", Plan.service_kind == FEEDBACK_SERVICE_CODE)
        ).scalar_one()
        pkg = db.execute(select(FeedbackPackage).where(FeedbackPackage.plan_id == plan.id)).scalar_one()
        sub = Subscription(
            org_id=org_id,
            service_code=FEEDBACK_SERVICE_CODE,
            plan_id=plan.id,
            status="active",
            payment_provider="gocardless",
            current_period_end=datetime.utcnow(),
        )
        db.add(sub)
        db.flush()
        period = FeedbackUsagePeriod(
            id=str(uuid.uuid4()),
            org_id=org_id,
            subscription_id=sub.id,
            period_start=datetime.utcnow(),
            period_end=datetime.utcnow(),
            wa_units_included=int(pkg.wa_units_included),
            wa_units_used=0,
            web_units_included=int(pkg.web_units_included or 0),
            web_units_used=0,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(period)
        now = datetime.utcnow()
        loc = FeedbackLocation(
            id=str(uuid.uuid4()),
            org_id=org_id,
            industry_id=industry_id,
            survey_type_id=type_id,
            name="Live QR",
            qr_token=f"live-{uuid.uuid4().hex[:12]}",
            wa_sender_country="gb",
            status="active",
            created_at=now,
            updated_at=now,
        )
        db.add(loc)
        db.commit()

        assert FeedbackBillingService.access_mode(db, org_id) == "live"
        mode, err = FeedbackLocationService.gate_session_start(db, loc)
        assert mode == "live"
        assert err is None
        FeedbackBillingService.consume_unit(db, org_id)
        db.commit()
        period_row = db.get(FeedbackUsagePeriod, period.id)
        assert int(period_row.wa_units_used or 0) == 1


def test_activate_preview_locations_after_pay():
    org_id = _seed_org()
    with get_sessionmaker()() as db:
        FeedbackSeedService.ensure_seeded(db)
        industry_id, type_id = _industry_and_type(db)
        now = datetime.utcnow()
        for i in range(2):
            db.add(
                FeedbackLocation(
                    id=str(uuid.uuid4()),
                    org_id=org_id,
                    industry_id=industry_id,
                    survey_type_id=type_id,
                    name=f"Draft {i}",
                    qr_token=f"draft{i}-{uuid.uuid4().hex[:10]}",
                    wa_sender_country="gb",
                    status="preview",
                    created_at=now,
                    updated_at=now,
                )
            )
        plan = db.execute(
            select(Plan).where(Plan.code == "cf_starter_gb", Plan.service_kind == FEEDBACK_SERVICE_CODE)
        ).scalar_one()
        db.add(
            Subscription(
                org_id=org_id,
                service_code=FEEDBACK_SERVICE_CODE,
                plan_id=plan.id,
                status="active",
                payment_provider="gocardless",
                current_period_end=datetime.utcnow(),
            )
        )
        db.commit()

        result = FeedbackLocationService.activate_preview_locations(db, org_id)
        max_loc = FeedbackBillingService.max_locations(db, org_id)
        assert result["activated"] >= 1
        assert result["activated"] <= max_loc
