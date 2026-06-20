"""Customer subscription finance summary API."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from sqlalchemy import select

from app.core.database import get_sessionmaker
from app.core.security import hash_password
from app.models.membership import OrganisationMembership
from app.models.organisation import Organisation
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.models.user import User
from app.services.platform_catalog_service import PlatformCatalogService
from app.services.subscription_summary_service import SubscriptionSummaryService


def _seed_core_sub() -> str:
    with get_sessionmaker()() as db:
        from app.services.gocardless_service import BillingService

        PlatformCatalogService.ensure_defaults(db)
        BillingService.ensure_default_plans(db)
        org = Organisation(name="Summary Org", contact_email="summary@example.com", country_code="GB")
        db.add(org)
        db.flush()
        user = User(
            email=f"summary-{uuid.uuid4().hex[:8]}@example.com",
            password_hash=hash_password("pass123"),
            is_active=True,
        )
        db.add(user)
        db.flush()
        db.add(OrganisationMembership(org_id=org.id, user_id=user.id))
        plan = db.execute(select(Plan).where(Plan.service_kind == "voxbulk").limit(1)).scalar_one()
        sub = Subscription(
            org_id=org.id,
            plan_id=plan.id,
            service_code="voxbulk",
            status="active",
            payment_provider="gocardless",
            mandate_status="active",
            current_period_end=datetime.utcnow() + timedelta(days=20),
        )
        db.add(sub)
        db.commit()
        return org.id


def test_subscription_summary_includes_core_finance():
    org_id = _seed_core_sub()
    with get_sessionmaker()() as db:
        summary = SubscriptionSummaryService.build_org_summary(db, org_id)
    assert summary["ok"] is True
    assert summary["core"] is not None
    assert summary["core"]["plan_code"]
    assert summary["core"]["next_billing_date"]
