"""Tests for disabled WA template admin service."""

from __future__ import annotations

import uuid

from app.core.database import get_sessionmaker
from app.models.customer_feedback import FeedbackIndustry, FeedbackSurveyType, FeedbackWaTemplate
from app.models.disabled_wa_template import DisabledWaTemplate
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.disabled_wa_template_service import DisabledWaTemplateService


def _session():
    SessionLocal = get_sessionmaker()
    return SessionLocal()


def test_add_names_dedup_and_disable_platform():
    db = _session()
    try:
        tpl_name = f"voxbulk_survey_test_disable_{uuid.uuid4().hex[:8]}"
        tpl = TelnyxWhatsappTemplate(
            telnyx_record_id=f"rec-{uuid.uuid4().hex[:8]}",
            template_id=f"tpl-{uuid.uuid4().hex[:8]}",
            name=tpl_name,
            language="en_US",
            status="APPROVED",
            active_for_survey=True,
            active_for_interview=True,
            active_for_appointment=True,
        )
        db.add(tpl)
        db.commit()
        db.refresh(tpl)

        first = DisabledWaTemplateService.add_names(db, [tpl_name, tpl_name])
        assert first["added"] == 1
        assert first["duplicates"] == 1
        row = next(item for item in first["items"] if item["raw_name"] == tpl_name)
        row_id = row["id"]
        DisabledWaTemplateService.set_disabled(db, row_id, True)

        db.refresh(tpl)
        assert tpl.active_for_survey is False
        assert tpl.active_for_interview is False
        assert tpl.active_for_appointment is False

        DisabledWaTemplateService.set_disabled(db, row_id, False)
        db.refresh(tpl)
        assert tpl.active_for_survey is True
        assert tpl.active_for_interview is True
        assert tpl.active_for_appointment is True
    finally:
        db.close()


def test_disable_feedback_template():
    db = _session()
    try:
        industry = FeedbackIndustry(
            id=str(uuid.uuid4()),
            slug=f"test-ind-{uuid.uuid4().hex[:6]}",
            name="Test Industry",
            is_active=True,
        )
        survey_type = FeedbackSurveyType(
            id=str(uuid.uuid4()),
            industry_id=industry.id,
            slug=f"overall-{uuid.uuid4().hex[:6]}",
            name="Overall experience",
            is_active=True,
        )
        db.add(industry)
        db.add(survey_type)
        db.flush()

        fb_tpl = FeedbackWaTemplate(
            id=str(uuid.uuid4()),
            industry_id=industry.id,
            survey_type_id=survey_type.id,
            template_key="welcome",
            body_text="Hello",
            is_active=True,
        )
        db.add(fb_tpl)
        db.commit()

        from app.services.customer_feedback.feedback_telnyx_push_service import feedback_meta_template_name

        meta_name = feedback_meta_template_name(
            fb_tpl,
            industry_slug=industry.slug,
            survey_type_slug=survey_type.slug,
            name_anchor_id=fb_tpl.id,
        )

        result = DisabledWaTemplateService.add_names(db, [meta_name])
        assert result["added"] == 1
        row = next(item for item in result["items"] if item["raw_name"] == meta_name)
        row_id = row["id"]
        assert row["target_kind"] == "feedback"

        DisabledWaTemplateService.set_disabled(db, row_id, True)
        db.refresh(fb_tpl)
        assert fb_tpl.is_active is False

        DisabledWaTemplateService.remove(db, row_id)
        db.refresh(fb_tpl)
        assert fb_tpl.is_active is True
        assert db.get(DisabledWaTemplate, row_id) is None
    finally:
        db.close()


def test_disabled_template_hides_survey_type_from_user_picker():
    from app.services.customer_feedback.catalog_service import FeedbackCatalogService
    from app.services.customer_feedback.feedback_telnyx_push_service import feedback_meta_template_name

    db = _session()
    try:
        tag = uuid.uuid4().hex[:8]
        industry = FeedbackIndustry(
            id=str(uuid.uuid4()), slug=f"ind-{tag}", name=f"Hide Test Industry {tag}", is_active=True
        )
        survey_type = FeedbackSurveyType(
            id=str(uuid.uuid4()),
            industry_id=industry.id,
            slug=f"hidden-topic-{tag}",
            name=f"Hidden Topic {tag}",
            is_active=True,
        )
        db.add(industry)
        db.add(survey_type)
        db.flush()
        fb_tpl = FeedbackWaTemplate(
            id=str(uuid.uuid4()),
            industry_id=industry.id,
            survey_type_id=survey_type.id,
            template_key="welcome",
            body_text="Hi",
            is_active=True,
        )
        db.add(fb_tpl)
        db.commit()

        meta_name = feedback_meta_template_name(
            fb_tpl, industry_slug=industry.slug, survey_type_slug=survey_type.slug, name_anchor_id=fb_tpl.id
        )

        # Visible to the user before disabling.
        before = FeedbackCatalogService.list_survey_types(db, industry_id=industry.id, exclude_disabled=True)
        assert any(t["id"] == survey_type.id for t in before)

        result = DisabledWaTemplateService.add_names(db, [meta_name])
        row = next(item for item in result["items"] if item["raw_name"] == meta_name)
        DisabledWaTemplateService.set_disabled(db, row["id"], True)

        # Hidden from the user picker, still present for admin (exclude_disabled=False).
        after_user = FeedbackCatalogService.list_survey_types(db, industry_id=industry.id, exclude_disabled=True)
        assert all(t["id"] != survey_type.id for t in after_user)
        after_admin = FeedbackCatalogService.list_survey_types(db, industry_id=industry.id)
        assert any(t["id"] == survey_type.id for t in after_admin)

        # Re-enabling brings it back for the user.
        DisabledWaTemplateService.set_disabled(db, row["id"], False)
        restored = FeedbackCatalogService.list_survey_types(db, industry_id=industry.id, exclude_disabled=True)
        assert any(t["id"] == survey_type.id for t in restored)
    finally:
        db.close()


def test_real_cf_template_name_hides_topic():
    """Regression: voxbulk_cf names use underscores but catalog slugs use hyphens."""
    from app.services.customer_feedback.catalog_service import FeedbackCatalogService

    db = _session()
    try:
        industry = db.execute(
            __import__("sqlalchemy").select(FeedbackIndustry).where(FeedbackIndustry.slug == "fitness")
        ).scalar_one_or_none()
        assert industry is not None
        survey_type = db.execute(
            __import__("sqlalchemy")
            .select(FeedbackSurveyType)
            .where(FeedbackSurveyType.industry_id == industry.id, FeedbackSurveyType.slug == "would-recommend")
        ).scalar_one_or_none()
        assert survey_type is not None

        template_name = "voxbulk_cf_fitness_would_recommend_would_recommend_aa247a14"
        result = DisabledWaTemplateService.add_names(db, [template_name])
        row = next(item for item in result["items"] if item["raw_name"] == template_name)
        row_id = row["id"]
        DisabledWaTemplateService.set_disabled(db, row_id, True)

        visible = FeedbackCatalogService.list_survey_types(db, industry_id=industry.id, exclude_disabled=True)
        assert all(t["id"] != survey_type.id for t in visible)
        # Admin view (include_archived) still sees the topic — disable only hides it from users.
        admin_view = FeedbackCatalogService.list_survey_types(db, industry_id=industry.id, include_archived=True)
        assert any(t["id"] == survey_type.id for t in admin_view)

        DisabledWaTemplateService.set_disabled(db, row_id, False)
        visible_again = FeedbackCatalogService.list_survey_types(db, industry_id=industry.id, exclude_disabled=True)
        assert any(t["id"] == survey_type.id for t in visible_again)
    finally:
        db.close()


def test_booking_app_experience_slug_variant_hides_topic():
    """Regression: catalog slug booking---app-experience vs template booking_app_experience."""
    from app.services.customer_feedback.catalog_service import FeedbackCatalogService

    db = _session()
    try:
        industry = db.execute(
            __import__("sqlalchemy").select(FeedbackIndustry).where(FeedbackIndustry.slug == "fitness")
        ).scalar_one_or_none()
        assert industry is not None
        survey_type = db.execute(
            __import__("sqlalchemy")
            .select(FeedbackSurveyType)
            .where(
                FeedbackSurveyType.industry_id == industry.id,
                FeedbackSurveyType.slug == "booking---app-experience",
            )
        ).scalar_one_or_none()
        assert survey_type is not None

        template_name = "voxbulk_cf_fitness_booking_app_experience_booking_app_experience_62190a1e"
        result = DisabledWaTemplateService.add_names(db, [template_name])
        row = next(item for item in result["items"] if item["raw_name"] == template_name)
        row_id = row["id"]
        DisabledWaTemplateService.set_disabled(db, row_id, True)

        visible = FeedbackCatalogService.list_survey_types(db, industry_id=industry.id, exclude_disabled=True)
        assert all(t["id"] != survey_type.id for t in visible)
    finally:
        db.close()


def test_disabled_platform_template_hides_wa_survey_type():
    from app.models.industry import Industry
    from app.models.survey_type import SurveyType
    from app.services.survey_type_service import SurveyTypeService

    db = _session()
    try:
        industry = Industry(id=str(uuid.uuid4()), slug=f"ind-{uuid.uuid4().hex[:6]}", name="WA Hide Industry", is_active=True)
        survey_type = SurveyType(
            id=str(uuid.uuid4()),
            industry_id=industry.id,
            slug=f"would_recommend_{uuid.uuid4().hex[:6]}",
            name="Would recommend",
            is_active=True,
        )
        tpl_name = f"voxbulk_survey_{survey_type.slug}_abc_{uuid.uuid4().hex[:6]}"
        tpl = TelnyxWhatsappTemplate(
            telnyx_record_id=f"rec-{uuid.uuid4().hex[:8]}",
            template_id=f"tpl-{uuid.uuid4().hex[:8]}",
            name=tpl_name,
            language="en_US",
            status="APPROVED",
            survey_type_id=survey_type.id,
            industry_id=industry.id,
            active_for_survey=True,
            active_for_interview=False,
            active_for_appointment=False,
        )
        db.add(industry)
        db.add(survey_type)
        db.add(tpl)
        db.commit()

        before = SurveyTypeService.list_types(db, industry_id=industry.id, exclude_disabled=True)
        assert any(t["id"] == survey_type.id for t in before)

        result = DisabledWaTemplateService.add_names(db, [tpl_name])
        row = next(item for item in result["items"] if item["raw_name"] == tpl_name)
        DisabledWaTemplateService.set_disabled(db, row["id"], True)

        after = SurveyTypeService.list_types(db, industry_id=industry.id, exclude_disabled=True)
        assert all(t["id"] != survey_type.id for t in after)
    finally:
        db.close()


def test_clear_all_removes_blocklist():
    db = _session()
    try:
        tpl_name = f"voxbulk_survey_clear_all_{uuid.uuid4().hex[:8]}"
        tpl = TelnyxWhatsappTemplate(
            telnyx_record_id=f"rec-{uuid.uuid4().hex[:8]}",
            template_id=f"tpl-{uuid.uuid4().hex[:8]}",
            name=tpl_name,
            language="en_US",
            status="APPROVED",
            active_for_survey=True,
        )
        db.add(tpl)
        db.commit()

        added = DisabledWaTemplateService.add_names(db, [tpl_name, f"legacy_{uuid.uuid4().hex[:6]}"])
        assert added["added"] >= 2
        row = next(item for item in added["items"] if item["raw_name"] == tpl_name)
        DisabledWaTemplateService.set_disabled(db, row["id"], True)
        db.refresh(tpl)
        assert tpl.active_for_survey is False

        result = DisabledWaTemplateService.clear_all(db)
        assert result["ok"] is True
        assert result["removed"] >= 2
        assert result["items"] == []
        assert db.query(DisabledWaTemplate).count() == 0

        db.refresh(tpl)
        assert tpl.active_for_survey is True
    finally:
        db.close()
