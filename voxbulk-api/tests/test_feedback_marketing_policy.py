"""Tests for Meta marketing WA template blocklist."""

from __future__ import annotations

import json
import uuid
from datetime import datetime

import pytest
from sqlalchemy import select

from app.core.database import get_sessionmaker
from app.models.customer_feedback import FeedbackIndustry, FeedbackSurveyType, FeedbackWaTemplate
from app.services.customer_feedback.catalog_service import FeedbackCatalogService
from app.services.customer_feedback.feedback_marketing_policy import (
    _collect_blocked_feedback_template_ids,
    apply_platform_wa_marketing_blocks,
    assert_whatsapp_template_send_allowed,
    blocked_meta_template_names,
    is_blocked_meta_template_name,
    set_feedback_survey_type_active,
)


@pytest.fixture(scope="module", autouse=True)
def _prepare_db():
    from sqlalchemy import inspect, text

    from app.core.database import Base, get_engine
    import app.models  # noqa: F401

    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    insp = inspect(engine)
    if "feedback_survey_types" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("feedback_survey_types")}
        if "wa_platform_block_exempt" not in cols:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE feedback_survey_types "
                        "ADD COLUMN wa_platform_block_exempt BOOLEAN NOT NULL DEFAULT 0"
                    )
                )


def test_blocklist_has_53_names():
    names = blocked_meta_template_names()
    assert len(names) == 53
    assert is_blocked_meta_template_name("voxbulk_survey_would_recommend_abc_9c83ff")
    assert not is_blocked_meta_template_name("voxbulk_cf_hotel_not_on_list_xyz")


def test_assert_whatsapp_template_send_allowed_blocks_listed_name():
    blocked = next(iter(blocked_meta_template_names()))
    assert assert_whatsapp_template_send_allowed(template_name=blocked) is not None
    assert assert_whatsapp_template_send_allowed(template_name="voxbulk_cf_allowed_template") is None


def test_arabic_template_paired_when_english_blocklisted(monkeypatch):
    with get_sessionmaker()() as db:
        industry = FeedbackIndustry(
            id=str(uuid.uuid4()),
            slug=f"test-ind-{uuid.uuid4().hex[:6]}",
            name="Test Industry",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(industry)
        db.flush()
        survey_type = FeedbackSurveyType(
            id=str(uuid.uuid4()),
            industry_id=industry.id,
            slug="service_speed",
            name="Service speed",
            is_active=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(survey_type)
        db.flush()

        en_tpl = FeedbackWaTemplate(
            id=str(uuid.uuid4()),
            industry_id=industry.id,
            survey_type_id=survey_type.id,
            template_key="service_speed",
            step_role="topic",
            step_order=1,
            language="en_GB",
            body_text="How was service speed?",
            meta_category="utility",
            is_active=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        ar_tpl = FeedbackWaTemplate(
            id=str(uuid.uuid4()),
            industry_id=industry.id,
            survey_type_id=survey_type.id,
            template_key="service_speed",
            step_role="topic",
            step_order=1,
            language="ar",
            body_text="كيف كانت سرعة الخدمة؟",
            meta_category="utility",
            is_active=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add_all([en_tpl, ar_tpl])
        db.commit()

        blocked_name = "voxbulk_cf_fitness_service_speed_service_speed_6206e653"

        def _meta(_db, row):
            if str(row.id) == str(en_tpl.id):
                return blocked_name
            return "voxbulk_cf_fitness_service_speed_service_speed_ar_pair"

        monkeypatch.setattr(
            "app.services.customer_feedback.feedback_marketing_policy.feedback_template_meta_name_for_row",
            _meta,
        )

        blocked_ids = _collect_blocked_feedback_template_ids(db)
        assert str(en_tpl.id) in blocked_ids
        assert str(ar_tpl.id) in blocked_ids


def test_customer_catalog_hides_disabled_survey_types():
    with get_sessionmaker()() as db:
        industry = FeedbackIndustry(
            id=str(uuid.uuid4()),
            slug=f"cat-ind-{uuid.uuid4().hex[:6]}",
            name="Catalog Industry",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(industry)
        db.flush()
        active_type = FeedbackSurveyType(
            id=str(uuid.uuid4()),
            industry_id=industry.id,
            slug="active_topic",
            name="Active topic",
            is_active=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        disabled_type = FeedbackSurveyType(
            id=str(uuid.uuid4()),
            industry_id=industry.id,
            slug="disabled_topic",
            name="Disabled topic",
            is_active=False,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add_all([active_type, disabled_type])
        db.flush()
        db.add(
            FeedbackWaTemplate(
                id=str(uuid.uuid4()),
                industry_id=industry.id,
                survey_type_id=active_type.id,
                template_key="active_topic",
                step_role="topic",
                step_order=1,
                language="en_GB",
                body_text="Active?",
                meta_category="utility",
                is_active=True,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
        )
        db.commit()

        customer_items = FeedbackCatalogService.list_survey_types(
            db, industry_id=industry.id, customer_facing=True
        )
        customer_ids = {item["id"] for item in customer_items}
        assert active_type.id in customer_ids
        assert disabled_type.id not in customer_ids


def test_set_feedback_survey_type_active_toggles_templates():
    with get_sessionmaker()() as db:
        industry = FeedbackIndustry(
            id=str(uuid.uuid4()),
            slug=f"toggle-ind-{uuid.uuid4().hex[:6]}",
            name="Toggle Industry",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(industry)
        db.flush()
        survey_type = FeedbackSurveyType(
            id=str(uuid.uuid4()),
            industry_id=industry.id,
            slug="toggle_topic",
            name="Toggle topic",
            is_active=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(survey_type)
        db.flush()
        tpl = FeedbackWaTemplate(
            id=str(uuid.uuid4()),
            industry_id=industry.id,
            survey_type_id=survey_type.id,
            template_key="toggle_topic",
            step_role="topic",
            step_order=1,
            language="en_GB",
            body_text="Toggle?",
            meta_category="utility",
            is_active=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(tpl)
        db.commit()

        set_feedback_survey_type_active(db, survey_type.id, active=False)
        db.refresh(survey_type)
        db.refresh(tpl)
        assert survey_type.is_active is False
        assert tpl.is_active is False

        set_feedback_survey_type_active(db, survey_type.id, active=True)
        db.refresh(survey_type)
        db.refresh(tpl)
        assert survey_type.is_active is True
        assert tpl.is_active is True


def test_apply_platform_blocks_seeded_blocklisted_templates():
    with get_sessionmaker()() as db:
        result = apply_platform_wa_marketing_blocks(db)
        assert result["blocklist_size"] == 53
        blocked_tpls = list(
            db.execute(
                select(FeedbackWaTemplate).where(
                    FeedbackWaTemplate.is_active.is_(False),
                    FeedbackWaTemplate.meta_category == "marketing",
                )
            ).scalars().all()
        )
        assert result["feedback_deactivated"] >= 0
        if blocked_tpls:
            assert all(not t.is_active for t in blocked_tpls)


def test_list_customer_catalog_excludes_disabled_type():
    from app.services.customer_feedback.catalog_service import FeedbackCatalogService

    with get_sessionmaker()() as db:
        industry = FeedbackIndustry(
            id=str(uuid.uuid4()),
            slug=f"cat-ind-{uuid.uuid4().hex[:6]}",
            name="Catalog Industry",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(industry)
        db.flush()
        active_type = FeedbackSurveyType(
            id=str(uuid.uuid4()),
            industry_id=industry.id,
            slug="active_topic",
            name="Active topic",
            is_active=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        disabled_type = FeedbackSurveyType(
            id=str(uuid.uuid4()),
            industry_id=industry.id,
            slug="disabled_topic",
            name="Disabled topic",
            is_active=False,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add_all([active_type, disabled_type])
        db.flush()
        db.add(
            FeedbackWaTemplate(
                id=str(uuid.uuid4()),
                industry_id=industry.id,
                survey_type_id=active_type.id,
                template_key="active_topic",
                step_role="topic",
                step_order=1,
                language="en_GB",
                body_text="Active?",
                meta_category="utility",
                is_active=True,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
        )
        db.commit()

        items = FeedbackCatalogService.list_customer_catalog_survey_types(db, industry_id=industry.id)
        ids = {item["id"] for item in items}
        assert active_type.id in ids
        assert disabled_type.id not in ids
        assert all(item.get("customer_selectable") for item in items)


def test_validate_customer_selectable_rejects_disabled_type():
    from app.models.customer_feedback import FeedbackLocation
    from app.models.organisation import Organisation
    from app.services.customer_feedback.catalog_service import FeedbackCatalogService
    from app.services.customer_feedback.location_service import FeedbackLocationService
    from app.services.customer_feedback.survey_config_service import build_survey_config

    with get_sessionmaker()() as db:
        industry = FeedbackIndustry(
            id=str(uuid.uuid4()),
            slug=f"val-ind-{uuid.uuid4().hex[:6]}",
            name="Validate Industry",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(industry)
        db.flush()
        active_type = FeedbackSurveyType(
            id=str(uuid.uuid4()),
            industry_id=industry.id,
            slug="active_topic",
            name="Active topic",
            is_active=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        disabled_type = FeedbackSurveyType(
            id=str(uuid.uuid4()),
            industry_id=industry.id,
            slug="disabled_topic",
            name="Disabled topic",
            is_active=False,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add_all([active_type, disabled_type])
        db.flush()
        db.add(
            FeedbackWaTemplate(
                id=str(uuid.uuid4()),
                industry_id=industry.id,
                survey_type_id=active_type.id,
                template_key="active_topic",
                step_role="topic",
                step_order=1,
                language="en_GB",
                body_text="Active?",
                meta_category="utility",
                is_active=True,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
        )
        org = Organisation(name="Org", contact_email=f"org-{uuid.uuid4().hex[:6]}@example.com")
        db.add(org)
        db.flush()
        loc = FeedbackLocation(
            id=str(uuid.uuid4()),
            org_id=org.id,
            industry_id=industry.id,
            survey_type_id=active_type.id,
            selected_survey_type_ids_json=json.dumps([active_type.id, disabled_type.id]),
            name="Branch",
            qr_token=f"tok-{uuid.uuid4().hex[:8]}",
            wa_sender_country="gb",
            status="active",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(loc)
        db.commit()

        with pytest.raises(ValueError, match="disabled or unavailable"):
            FeedbackCatalogService.validate_customer_selectable_type_ids(
                db,
                industry_id=industry.id,
                type_ids=[disabled_type.id],
            )

        config = build_survey_config(
            db,
            industry_id=industry.id,
            selected_type_ids=[active_type.id, disabled_type.id],
            open_question_enabled=False,
            marketing_opt_in_enabled=False,
        )
        topic_ids = [step["survey_type_id"] for step in config["steps"] if step.get("kind") == "topic"]
        assert topic_ids == [active_type.id]

        updated = FeedbackLocationService.purge_survey_type_from_locations(db, disabled_type.id)
        assert updated == 1
        db.refresh(loc)
        assert json.loads(loc.selected_survey_type_ids_json) == [active_type.id]
