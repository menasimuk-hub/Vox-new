"""Tests for dashboard visibility when WA templates are pending or marketing."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

from app.core.database import get_sessionmaker
from app.models.customer_feedback import FeedbackIndustry, FeedbackSurveyType, FeedbackWaTemplate
from app.models.industry import Industry
from app.models.survey_type import SurveyType
from app.models.survey_type_template import SurveyTypeTemplate
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.customer_feedback.catalog_service import FeedbackCatalogService
from app.services.survey_type_service import SurveyTypeService
from app.services.wa_template_dashboard_visibility_service import platform_template_blocks_dashboard


def _session():
    return get_sessionmaker()()


def test_pending_thank_you_not_blocked_for_dashboard():
    row = SimpleNamespace(
        category="UTILITY",
        status="PENDING",
        step_role="completion",
        name="was_system_thank_you_001_en",
        display_name="Thank you",
        template_id=None,
        draft_components_json=None,
        components_json='[{"type":"BODY","text":"Thanks"}]',
    )
    assert platform_template_blocks_dashboard(row) is False


def test_pending_buttoned_welcome_still_blocked():
    row = SimpleNamespace(
        category="UTILITY",
        status="PENDING",
        step_role="start",
        name="was_system_welcome_001_en",
        display_name="Welcome",
        template_id=None,
        draft_components_json=None,
        components_json=(
            '[{"type":"BODY","text":"Hi"},'
            '{"type":"BUTTONS","buttons":[{"type":"QUICK_REPLY","text":"Start survey"}]}]'
        ),
    )
    assert platform_template_blocks_dashboard(row) is True


def test_platform_survey_type_hidden_when_linked_template_pending():
    db = _session()
    try:
        industry = Industry(
            id=str(uuid.uuid4()),
            slug=f"vis-ind-{uuid.uuid4().hex[:6]}",
            name="Visibility Industry",
            is_active=True,
        )
        survey_type = SurveyType(
            id=str(uuid.uuid4()),
            industry_id=industry.id,
            slug=f"topic-{uuid.uuid4().hex[:6]}",
            name="Topic",
            is_active=True,
        )
        approved = TelnyxWhatsappTemplate(
            telnyx_record_id=f"rec-{uuid.uuid4().hex[:8]}",
            template_id=f"tpl-{uuid.uuid4().hex[:8]}",
            name=f"was_{uuid.uuid4().hex[:8]}_standard_en",
            language="en_GB",
            status="APPROVED",
            category="UTILITY",
            active_for_survey=True,
            step_role="rating",
            components_json=(
                '[{"type":"BODY","text":"How was it?"},'
                '{"type":"BUTTONS","buttons":[{"type":"QUICK_REPLY","text":"Good"}]}]'
            ),
        )
        # Buttoned middle question still pending Meta — topic must stay hidden.
        pending = TelnyxWhatsappTemplate(
            telnyx_record_id=f"rec-{uuid.uuid4().hex[:8]}",
            template_id=f"tpl-{uuid.uuid4().hex[:8]}",
            name=f"was_{uuid.uuid4().hex[:8]}_anonymous_en",
            language="en_GB",
            status="PENDING",
            category="UTILITY",
            active_for_survey=True,
            step_role="rating",
            components_json=(
                '[{"type":"BODY","text":"Rate us"},'
                '{"type":"BUTTONS","buttons":[{"type":"QUICK_REPLY","text":"Poor"}]}]'
            ),
        )
        db.add(industry)
        db.add(survey_type)
        db.add(approved)
        db.add(pending)
        db.flush()
        db.add(
            SurveyTypeTemplate(
                industry_id=industry.id,
                survey_type_id=survey_type.id,
                template_id=int(approved.id),
                usable_as_standard=True,
            )
        )
        db.add(
            SurveyTypeTemplate(
                industry_id=industry.id,
                survey_type_id=survey_type.id,
                template_id=int(pending.id),
                usable_as_anonymous=True,
            )
        )
        db.commit()

        visible = SurveyTypeService.list_types(db, industry_id=industry.id, exclude_disabled=True)
        assert all(row["id"] != survey_type.id for row in visible)
    finally:
        db.close()


def test_feedback_survey_type_hidden_when_marketing_pair_pending():
    db = _session()
    try:
        industry = FeedbackIndustry(
            id=str(uuid.uuid4()),
            slug=f"fb-vis-{uuid.uuid4().hex[:6]}",
            name="Feedback Visibility",
            is_active=True,
        )
        survey_type = FeedbackSurveyType(
            id=str(uuid.uuid4()),
            industry_id=industry.id,
            slug=f"overall-{uuid.uuid4().hex[:6]}",
            name="Overall",
            is_active=True,
        )
        utility = FeedbackWaTemplate(
            id=str(uuid.uuid4()),
            industry_id=industry.id,
            survey_type_id=survey_type.id,
            template_key="welcome",
            body_text="Hello",
            meta_category="utility",
            telnyx_sync_status="approved",
            is_active=True,
        )
        marketing = FeedbackWaTemplate(
            id=str(uuid.uuid4()),
            industry_id=industry.id,
            survey_type_id=survey_type.id,
            template_key="marketing_opt_in",
            body_text="Opt in",
            meta_category="marketing",
            telnyx_sync_status="pending",
            is_active=True,
        )
        db.add(industry)
        db.add(survey_type)
        db.add(utility)
        db.add(marketing)
        db.commit()

        visible = FeedbackCatalogService.list_survey_types(
            db,
            industry_id=industry.id,
            exclude_disabled=True,
        )
        assert all(row["id"] != survey_type.id for row in visible)
    finally:
        db.close()
