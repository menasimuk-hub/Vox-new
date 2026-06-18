"""Tests for Customer Feedback service."""

from __future__ import annotations

import json
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
    assert resolve_session_language(phone="+970597567750", trigger_hint=None) == "ar"
    assert resolve_session_language(phone="970597567750", trigger_hint=None) == "ar"
    assert resolve_session_language(phone="+33612345678", trigger_hint=None) == "fr"
    assert resolve_session_language(phone="+9991234567890", trigger_hint=None, location_country="ae") == "ar"
    assert resolve_session_language(phone="+9991234567890", trigger_hint=None, location_country="gb") == "en_GB"


def test_resolve_template_language_preserves_locale():
    from app.services.customer_feedback.survey_config_service import resolve_template_language

    assert resolve_template_language("fr") == "fr"
    assert resolve_template_language("de") == "de"
    assert resolve_template_language("en_US") == "en_US"
    assert resolve_template_language("ar") == "ar"


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
        assert names == {"Feedback Starter", "Feedback Pro", "Feedback Business"}
        pro = next(item for item in items if item["plan_name"] == "Feedback Pro")
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


def test_activation_enables_customer_feedback_module():
    with get_sessionmaker()() as db:
        email = f"fb-act-{uuid.uuid4().hex[:8]}@example.com"
        org = Organisation(
            name="Feedback Activate Org",
            contact_email=email,
            allowed_services_json='{"customer_feedback": false}',
            enabled_services_json='{"customer_feedback": false}',
        )
        db.add(org)
        db.commit()
        FeedbackSeedService.ensure_seeded(db)
        plan = db.execute(
            select(Plan).where(Plan.code == "cf_starter_gb", Plan.service_kind == FEEDBACK_SERVICE_CODE)
        ).scalar_one()
        sub = Subscription(
            org_id=org.id,
            service_code="voxbulk",
            plan_id=plan.id,
            status="active",
            payment_provider="gocardless",
            current_period_end=datetime.utcnow(),
        )
        db.add(sub)
        db.commit()
        FeedbackBillingService.on_subscription_activated(db, org_id=org.id, subscription=sub, plan=plan)
        db.refresh(org)
        db.refresh(sub)
        assert sub.service_code == FEEDBACK_SERVICE_CODE
        allowed = json.loads(org.allowed_services_json or "{}")
        enabled = json.loads(org.enabled_services_json or "{}")
        assert allowed.get("customer_feedback") is True
        assert enabled.get("customer_feedback") is True
        usage = db.execute(
            select(FeedbackUsagePeriod).where(FeedbackUsagePeriod.org_id == org.id)
        ).scalar_one_or_none()
        assert usage is not None


def test_seed_does_not_clobber_renamed_feedback_plan():
    with get_sessionmaker()() as db:
        FeedbackSeedService.ensure_seeded(db)
        plan = db.execute(
            select(Plan).where(Plan.code == "cf_pro_gb", Plan.service_kind == FEEDBACK_SERVICE_CODE)
        ).scalar_one()
        plan.name = "Custom QR Pro Plan"
        db.add(plan)
        db.commit()
        FeedbackSeedService.ensure_seeded(db)
        db.refresh(plan)
        assert plan.name == "Custom QR Pro Plan"


def test_gocardless_service_code_from_plan_kind():
    from app.services.gocardless_service import BillingService

    feedback_plan = Plan(id="p1", code="cf_starter_gb", name="Feedback Starter", service_kind="customer_feedback")
    vox_plan = Plan(id="p2", code="starter", name="Starter", service_kind="voxbulk")
    assert BillingService._subscription_service_code(plan=feedback_plan, flow_purpose=None) == "customer_feedback"
    assert BillingService._subscription_service_code(plan=vox_plan, flow_purpose="customer_feedback") == "voxbulk"
    assert BillingService._subscription_service_code(plan=vox_plan, flow_purpose=None) == "voxbulk"


def test_is_feedback_intent_message():
    assert FeedbackLocationService.is_feedback_intent_message("Hi! I'd like to share feedback for Acme") is True
    assert FeedbackLocationService.is_feedback_intent_message("Can I share feedback please?") is True
    assert FeedbackLocationService.is_feedback_intent_message("random product name") is False
    assert FeedbackLocationService.is_feedback_intent_message(
        "Hi! I'd like to share feedback for Acme at Branch. acme-branch-a3f2b1"
    ) is False


def test_start_session_sends_whatsapp_with_to_number_kwarg():
    from unittest.mock import MagicMock

    from app.models.customer_feedback import FeedbackLocation, FeedbackWaTemplate
    from app.services.customer_feedback.feedback_wa_send_service import FeedbackWaSendService
    from app.services.customer_feedback.whatsapp_service import FeedbackWhatsappService
    from app.services.telnyx_messaging_service import TelnyxMessageResult

    with get_sessionmaker()() as db:
        org_id, _user_id = _seed_org()
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

        industry = db.execute(select(FeedbackIndustry).where(FeedbackIndustry.slug == "restaurant")).scalar_one()
        survey_type = db.execute(
            select(FeedbackSurveyType).where(
                FeedbackSurveyType.industry_id == industry.id,
                FeedbackSurveyType.slug == "food-quality",
            )
        ).scalar_one()
        token = f"acme-downtown-{uuid.uuid4().hex[:6]}"
        location = FeedbackLocation(
            org_id=org_id,
            industry_id=industry.id,
            survey_type_id=survey_type.id,
            name="Downtown",
            qr_token=token,
            wa_sender_country="gb",
            status="active",
        )
        db.add(location)
        db.flush()
        db.add(
            FeedbackWaTemplate(
                survey_type_id=survey_type.id,
                template_key="food_quality",
                language="en_GB",
                body_text="How was the food?",
                is_active=True,
                telnyx_sync_status="approved",
            )
        )
        db.commit()

        send_mock = MagicMock(
            return_value=TelnyxMessageResult(ok=True, status="sent", detail=None, channel="whatsapp")
        )
        original_send = FeedbackWaSendService.send_plain_or_template
        FeedbackWaSendService.send_plain_or_template = staticmethod(send_mock)
        try:
            result = FeedbackWhatsappService.try_handle_inbound(
                db,
                from_phone="+447700900123",
                body=f"Hi! I'd like to share feedback for Acme at Downtown. {token}",
                org_id="wrong-org-id-for-webhook",
            )
        finally:
            FeedbackWaSendService.send_plain_or_template = original_send

        assert result.get("handled") is True
        assert result.get("session_id")
        assert result.get("org_id") == org_id
        send_mock.assert_called()
        kwargs = send_mock.call_args.kwargs
        assert kwargs.get("to_number") == "+447700900123"
        assert kwargs.get("tpl") is not None
        assert kwargs.get("location") is not None


def test_share_feedback_without_token_replies_helpfully():
    from unittest.mock import MagicMock

    from app.services.customer_feedback.feedback_wa_send_service import FeedbackWaSendService
    from app.services.customer_feedback.location_service import SCAN_QR_HINT
    from app.services.customer_feedback.whatsapp_service import FeedbackWhatsappService
    from app.services.telnyx_messaging_service import TelnyxMessageResult

    with get_sessionmaker()() as db:
        org_id, _user_id = _seed_org()
        send_mock = MagicMock(
            return_value=TelnyxMessageResult(ok=True, status="sent", detail=None, channel="whatsapp")
        )
        original_send = FeedbackWaSendService.send_plain_or_template
        FeedbackWaSendService.send_plain_or_template = staticmethod(send_mock)
        try:
            result = FeedbackWhatsappService.try_handle_inbound(
                db,
                from_phone="+447700900456",
                body="Hi! I'd like to share feedback for my visit",
                org_id=org_id,
            )
        finally:
            FeedbackWaSendService.send_plain_or_template = original_send

        assert result.get("handled") is True
        assert result.get("reason") == "missing_token"
        send_mock.assert_called_once()
        assert send_mock.call_args.kwargs.get("body") == SCAN_QR_HINT
        assert send_mock.call_args.kwargs.get("tpl") is None


def test_send_feedback_template_uses_meta_template_name():
    from unittest.mock import MagicMock

    from app.models.customer_feedback import FeedbackWaTemplate
    from app.services.customer_feedback.feedback_wa_send_service import FeedbackWaSendService
    from app.services.telnyx_messaging_service import TelnyxMessageResult, TelnyxMessagingService

    with get_sessionmaker()() as db:
        tpl = FeedbackWaTemplate(
            template_key="thank_you",
            language="en_GB",
            body_text="Thank you for your feedback.",
            is_active=True,
            telnyx_sync_status="approved",
        )
        db.add(tpl)
        db.commit()
        db.refresh(tpl)

        send_mock = MagicMock(
            return_value=TelnyxMessageResult(ok=True, status="sent", detail=None, channel="whatsapp")
        )
        original_send = TelnyxMessagingService.send_whatsapp
        TelnyxMessagingService.send_whatsapp = staticmethod(send_mock)
        try:
            result = FeedbackWaSendService.send_template(
                db,
                to_number="+447700900999",
                org_id="org-1",
                tpl=tpl,
            )
        finally:
            TelnyxMessagingService.send_whatsapp = original_send

        assert result.ok is True
        send_mock.assert_called()
        kwargs = send_mock.call_args.kwargs
        assert kwargs.get("template_name", "").startswith("voxbulk_cf_")
        assert kwargs.get("to_number") == "+447700900999"
        assert kwargs.get("template_language")


def test_fitness_meta_name_uses_template_row_not_location():
    from app.models.customer_feedback import FeedbackIndustry, FeedbackLocation, FeedbackSurveyType, FeedbackWaTemplate
    from app.services.customer_feedback.feedback_wa_send_service import FeedbackWaSendService

    with get_sessionmaker()() as db:
        FeedbackSeedService.ensure_seeded(db)
        fitness = db.execute(select(FeedbackIndustry).where(FeedbackIndustry.slug == "fitness")).scalar_one()
        survey_type = db.execute(
            select(FeedbackSurveyType).where(
                FeedbackSurveyType.industry_id == fitness.id,
                FeedbackSurveyType.slug == "overall-experience",
            )
        ).scalar_one()
        thank_tpl = FeedbackWaTemplate(
            template_key="thank_you",
            language="en_GB",
            body_text="Thank you!",
            is_active=True,
            telnyx_sync_status="approved",
        )
        db.add(thank_tpl)
        org_id, _user_id = _seed_org()
        location = FeedbackLocation(
            org_id=org_id,
            industry_id=fitness.id,
            survey_type_id=survey_type.id,
            name="Gym",
            qr_token=f"fitness-gym-{uuid.uuid4().hex[:6]}",
            wa_sender_country="gb",
            status="active",
        )
        db.add(location)
        db.commit()
        db.refresh(thank_tpl)

        meta_name = FeedbackWaSendService.resolve_meta_template_name(db, thank_tpl)
        assert meta_name.startswith("voxbulk_cf_thank_you_")
        assert "fitness" not in meta_name
        assert "overall" not in meta_name


def test_load_survey_config_rebuilds_from_flags_when_json_missing():
    from app.models.customer_feedback import FeedbackIndustry, FeedbackLocation, FeedbackSurveyType
    from app.services.customer_feedback.survey_config_service import (
        build_survey_config,
        load_survey_config,
        survey_config_needs_rebuild,
    )

    with get_sessionmaker()() as db:
        FeedbackSeedService.ensure_seeded(db)
        industry = db.execute(select(FeedbackIndustry).where(FeedbackIndustry.slug == "restaurant")).scalar_one()
        types = list(
            db.execute(
                select(FeedbackSurveyType)
                .where(FeedbackSurveyType.industry_id == industry.id)
                .order_by(FeedbackSurveyType.sort_order)
                .limit(2)
            ).scalars().all()
        )
        assert len(types) >= 2
        now = datetime.utcnow()
        org_id, _ = _seed_org()
        loc = FeedbackLocation(
            id=str(uuid.uuid4()),
            org_id=org_id,
            industry_id=industry.id,
            survey_type_id=types[0].id,
            selected_survey_type_ids_json=json.dumps([types[0].id, types[1].id]),
            open_question_enabled=True,
            marketing_opt_in_enabled=True,
            survey_config_json=None,
            name="Legacy",
            qr_token=f"legacy-{uuid.uuid4().hex[:8]}",
            wa_sender_country="gb",
            status="active",
            created_at=now,
            updated_at=now,
        )
        db.add(loc)
        db.commit()

        assert survey_config_needs_rebuild(loc, None) is True
        config = load_survey_config(db, loc)
        kinds = [step["kind"] for step in config["steps"]]
        assert kinds == ["topic", "topic", "open_question", "marketing_opt_in"]
        assert "thank_you" not in kinds


def test_build_survey_config_excludes_thank_you_step():
    from app.models.customer_feedback import FeedbackIndustry, FeedbackSurveyType
    from app.services.customer_feedback.survey_config_service import build_survey_config

    with get_sessionmaker()() as db:
        FeedbackSeedService.ensure_seeded(db)
        industry = db.execute(select(FeedbackIndustry).where(FeedbackIndustry.slug == "fitness")).scalar_one()
        survey_type = db.execute(
            select(FeedbackSurveyType).where(FeedbackSurveyType.industry_id == industry.id).limit(1)
        ).scalar_one()
        config = build_survey_config(
            db,
            industry_id=industry.id,
            selected_type_ids=[survey_type.id],
            open_question_enabled=True,
            marketing_opt_in_enabled=False,
        )
        kinds = [step["kind"] for step in config["steps"]]
        assert kinds == ["topic", "open_question"]
        assert "thank_you" not in kinds


def test_repair_survey_config_persists_rebuilt_json():
    from app.models.customer_feedback import FeedbackIndustry, FeedbackLocation, FeedbackSurveyType
    from app.services.customer_feedback.survey_config_service import repair_survey_config_if_needed

    with get_sessionmaker()() as db:
        FeedbackSeedService.ensure_seeded(db)
        org_id, _ = _seed_org()
        industry = db.execute(select(FeedbackIndustry).where(FeedbackIndustry.slug == "salon")).scalar_one()
        survey_type = db.execute(
            select(FeedbackSurveyType).where(FeedbackSurveyType.industry_id == industry.id).limit(1)
        ).scalar_one()
        loc = FeedbackLocation(
            id=str(uuid.uuid4()),
            org_id=org_id,
            industry_id=industry.id,
            survey_type_id=survey_type.id,
            selected_survey_type_ids_json=json.dumps([survey_type.id]),
            open_question_enabled=True,
            marketing_opt_in_enabled=True,
            survey_config_json=None,
            name="Repair me",
            qr_token=f"repair-{uuid.uuid4().hex[:8]}",
            wa_sender_country="gb",
            status="active",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(loc)
        db.commit()

        assert repair_survey_config_if_needed(db, loc) is True
        db.refresh(loc)
        parsed = json.loads(loc.survey_config_json or "{}")
        kinds = [step["kind"] for step in parsed.get("steps", [])]
        assert "open_question" in kinds
        assert "marketing_opt_in" in kinds
        assert "thank_you" not in kinds


def test_update_location_rebuilds_survey_config():
    from app.models.customer_feedback import FeedbackIndustry, FeedbackLocation, FeedbackSurveyType, FeedbackWaSender
    from app.services.customer_feedback.survey_config_service import build_survey_config

    with get_sessionmaker()() as db:
        FeedbackSeedService.ensure_seeded(db)
        org_id, _ = _seed_org()
        sender = db.execute(
            select(FeedbackWaSender).where(FeedbackWaSender.country_code == "gb")
        ).scalar_one_or_none()
        if sender is None:
            db.add(
                FeedbackWaSender(
                    id=str(uuid.uuid4()),
                    country_code="gb",
                    phone_e164="+447700900111",
                    is_active=True,
                    created_at=datetime.utcnow(),
                )
            )
        else:
            sender.phone_e164 = "+447700900111"
            db.add(sender)
        db.commit()
        industry = db.execute(select(FeedbackIndustry).where(FeedbackIndustry.slug == "hotel")).scalar_one()
        types = list(
            db.execute(
                select(FeedbackSurveyType)
                .where(FeedbackSurveyType.industry_id == industry.id)
                .order_by(FeedbackSurveyType.sort_order)
                .limit(2)
            ).scalars().all()
        )
        initial_config = build_survey_config(
            db,
            industry_id=industry.id,
            selected_type_ids=[types[0].id],
            open_question_enabled=False,
            marketing_opt_in_enabled=False,
        )
        qr_token = f"hotel-lobby-{uuid.uuid4().hex[:6]}"
        row = FeedbackLocation(
            id=str(uuid.uuid4()),
            org_id=org_id,
            industry_id=industry.id,
            survey_type_id=types[0].id,
            selected_survey_type_ids_json=json.dumps([types[0].id]),
            open_question_enabled=False,
            marketing_opt_in_enabled=False,
            survey_config_json=json.dumps(initial_config),
            name="Lobby",
            qr_token=qr_token,
            wa_sender_country="gb",
            status="active",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(row)
        db.commit()

        updated = FeedbackLocationService.update_location(
            db,
            org_id,
            row.id,
            {
                "selected_survey_type_ids": [types[0].id, types[1].id],
                "open_question_enabled": True,
                "marketing_opt_in_enabled": True,
            },
        )
        assert updated["open_question_enabled"] is True
        assert updated["marketing_opt_in_enabled"] is True
        assert len(updated.get("selected_survey_type_ids") or []) == 2

        db.refresh(row)
        parsed = json.loads(row.survey_config_json or "{}")
        kinds = [step["kind"] for step in parsed.get("steps", [])]
        assert kinds.count("topic") == 2
        assert "open_question" in kinds
        assert "marketing_opt_in" in kinds
        assert row.qr_token == qr_token
