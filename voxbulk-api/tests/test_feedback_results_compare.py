"""Tests for Customer Feedback compare-locations API."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta

from sqlalchemy import select

from app.core.database import get_sessionmaker
from app.core.security import hash_password
from app.models.customer_feedback import (
    FEEDBACK_SERVICE_CODE,
    FeedbackIndustry,
    FeedbackLocation,
    FeedbackResponse,
    FeedbackSession,
    FeedbackSurveyType,
    FeedbackWaTemplate,
)
from app.models.membership import OrganisationMembership
from app.models.organisation import Organisation
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.models.user import User
from app.services.customer_feedback.billing_service import FeedbackBillingService
from app.services.customer_feedback.feedback_results_compare import compare_locations
from app.services.customer_feedback.seed_service import FeedbackSeedService


def _seed_compare_org(*, pro: bool = True) -> tuple[str, str, FeedbackLocation, FeedbackLocation]:
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
        email = f"fb-compare-{uuid.uuid4().hex[:8]}@example.com"
        org = Organisation(
            name="Compare Org",
            contact_email=email,
            allowed_services_json='{"customer_feedback": true}',
            enabled_services_json='{"customer_feedback": true}',
        )
        db.add(org)
        db.flush()
        user = User(email=email, password_hash=hash_password("pass123"), is_active=True)
        db.add(user)
        db.flush()
        db.add(OrganisationMembership(org_id=org.id, user_id=user.id))
        plan_code = "cf_pro_gb" if pro else "cf_starter_gb"
        plan = db.execute(
            select(Plan).where(Plan.code == plan_code, Plan.service_kind == FEEDBACK_SERVICE_CODE)
        ).scalar_one()
        sub = Subscription(
            org_id=org.id,
            service_code=FEEDBACK_SERVICE_CODE,
            plan_id=plan.id,
            status="active",
            payment_provider="gocardless",
            current_period_end=datetime.utcnow(),
        )
        db.add(sub)
        db.flush()
        FeedbackBillingService.on_subscription_activated(db, org_id=org.id, subscription=sub, plan=plan)
        now = datetime.utcnow()
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
        loc_a = FeedbackLocation(
            id=str(uuid.uuid4()),
            org_id=org.id,
            industry_id=industry.id,
            survey_type_id=survey_type.id,
            name="Branch A",
            qr_token=f"a-{uuid.uuid4().hex[:8]}",
            wa_sender_country="gb",
            status="active",
            scan_count=120,
            created_at=now,
            updated_at=now,
        )
        loc_b = FeedbackLocation(
            id=str(uuid.uuid4()),
            org_id=org.id,
            industry_id=industry.id,
            survey_type_id=survey_type.id,
            name="Branch B",
            qr_token=f"b-{uuid.uuid4().hex[:8]}",
            wa_sender_country="gb",
            status="active",
            scan_count=80,
            created_at=now,
            updated_at=now,
        )
        db.add(loc_a)
        db.add(loc_b)
        db.flush()

        for loc, answer in ((loc_a, "excellent"), (loc_b, "good")):
            sess = FeedbackSession(
                id=str(uuid.uuid4()),
                org_id=org.id,
                location_id=loc.id,
                visitor_phone=f"+44770098{loc.id[:4]}",
                status="completed",
                current_step=1,
                detected_language="en_GB",
                started_at=now - timedelta(hours=2),
                completed_at=now - timedelta(hours=1),
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
                    answer_text=answer,
                    answer_text_en=answer,
                    original_text=answer.title(),
                    step_order=1,
                    created_at=now,
                )
            )
        db.commit()
        return org.id, email, loc_a, loc_b


def test_compare_locations_returns_metrics_for_two_locations():
    org_id, _email, loc_a, loc_b = _seed_compare_org(pro=True)
    with get_sessionmaker()() as db:
        payload = compare_locations(db, org_id, [loc_a.id, loc_b.id])
        assert payload["ok"] is True
        assert len(payload["locations"]) == 2
        by_id = {row["id"]: row for row in payload["locations"]}
        assert by_id[loc_a.id]["responses"] >= 1
        assert by_id[loc_b.id]["responses"] >= 1
        assert by_id[loc_a.id]["invited"] >= 1
        assert payload["shared_questions"]


def test_compare_locations_starter_plan_forbidden():
    org_id, _email, loc_a, loc_b = _seed_compare_org(pro=False)
    with get_sessionmaker()() as db:
        try:
            compare_locations(db, org_id, [loc_a.id, loc_b.id])
            raise AssertionError("expected ValueError")
        except ValueError as exc:
            assert "multi-location" in str(exc).lower()


def test_compare_locations_http(app_client):
    org_id, email, loc_a, loc_b = _seed_compare_org(pro=True)
    tok = app_client.post(
        "/auth/token",
        data={"username": email, "password": "pass123", "org_id": org_id},
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {tok}"}
    res = app_client.get(
        f"/customer-feedback/results/compare?location_ids={loc_a.id},{loc_b.id}",
        headers=headers,
    )
    assert res.status_code == 200
    body = res.json()
    assert len(body.get("locations") or []) == 2
