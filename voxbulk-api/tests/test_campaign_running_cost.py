"""Campaign running cost — catalog value vs amount due."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta

from app.core.database import get_sessionmaker
from app.core.security import hash_password
from app.models.membership import OrganisationMembership
from app.models.org_usage_period import OrgUsagePeriod
from app.models.organisation import Organisation
from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.models.user import User
from app.services.campaign_running_cost_service import CampaignRunningCostService
from app.services.platform_catalog_service import PlatformCatalogService


def _seed_subscriber_org(*, calls_included: int = 100, calls_used: int = 0) -> tuple[str, str]:
    email = f"cost-{uuid.uuid4().hex[:8]}@example.com"
    with get_sessionmaker()() as db:
        PlatformCatalogService.ensure_defaults(db)
        org = Organisation(name="Cost Org", contact_email=email)
        db.add(org)
        db.flush()
        user = User(email=email, password_hash=hash_password("pass123"), is_active=True)
        db.add(user)
        db.flush()
        db.add(OrganisationMembership(org_id=org.id, user_id=user.id))
        db.add(
            OrgUsagePeriod(
                org_id=org.id,
                period_start=datetime.utcnow(),
                period_end=datetime.utcnow() + timedelta(days=30),
                status="active",
                plan_code="starter",
                calls_included=calls_included,
                calls_used=calls_used,
                whatsapp_included=50,
                whatsapp_used=0,
                overage_per_min_pence=35,
            )
        )
        db.commit()
        return org.id, user.id


def test_running_cost_subscriber_in_allowance_shows_catalog_not_due():
    org_id, user_id = _seed_subscriber_org(calls_included=100, calls_used=0)
    with get_sessionmaker()() as db:
        order = ServiceOrder(
            org_id=org_id,
            user_id=user_id,
            service_code="interview",
            title="In allowance",
            status="running",
            payment_status="approved",
            payment_method="subscription_allowance",
            launch_billing_json=json.dumps(
                {
                    "channel": "ai_call",
                    "billing_phase": "pending_settlement",
                    "payment_method": "allowance",
                    "per_min_minor": 32,
                    "extra_per_min_minor": 35,
                    "list_per_min_minor": 35,
                    "connection_fee_minor": 200,
                    "calls_remaining_at_launch": 100,
                    "currency": "GBP",
                }
            ),
        )
        db.add(order)
        db.flush()
        db.add(
            ServiceOrderRecipient(
                order_id=order.id,
                row_number=1,
                name="A",
                phone="+447700900001",
                status="completed",
                result_json=json.dumps(
                    {
                        "duration_seconds": 120,
                        "billable_minutes": 2,
                        "usage_metered_at": datetime.utcnow().isoformat(),
                        "usage_metered_minutes": 2,
                    }
                ),
            )
        )
        db.commit()
        org = db.get(Organisation, org_id)
        payload = CampaignRunningCostService.compute_for_order(db, order)
        assert int(payload["catalog_cost_minor"]) > 0
        assert int(payload["amount_due_minor"]) == 0
        assert payload["cost_kind"] == "running"
