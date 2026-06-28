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
        assert len(first["items"]) == 1

        row_id = first["items"][0]["id"]
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
        row_id = result["items"][0]["id"]
        assert result["items"][0]["target_kind"] == "feedback"

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
        industry = FeedbackIndustry(
            id=str(uuid.uuid4()), slug=f"ind-{uuid.uuid4().hex[:6]}", name="Hide Test Industry", is_active=True
        )
        survey_type = FeedbackSurveyType(
            id=str(uuid.uuid4()),
            industry_id=industry.id,
            slug=f"hidden-topic-{uuid.uuid4().hex[:6]}",
            name="Hidden Topic",
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
        DisabledWaTemplateService.set_disabled(db, result["items"][0]["id"], True)

        # Hidden from the user picker, still present for admin (exclude_disabled=False).
        after_user = FeedbackCatalogService.list_survey_types(db, industry_id=industry.id, exclude_disabled=True)
        assert all(t["id"] != survey_type.id for t in after_user)
        after_admin = FeedbackCatalogService.list_survey_types(db, industry_id=industry.id)
        assert any(t["id"] == survey_type.id for t in after_admin)

        # Re-enabling brings it back for the user.
        DisabledWaTemplateService.set_disabled(db, result["items"][0]["id"], False)
        restored = FeedbackCatalogService.list_survey_types(db, industry_id=industry.id, exclude_disabled=True)
        assert any(t["id"] == survey_type.id for t in restored)
    finally:
        db.close()
