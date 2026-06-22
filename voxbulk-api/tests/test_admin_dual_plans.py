"""Admin dual-plan assignment — C.P (voxbulk) and F.B (customer_feedback)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from sqlalchemy import select

from app.core.database import get_sessionmaker
from app.core.security import hash_password
from app.models.customer_feedback import FEEDBACK_SERVICE_CODE
from app.models.membership import OrganisationMembership
from app.models.organisation import Organisation
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.models.user import User
from app.services.admin_org_service import AdminOrganisationService
from app.services.billing_access_service import BillingAccessService
from app.services.customer_feedback.billing_service import FeedbackBillingService
from app.services.customer_feedback.seed_service import FeedbackSeedService
from app.services.gocardless_service import BillingService
from app.services.platform_catalog_service import PlatformCatalogService


def _admin_headers(app_client) -> dict[str, str]:
    with get_sessionmaker()() as db:
        org = Organisation(name="Dual Plan Admin Org")
        db.add(org)
        db.flush()
        su = User(
            email=f"su-dual-{uuid.uuid4().hex[:8]}@example.com",
            password_hash=hash_password("pass123"),
            is_active=True,
            is_superuser=True,
        )
        db.add(su)
        db.flush()
        db.add(OrganisationMembership(org_id=org.id, user_id=su.id))
        db.commit()
        admin_org_id = org.id
        email = su.email

    tok = app_client.post(
        "/auth/token",
        data={"username": email, "password": "pass123", "org_id": admin_org_id},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def _seed_target_org(*, with_feedback: bool = True, with_core: bool = False) -> str:
    with get_sessionmaker()() as db:
        PlatformCatalogService.ensure_defaults(db)
        BillingService.ensure_default_plans(db)
        FeedbackSeedService.ensure_seeded(db)

        org = Organisation(name=f"Dual Plan Target {uuid.uuid4().hex[:6]}", country_code="GB")
        db.add(org)
        db.flush()

        if with_feedback:
            cf_plan = db.execute(
                select(Plan).where(Plan.code == "cf_starter_gb", Plan.service_kind == FEEDBACK_SERVICE_CODE)
            ).scalar_one()
            fb_sub = Subscription(
                org_id=org.id,
                plan_id=cf_plan.id,
                service_code=FEEDBACK_SERVICE_CODE,
                status="active",
                current_period_end=datetime.utcnow() + timedelta(days=30),
                payment_provider="manual_cash",
            )
            db.add(fb_sub)
            db.flush()
            FeedbackBillingService.on_subscription_activated(db, org_id=org.id, subscription=fb_sub, plan=cf_plan)

        if with_core:
            core_plan = db.execute(
                select(Plan).where(Plan.service_kind == "voxbulk", Plan.code == "starter")
            ).scalar_one_or_none()
            if core_plan is None:
                core_plan = db.execute(select(Plan).where(Plan.service_kind == "voxbulk").limit(1)).scalar_one()
            db.add(
                Subscription(
                    org_id=org.id,
                    plan_id=core_plan.id,
                    service_code="voxbulk",
                    status="active",
                    payment_provider="manual_cash",
                )
            )

        db.commit()
        return org.id


def test_org_summary_splits_core_and_feedback_plans():
    org_id = _seed_target_org(with_feedback=True, with_core=False)
    with get_sessionmaker()() as db:
        summary = AdminOrganisationService.get_org_summary(db, org_id=org_id)
    assert summary is not None
    assert summary.feedback_plan_code == "cf_starter_gb"
    assert summary.core_plan_code is None
    assert summary.plan_code is None


def test_assign_cp_when_fb_exists(app_client):
    headers = _admin_headers(app_client)
    org_id = _seed_target_org(with_feedback=True, with_core=False)

    r = app_client.put(
        f"/admin/organisations/{org_id}/subscription",
        json={"plan_code": "starter", "status": "active"},
        headers=headers,
    )
    assert r.status_code == 200, r.text

    with get_sessionmaker()() as db:
        summary = AdminOrganisationService.get_org_summary(db, org_id=org_id)
        assert summary.feedback_plan_code == "cf_starter_gb"
        assert summary.core_plan_code == "starter"
        fb_sub = BillingAccessService.get_feedback_subscription(db, org_id)
        core_sub = BillingAccessService.get_valid_core_subscription(db, org_id)
        assert fb_sub is not None
        assert core_sub is not None
        assert fb_sub.plan_id != core_sub.plan_id


def test_change_cp_does_not_change_fb(app_client):
    headers = _admin_headers(app_client)
    org_id = _seed_target_org(with_feedback=True, with_core=True)

    with get_sessionmaker()() as db:
        fb_before = BillingAccessService.get_feedback_subscription(db, org_id)
        fb_plan_id = fb_before.plan_id

    r = app_client.put(
        f"/admin/organisations/{org_id}/subscription",
        json={"plan_code": "starter", "status": "active", "force_raw": True},
        headers=headers,
    )
    assert r.status_code == 200, r.text

    with get_sessionmaker()() as db:
        fb_after = BillingAccessService.get_feedback_subscription(db, org_id)
        assert fb_after.plan_id == fb_plan_id
        core_sub = BillingAccessService.get_valid_core_subscription(db, org_id)
        core_plan = db.get(Plan, core_sub.plan_id)
        assert core_plan.code == "starter"


def test_force_raw_core_does_not_overwrite_feedback_row(app_client):
    headers = _admin_headers(app_client)
    org_id = _seed_target_org(with_feedback=True, with_core=False)

    with get_sessionmaker()() as db:
        fb_sub = BillingAccessService.get_feedback_subscription(db, org_id)
        fb_sub_id = fb_sub.id

    r = app_client.put(
        f"/admin/organisations/{org_id}/subscription",
        json={"plan_code": "starter", "status": "active", "force_raw": True},
        headers=headers,
    )
    assert r.status_code == 200, r.text

    with get_sessionmaker()() as db:
        assert db.get(Subscription, fb_sub_id) is not None
        fb = BillingAccessService.get_feedback_subscription(db, org_id)
        assert fb.id == fb_sub_id
        assert fb.service_code == FEEDBACK_SERVICE_CODE
        core = BillingAccessService.get_valid_core_subscription(db, org_id)
        assert core is not None
        assert core.service_code == "voxbulk"
        core_plan = db.get(Plan, core.plan_id)
        assert core_plan.code == "starter"


def test_feedback_assign_rejects_core_plan(app_client):
    headers = _admin_headers(app_client)
    org_id = _seed_target_org(with_feedback=False, with_core=False)

    r = app_client.put(
        f"/admin/organisations/{org_id}/feedback-subscription",
        json={"plan_code": "starter", "status": "active"},
        headers=headers,
    )
    assert r.status_code == 400
    assert "feedback" in r.json().get("detail", "").lower() or "customer" in r.json().get("detail", "").lower()


def test_feedback_assign_creates_subscription(app_client):
    headers = _admin_headers(app_client)
    org_id = _seed_target_org(with_feedback=False, with_core=False)

    r = app_client.put(
        f"/admin/organisations/{org_id}/feedback-subscription",
        json={"plan_code": "cf_starter_gb", "status": "active"},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["plan_code"] == "cf_starter_gb"
    assert body["service_code"] == FEEDBACK_SERVICE_CODE

    with get_sessionmaker()() as db:
        summary = AdminOrganisationService.get_org_summary(db, org_id=org_id)
        assert summary.feedback_plan_code == "cf_starter_gb"


def test_core_assign_rejects_feedback_plan(app_client):
    headers = _admin_headers(app_client)
    org_id = _seed_target_org(with_feedback=False, with_core=False)

    r = app_client.put(
        f"/admin/organisations/{org_id}/subscription",
        json={"plan_code": "cf_starter_gb", "status": "active"},
        headers=headers,
    )
    assert r.status_code == 400
    assert "c.p" in r.json().get("detail", "").lower() or "core" in r.json().get("detail", "").lower()
