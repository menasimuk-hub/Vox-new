"""Phone campaign settlement — PAYG hold refund and subscription in-allowance (no invoice)."""

from __future__ import annotations

import json
import uuid

from app.core.database import get_sessionmaker
from app.core.security import hash_password
from app.models.membership import OrganisationMembership
from app.models.organisation import Organisation
from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.models.user import User
from app.services.campaign_billing_settlement_service import CampaignBillingSettlementService
from app.services.platform_catalog_service import PlatformCatalogService


def _seed_org(*, wallet_minor: int = 50_000) -> tuple[str, str]:
    email = f"settle-{uuid.uuid4().hex[:8]}@example.com"
    with get_sessionmaker()() as db:
        PlatformCatalogService.ensure_defaults(db)
        org = Organisation(name="Settle Org", wallet_balance_pence=wallet_minor, contact_email=email)
        db.add(org)
        db.flush()
        user = User(email=email, password_hash=hash_password("pass123"), is_active=True)
        db.add(user)
        db.flush()
        db.add(OrganisationMembership(org_id=org.id, user_id=user.id))
        db.commit()
        return org.id, user.id


def test_payg_settlement_refunds_hold_when_call_shorter_than_estimate():
    org_id, user_id = _seed_org()
    with get_sessionmaker()() as db:
        order = ServiceOrder(
            org_id=org_id,
            user_id=user_id,
            service_code="survey",
            title="Payg settle",
            status="running",
            payment_status="approved",
            payment_method="wallet",
            recipient_count=1,
            launch_billing_json=json.dumps(
                {
                    "channel": "ai_call",
                    "currency": "GBP",
                    "billing_phase": "held",
                    "payment_method": "wallet",
                    "unit_rate_minor": 100,
                    "connection_fee_minor": 0,
                    "wallet_hold_minor": 375,
                    "wallet_charge_minor": 375,
                    "duration_minutes": 3,
                }
            ),
        )
        db.add(order)
        db.flush()
        db.add(
            ServiceOrderRecipient(
                order_id=order.id,
                row_number=1,
                name="Test",
                phone="+447700900123",
                status="completed",
                result_json=json.dumps({"duration_seconds": 60, "billable_minutes": 1, "hangup_cause": "normal_clearing"}),
            )
        )
        db.commit()
        order_id = order.id
        org_before = db.get(Organisation, org_id)
        wallet_before = int(org_before.wallet_balance_pence or 0)

    with get_sessionmaker()() as db:
        order = db.get(ServiceOrder, order_id)
        result = CampaignBillingSettlementService.settle_order(db, order, trigger="completion")
        assert result is not None
        assert int(result["total_billable_minutes"]) == 1
        assert int(result["final_charge_minor"]) == 100
        assert int(result["hold_refund_minor"]) == 275
        assert result.get("invoice_id")
        org = db.get(Organisation, org_id)
        assert int(org.wallet_balance_pence or 0) == wallet_before + 275
