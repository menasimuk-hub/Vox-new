"""Tests for WA template industry export resolver."""
from __future__ import annotations
import uuid
from sqlalchemy import select
from app.models.customer_feedback import FeedbackIndustry, FeedbackSurveyType, FeedbackWaTemplate
from app.models.industry import Industry
from app.models.survey_type import SurveyType
from app.services.customer_feedback.feedback_telnyx_push_service import feedback_meta_template_name
from app.services.wa_template_industry_export_service import (
    build_export_resolver_context,
    parse_feedback_template_name,
    parse_platform_survey_template_name,
    resolve_template_export_rows,
)
def _ensure_feedback_fitness(db):
    ind = db.execute(select(FeedbackIndustry).where(FeedbackIndustry.slug == "fitness")).scalar_one_or_none()
    if ind is None:
        ind = FeedbackIndustry(slug="fitness", name="Fitness", is_active=True, sort_order=1)
        db.add(ind)
        db.flush()
    st = db.execute(
        select(FeedbackSurveyType).where(
            FeedbackSurveyType.industry_id == ind.id,
            FeedbackSurveyType.slug == "would_recommend",
        )
    ).scalar_one_or_none()
    if st is None:
        st = FeedbackSurveyType(industry_id=ind.id, slug="would_recommend", name="Would recommend", is_active=True, sort_order=1)
        db.add(st)
        db.flush()
    tpl = db.execute(
        select(FeedbackWaTemplate).where(
            FeedbackWaTemplate.survey_type_id == st.id,
            FeedbackWaTemplate.template_key == "would_recommend",
            FeedbackWaTemplate.language == "en_GB",
        )
    ).scalar_one_or_none()
    if tpl is None:
        tpl = FeedbackWaTemplate(
            industry_id=ind.id,
            survey_type_id=st.id,
            step_order=1,
            template_key="would_recommend",
            body_text="Would you recommend us?",
            language="en_GB",
            telnyx_sync_status="approved",
            is_active=True,
        )
        db.add(tpl)
    db.commit()
    return ind, st
def _seed_employee_survey_type(db):
    industry = Industry(slug=f"employee_survey_{uuid.uuid4().hex[:6]}", name="Employee Survey", is_active=True)
    db.add(industry)
    db.flush()
    st = SurveyType(industry_id=industry.id, slug="team_collaboration", name="Team collaboration", is_active=True)
    db.add(st)
    db.commit()
    return industry, st
def test_parse_cf_fitness_name():
    from app.core.database import get_sessionmaker
    with get_sessionmaker()() as db:
        _ensure_feedback_fitness(db)
        ctx = build_export_resolver_context(db)
        parsed = parse_feedback_template_name("cfs_fitness_would_recommend_en_v1", ctx)
    assert parsed is not None
    assert parsed["industry_slug"] == "fitness"
    assert parsed["survey_type_slug"] == "would_recommend"


def test_cf_meta_index_matches_feedback_row():
    from app.core.database import get_sessionmaker

    with get_sessionmaker()() as db:
        ind, st = _ensure_feedback_fitness(db)
        tpl = db.execute(
            select(FeedbackWaTemplate).where(
                FeedbackWaTemplate.survey_type_id == st.id,
                FeedbackWaTemplate.template_key == "would_recommend",
                FeedbackWaTemplate.language == "en_GB",
            )
        ).scalar_one()
        ctx = build_export_resolver_context(db)
        meta = feedback_meta_template_name(
            tpl,
            industry_slug=ind.slug,
            survey_type_slug=st.slug,
            name_anchor_id=tpl.id,
        ).lower()
        assert meta in ctx.cf_meta_index
        assert ctx.cf_meta_index[meta]["source"] == "feedback_db"


def test_parse_platform_survey_team_collaboration():
    from app.core.database import get_sessionmaker
    with get_sessionmaker()() as db:
        industry, _st = _seed_employee_survey_type(db)
        ctx = build_export_resolver_context(db)
        parsed = parse_platform_survey_template_name("voxbulk_survey_team_collaboration_abc_6795e3", ctx)
    assert parsed["survey_type_slug"] == "team_collaboration"
    assert parsed["industry_slug"] == industry.slug
def test_resolve_export_rows_mixed_list():
    from app.core.database import get_sessionmaker
    with get_sessionmaker()() as db:
        _ensure_feedback_fitness(db)
        _seed_employee_survey_type(db)
        rows = resolve_template_export_rows(
            db,
            [
                "cfs_fitness_would_recommend_en_v1",
                "voxbulk_survey_team_collaboration_abc_6795e3",
                "voxbulk_survey_would_recommend_abc_9c83ff",
            ],
        )
    assert len(rows) == 3
    assert rows[0]["product_line"] == "Customer Feedback"
    assert rows[1]["survey_type_slug"] == "team_collaboration"
    assert rows[2]["product_line"] == "Platform WA Survey"
