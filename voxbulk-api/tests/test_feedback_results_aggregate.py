"""Tests for Customer Feedback results aggregation."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from app.core.database import get_sessionmaker
from app.core.security import hash_password
from app.models.customer_feedback import (
    FeedbackIndustry,
    FeedbackLocation,
    FeedbackResponse,
    FeedbackSession,
    FeedbackSurveyType,
    FeedbackWaTemplate,
)
from app.models.membership import OrganisationMembership
from app.models.organisation import Organisation
from app.models.user import User
from app.services.customer_feedback.feedback_results_aggregate import (
    build_aggregates,
    build_respondents,
    classify_pge,
    compute_summary,
    load_template_index,
)
from app.services.customer_feedback.results_service import FeedbackResultsService
from app.services.customer_feedback.seed_service import FeedbackSeedService


@pytest.fixture(scope="module", autouse=True)
def _prepare_db():
    from app.core.database import Base, get_engine
    import app.models  # noqa: F401

    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        from sqlalchemy import inspect, text

        insp = inspect(conn)
        cols = {c["name"] for c in insp.get_columns("feedback_responses")}
        if "answer_source" not in cols:
            conn.execute(text("ALTER TABLE feedback_responses ADD COLUMN answer_source VARCHAR(16)"))
        if "feedback_results_insights" not in insp.get_table_names():
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS feedback_results_insights (
                        id VARCHAR(36) PRIMARY KEY,
                        org_id VARCHAR(36) NOT NULL,
                        location_key VARCHAR(64) NOT NULL DEFAULT '__all__',
                        fingerprint VARCHAR(64) NOT NULL DEFAULT '',
                        themes_json TEXT,
                        recommendations_json TEXT,
                        source VARCHAR(32),
                        created_at DATETIME NOT NULL,
                        updated_at DATETIME NOT NULL,
                        UNIQUE (org_id, location_key)
                    )
                    """
                )
            )


def _seed_org_with_feedback() -> tuple[str, FeedbackLocation, FeedbackSurveyType]:
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
        email = f"fb-res-{uuid.uuid4().hex[:8]}@example.com"
        org = Organisation(
            name="Results Org",
            contact_email=email,
            allowed_services_json='{"customer_feedback": true}',
        )
        db.add(org)
        db.flush()
        user = User(email=email, password_hash=hash_password("pass123"), is_active=True)
        db.add(user)
        db.flush()
        db.add(OrganisationMembership(org_id=org.id, user_id=user.id))
        now = datetime.utcnow()
        loc = FeedbackLocation(
            id=str(uuid.uuid4()),
            org_id=org.id,
            industry_id=industry.id,
            survey_type_id=survey_type.id,
            name="Main Gym",
            qr_token=f"gym-{uuid.uuid4().hex[:10]}",
            wa_sender_country="gb",
            status="active",
            scan_count=50,
            created_at=now,
            updated_at=now,
        )
        db.add(loc)
        db.flush()
        tpl = FeedbackWaTemplate(
            id=str(uuid.uuid4()),
            industry_id=industry.id,
            survey_type_id=survey_type.id,
            step_order=1,
            template_key="overall-visit",
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
        db.add(tpl)
        sess = FeedbackSession(
            id=str(uuid.uuid4()),
            org_id=org.id,
            location_id=loc.id,
            visitor_phone="+447700900111",
            status="completed",
            current_step=2,
            detected_language="en_GB",
            started_at=now - timedelta(hours=1),
            completed_at=now,
            created_at=now,
        )
        db.add(sess)
        db.add(
            FeedbackResponse(
                id=str(uuid.uuid4()),
                session_id=sess.id,
                org_id=org.id,
                location_id=loc.id,
                survey_type_id=survey_type.id,
                question_key="overall-visit",
                answer_text="poor",
                answer_text_en="poor",
                original_text="Poor",
                step_order=1,
                created_at=now,
            )
        )
        db.add(
            FeedbackResponse(
                id=str(uuid.uuid4()),
                session_id=sess.id,
                org_id=org.id,
                location_id=loc.id,
                survey_type_id=survey_type.id,
                question_key="tell-us-more",
                answer_text="Waiting area was too crowded",
                answer_text_en="Waiting area was too crowded",
                original_text="Waiting area was too crowded",
                step_order=2,
                answer_source="text",
                created_at=now,
            )
        )
        db.commit()
        return org.id, loc, survey_type


def test_classify_pge():
    assert classify_pge("Excellent") == "excellent"
    assert classify_pge("poor") == "poor"
    assert classify_pge("good") == "good"


def test_build_aggregates_pge_breakdown():
    org_id, loc, survey_type = _seed_org_with_feedback()
    with get_sessionmaker()() as db:
        responses = list(
            db.execute(
                select(FeedbackResponse).where(FeedbackResponse.org_id == org_id)
            ).scalars().all()
        )
        templates = load_template_index(db, survey_type_ids={survey_type.id})
        aggregates = build_aggregates(responses, templates)
        assert aggregates
        rating = next((a for a in aggregates if a.get("step_role") == "rating"), None)
        assert rating is not None
        breakdown = {b["key"]: b for b in rating.get("breakdown") or []}
        assert breakdown.get("poor", {}).get("count", 0) >= 1


def test_unhappy_respondent_flag():
    org_id, loc, survey_type = _seed_org_with_feedback()
    with get_sessionmaker()() as db:
        sessions = list(
            db.execute(select(FeedbackSession).where(FeedbackSession.org_id == org_id)).scalars().all()
        )
        responses = list(
            db.execute(select(FeedbackResponse).where(FeedbackResponse.org_id == org_id)).scalars().all()
        )
        by_session: dict[str, list] = {}
        for r in responses:
            by_session.setdefault(r.session_id, []).append(r)
        templates = load_template_index(db, survey_type_ids={survey_type.id})
        locations = {loc.id: loc}
        respondents = build_respondents(sessions, by_session, templates, locations)
        assert respondents
        assert respondents[0].get("is_unhappy") is True


def test_customer_results_api_shape(monkeypatch):
    org_id, loc, _survey_type = _seed_org_with_feedback()

    def _fake_location_to_dict(_db, row):
        return {"id": row.id, "name": row.name, "scan_count": row.scan_count or 0}

    monkeypatch.setattr(
        "app.services.customer_feedback.results_service.location_to_dict",
        _fake_location_to_dict,
    )
    with get_sessionmaker()() as db:
        payload = FeedbackResultsService.customer_results(db, org_id, location_id=loc.id)
        assert payload.get("ok") is True
        assert "aggregates" in payload
        assert "respondents" in payload
        assert "weekly_trend" in payload
        assert payload["summary"]["completed_sessions"] >= 1
        assert payload["rows"][0].get("session_id")


def test_insights_insufficient_data():
    with get_sessionmaker()() as db:
        email = f"empty-{uuid.uuid4().hex[:6]}@example.com"
        org = Organisation(name="Empty", contact_email=email, allowed_services_json='{"customer_feedback": true}')
        db.add(org)
        db.commit()
        payload = FeedbackResultsService.customer_insights(db, org.id)
        assert payload["ai"]["source"] == "insufficient_data"
