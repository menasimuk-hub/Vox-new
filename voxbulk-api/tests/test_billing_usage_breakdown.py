"""Tests for billing usage breakdown API."""

from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import select

from app.core.database import get_sessionmaker
from app.core.security import hash_password
from app.models.membership import OrganisationMembership
from app.models.organisation import Organisation
from app.models.plan import Plan
from app.models.service_order import ServiceOrder
from app.models.subscription import Subscription
from app.models.user import User
from app.services.billing_usage_breakdown_service import BillingUsageBreakdownService
from app.services.gocardless_service import BillingService

@pytest.fixture(scope="module", autouse=True)
def _prepare_db():
    from app.core.database import Base, get_engine
    import app.models  # noqa: F401

    Base.metadata.create_all(bind=get_engine())


def _seed_org_with_user() -> tuple[str, str]:
    with get_sessionmaker()() as db:
        BillingService.ensure_default_plans(db)
        plan = db.execute(select(Plan).where(Plan.code != "payg").limit(1)).scalar_one()
        email = f"usage-{uuid.uuid4().hex[:8]}@example.com"
        org = Organisation(name="Usage Org", contact_email=email, wallet_balance_pence=0)
        db.add(org)
        db.flush()
        user = User(email=email, password_hash=hash_password("pass123"), is_active=True)
        db.add(user)
        db.flush()
        db.add(OrganisationMembership(org_id=org.id, user_id=user.id))
        db.add(
            Subscription(
                org_id=org.id,
                plan_id=plan.id,
                status="active",
                payment_provider="gocardless",
            )
        )
        db.commit()
        return org.id, user.id


def test_usage_breakdown_lists_launched_order():
    org_id, user_id = _seed_org_with_user()
    with get_sessionmaker()() as db:
        org = db.get(Organisation, org_id)
        assert org is not None

        order = ServiceOrder(
            id="usage-order-1",
            org_id=org_id,
            user_id=user_id,
            service_code="survey",
            title="Usage test survey",
            campaign_id="CAMP-001",
            status="running",
            payment_status="approved",
            recipient_count=10,
            quote_total_pence=0,
            config_json=json.dumps({"survey_channel": "whatsapp"}),
            launch_billing_json=json.dumps(
                {
                    "channel": "whatsapp",
                    "unit": "recipients",
                    "units_billable": 10,
                    "wallet_charge_minor": 0,
                    "dd_charge_minor": 0,
                    "payment_method": "allowance",
                }
            ),
        )
        db.add(order)
        db.commit()

        payload = BillingUsageBreakdownService.build(db, org, limit=20)
        assert payload["ok"] is True
        assert payload["rows"]
        row = payload["rows"][0]
        assert row["order_id"] == "usage-order-1"
        assert row["name"] == "Usage test survey"
        assert row["billing_source"] == "included_in_package"
        assert row["cost_minor"] == 0
        assert "messages" in str(row["usage_display"])


def test_usage_breakdown_row_lookup():
    org_id, user_id = _seed_org_with_user()
    with get_sessionmaker()() as db:
        org = db.get(Organisation, org_id)
        assert org is not None

        order = ServiceOrder(
            id="usage-order-2",
            org_id=org_id,
            user_id=user_id,
            service_code="interview",
            title="Interview usage",
            status="completed",
            payment_status="approved",
            recipient_count=3,
            quote_total_pence=1500,
            launch_billing_json=json.dumps(
                {
                    "channel": "ai_call",
                    "unit": "minutes",
                    "units_billable": 15,
                    "wallet_charge_minor": 1500,
                    "payment_method": "wallet",
                }
            ),
        )
        db.add(order)
        db.commit()

        row = BillingUsageBreakdownService.get_row(db, org_id, "usage-order-2")
        assert row is not None
        assert row["service_code"] == "interview"
        assert row["billing_source"] == "wallet"
        assert row["cost_minor"] == 1500
