"""Tests for Customer Feedback service."""

from __future__ import annotations

import uuid
from datetime import datetime

import pytest
from sqlalchemy import select

from app.core.database import get_sessionmaker
from app.core.security import hash_password
from app.models.customer_feedback import FEEDBACK_SERVICE_CODE, FeedbackIndustry, FeedbackPackage, FeedbackSurveyType, FeedbackUsagePeriod
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.models.membership import OrganisationMembership
from app.models.organisation import Organisation
from app.models.user import User
from app.services.customer_feedback.billing_service import FeedbackBillingService
from app.services.customer_feedback.catalog_service import FeedbackCatalogService
from app.services.customer_feedback.location_service import FeedbackLocationService
from app.services.customer_feedback.seed_service import FeedbackSeedService


@pytest.fixture(scope="module", autouse=True)
def _prepare_db():
    from app.core.database import Base, get_engine
    import app.models  # noqa: F401

    Base.metadata.create_all(bind=get_engine())


def _seed_org() -> tuple[str, str]:
    with get_sessionmaker()() as db:
        email = f"fb-{uuid.uuid4().hex[:8]}@example.com"
        org = Organisation(name="Feedback Org", contact_email=email, allowed_services_json='{"customer_feedback": true}')
        db.add(org)
        db.flush()
        user = User(email=email, password_hash=hash_password("pass123"), is_active=True)
        db.add(user)
        db.flush()
        db.add(OrganisationMembership(org_id=org.id, user_id=user.id))
        db.commit()
        return org.id, user.id


def test_seed_industries_and_survey_types():
    with get_sessionmaker()() as db:
        FeedbackSeedService.ensure_seeded(db)
        industries = FeedbackCatalogService.list_industries(db, include_inactive=True)
        assert len(industries) >= 7
        restaurant = db.execute(select(FeedbackIndustry).where(FeedbackIndustry.slug == "restaurant")).scalar_one()
        types = FeedbackCatalogService.list_survey_types(db, industry_id=restaurant.id)
        assert len(types) >= 15


def test_parse_trigger_ref():
    token = FeedbackLocationService.parse_trigger_ref(
        "Hi! I'd like to share feedback for Acme Ltd at Marylebone. acme-marylebone-a3f2b1"
    )
    assert token == "acme-marylebone-a3f2b1"
    legacy = FeedbackLocationService.parse_trigger_ref("Hello [ref:abc123-token]")
    assert legacy == "abc123-token"
    with_ar = FeedbackLocationService.parse_trigger_ref(
        "Hi! I'd like to share feedback for Acme at Branch. acme-branch-a3f2b1 (ar)"
    )
    assert with_ar == "acme-branch-a3f2b1"


def test_parse_trigger_language_hint():
    assert FeedbackLocationService.parse_trigger_language_hint(
        "Hi! feedback acme-branch-a3f2b1 (ar)"
    ) == "ar"
    assert FeedbackLocationService.parse_trigger_language_hint(
        "Hi! feedback acme-branch-a3f2b1 (EN_GB)"
    ) == "en_gb"
    assert FeedbackLocationService.parse_trigger_language_hint("no hint here") is None


def test_resolve_session_language():
    from app.services.customer_feedback.locale_service import resolve_session_language

    assert resolve_session_language(phone="+447700900000", trigger_hint="ar") == "ar"
    assert resolve_session_language(phone="+966501234567", trigger_hint=None) == "ar"
    assert resolve_session_language(phone="+447700900000", trigger_hint=None) == "en_GB"


def test_template_for_step_prefers_arabic():
    import json
    import uuid
    from datetime import datetime

    from app.models.customer_feedback import FeedbackIndustry, FeedbackLocation, FeedbackSurveyType, FeedbackWaTemplate
    from app.services.customer_feedback.survey_config_service import template_for_step

    with get_sessionmaker()() as db:
        FeedbackSeedService.ensure_seeded(db)
        industry = db.execute(
            select(FeedbackIndustry).where(FeedbackIndustry.slug == "fitness")
        ).scalar_one()
        survey_type = db.execute(
            select(FeedbackSurveyType)
            .where(FeedbackSurveyType.industry_id == industry.id)
            .order_by(FeedbackSurveyType.sort_order)
            .limit(1)
        ).scalar_one()
        now = datetime.utcnow()
        db.add(
            FeedbackWaTemplate(
                id=str(uuid.uuid4()),
                industry_id=industry.id,
                survey_type_id=survey_type.id,
                step_order=1,
                template_key=survey_type.slug,
                body_text="مرحبا",
                buttons_json=json.dumps(["ممتاز", "جيد", "ضعيف"]),
                step_role="rating",
                language="ar",
                meta_category="utility",
                telnyx_sync_status="draft",
                is_active=True,
                created_at=now,
                updated_at=now,
            )
        )
        org_id, _ = _seed_org()
        loc = FeedbackLocation(
            id=str(uuid.uuid4()),
            org_id=org_id,
            industry_id=industry.id,
            survey_type_id=survey_type.id,
            name="Main",
            qr_token=f"test-gym-{uuid.uuid4().hex[:12]}",
            wa_sender_country="gb",
            status="active",
            created_at=now,
            updated_at=now,
        )
        db.add(loc)
        db.commit()
        tpl = template_for_step(
            db,
            loc,
            {"kind": "topic", "survey_type_id": survey_type.id},
            language="ar",
        )
        assert tpl is not None
        assert tpl.language == "ar"
        assert "مرحبا" in tpl.body_text


def test_map_arabic_button_to_english_for_branching():
    import json
    import uuid
    from datetime import datetime

    from app.models.customer_feedback import FeedbackIndustry, FeedbackSurveyType, FeedbackWaTemplate
    from app.services.customer_feedback.feedback_answer_service import (
        is_negative_topic_answer,
        map_answer_to_english_label,
    )

    with get_sessionmaker()() as db:
        FeedbackSeedService.ensure_seeded(db)
        industry = db.execute(
            select(FeedbackIndustry).where(FeedbackIndustry.slug == "fitness")
        ).scalar_one()
        survey_type = db.execute(
            select(FeedbackSurveyType)
            .where(FeedbackSurveyType.industry_id == industry.id)
            .order_by(FeedbackSurveyType.sort_order)
            .limit(1)
        ).scalar_one()
        now = datetime.utcnow()
        en_tpl = FeedbackWaTemplate(
            id=str(uuid.uuid4()),
            industry_id=industry.id,
            survey_type_id=survey_type.id,
            step_order=1,
            template_key=survey_type.slug,
            body_text="How was your visit?",
            buttons_json=json.dumps(["Excellent", "Good", "Poor"]),
            step_role="rating",
            language="en_GB",
            meta_category="utility",
            telnyx_sync_status="draft",
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        ar_tpl = FeedbackWaTemplate(
            id=str(uuid.uuid4()),
            industry_id=industry.id,
            survey_type_id=survey_type.id,
            step_order=1,
            template_key=survey_type.slug,
            body_text="كيف كانت زيارتك؟",
            buttons_json=json.dumps(["ممتاز", "جيد", "ضعيف"]),
            step_role="rating",
            language="ar",
            meta_category="utility",
            telnyx_sync_status="draft",
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        db.add(en_tpl)
        db.add(ar_tpl)
        db.commit()
        mapped = map_answer_to_english_label(
            db,
            answer="ضعيف",
            tpl=ar_tpl,
            detected_language="ar",
        )
        assert mapped == "poor"
        assert is_negative_topic_answer(
            db,
            answer="ضعيف",
            tpl=ar_tpl,
            detected_language="ar",
        )


def test_feedback_meta_name_shared_for_arabic_and_english():
    import uuid
    from datetime import datetime

    from app.models.customer_feedback import FeedbackWaTemplate
    from app.services.customer_feedback.feedback_telnyx_push_service import feedback_meta_template_name

    en_id = str(uuid.uuid4())
    ar_id = str(uuid.uuid4())
    en = FeedbackWaTemplate(
        id=en_id,
        template_key="overall-experience",
        body_text="Hello",
        language="en_GB",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    ar = FeedbackWaTemplate(
        id=ar_id,
        template_key="overall-experience",
        body_text="مرحبا",
        language="ar",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    en_name = feedback_meta_template_name(
        en, industry_slug="fitness", survey_type_slug="overall-experience", name_anchor_id=en_id
    )
    ar_name = feedback_meta_template_name(
        ar, industry_slug="fitness", survey_type_slug="overall-experience", name_anchor_id=en_id
    )
    assert en_name == ar_name
    assert en_id.replace("-", "")[:8] in en_name.replace("_", "")


def test_finalize_translated_body_keeps_leading_emoji():
    from app.services.customer_feedback.feedback_template_translation_service import finalize_translated_body

    body = finalize_translated_body(
        source_body="💪 Thanks for training with us! How was your visit?",
        translated_body="كيف كانت زيارتك اليوم؟ 💪",
    )
    assert body.startswith("💪")
    assert "💪" not in body[2:]
    assert "كيف" in body


def test_map_remote_meta_status_to_local():
    from app.services.customer_feedback.feedback_telnyx_push_service import map_remote_meta_status_to_local

    assert map_remote_meta_status_to_local("APPROVED") == "approved"
    assert map_remote_meta_status_to_local("PENDING") == "pending"
    assert map_remote_meta_status_to_local("IN_APPEAL") == "pending"
    assert map_remote_meta_status_to_local("REJECTED") == "rejected"
    assert map_remote_meta_status_to_local("PAUSED") == "paused"
    assert map_remote_meta_status_to_local("SUBMITTED") == "submitted"
    assert map_remote_meta_status_to_local(None) == "draft"


def test_trigger_template_format():
    from app.services.customer_feedback.location_service import build_trigger_text, build_location_qr_token

    token = build_location_qr_token(company="Acme Ltd", branch="Marylebone")
    assert token.count("-") >= 2
    assert len(token.split("-")[-1]) == 6
    text = build_trigger_text(company="Acme Ltd", branch="Marylebone", token=token)
    assert "Acme Ltd" in text
    assert "Marylebone" in text
    assert token in text
    assert "Ref:" not in text


def test_seed_feedback_packages_all_zones():
    with get_sessionmaker()() as db:
        FeedbackSeedService.ensure_seeded(db)
        packages = list(db.execute(select(FeedbackPackage)).scalars().all())
        zones = {pkg.market_zone for pkg in packages}
        assert zones >= {"gb", "eu", "us", "ca", "au"}
        for zone in ("gb", "eu", "us", "ca", "au"):
            zone_packages = [pkg for pkg in packages if pkg.market_zone == zone]
            assert len(zone_packages) == 3
            units = sorted(pkg.wa_units_included for pkg in zone_packages)
            assert units == [1000, 3000, 10000]


def test_list_packages_for_eu_org():
    org_id, _user_id = _seed_org()
    with get_sessionmaker()() as db:
        org = db.get(Organisation, org_id)
        org.country = "Germany"
        db.commit()
        FeedbackSeedService.ensure_seeded(db)
        items = FeedbackCatalogService.list_packages(db, market_zone="eu", active_only=True)
        assert len(items) == 3
        names = {item["plan_name"] for item in items}
        assert names == {"Starter", "Pro", "Business"}
        pro = next(item for item in items if item["plan_name"] == "Pro")
        assert pro["is_featured"] is True
        assert pro["wa_units_included"] == 3000


def test_feedback_period_renewal_opens_new_usage_period():
    org_id, _user_id = _seed_org()
    with get_sessionmaker()() as db:
        FeedbackSeedService.ensure_seeded(db)
        plan = db.execute(
            select(Plan).where(Plan.code == "cf_starter_gb", Plan.service_kind == FEEDBACK_SERVICE_CODE)
        ).scalar_one()
        sub = Subscription(
            org_id=org_id,
            service_code=FEEDBACK_SERVICE_CODE,
            plan_id=plan.id,
            status="active",
            payment_provider="gocardless",
            current_period_end=datetime.utcnow(),
        )
        db.add(sub)
        db.commit()
        FeedbackBillingService.on_subscription_activated(db, org_id=org_id, subscription=sub, plan=plan)
        from app.services.billing_lifecycle_service import BillingLifecycleService

        BillingLifecycleService._advance_subscription_period(db, sub, plan)
        periods = list(
            db.execute(select(FeedbackUsagePeriod).where(FeedbackUsagePeriod.org_id == org_id)).scalars().all()
        )
        assert len(periods) == 2


def test_fitness_industry_has_twenty_templates_after_import():
    from app.services.customer_feedback.feedback_telnyx_push_service import (
        list_feedback_templates_for_industry,
        push_all_feedback_templates_for_industry,
        resolve_feedback_industry,
    )
    from app.services.customer_feedback.template_import_service import FeedbackTemplateImportService

    with get_sessionmaker()() as db:
        FeedbackSeedService.ensure_seeded(db)
        FeedbackTemplateImportService.import_from_md(db)
        fitness = resolve_feedback_industry(db, industry_slug="fitness")
        templates = [
            tpl
            for tpl in list_feedback_templates_for_industry(db, fitness.id)
            if tpl.language in {"en_GB", "en", "en_US", "en_AU"}
        ]
        assert len(templates) >= 20
        assert len({tpl.survey_type_id for tpl in templates}) == 20
        summary = push_all_feedback_templates_for_industry(db, industry_slug="fitness", dry_run=True)
        assert summary["template_count"] >= 20
        assert summary["pushed"] >= 20
        assert summary["failed"] == 0
