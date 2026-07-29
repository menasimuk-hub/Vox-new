"""Overage consent — launch blocked and settlement does not invoice when disabled."""

from __future__ import annotations

import json
import uuid

from app.core.database import get_sessionmaker
from app.core.security import hash_password
from app.models.billing_invoice import BillingInvoice
from app.models.membership import OrganisationMembership
from app.models.organisation import Organisation
from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.models.user import User
from app.services.campaign_billing_settlement_service import CampaignBillingSettlementService
from app.services.org_control_center_actions_service import OrgControlCenterActionsService
from app.services.platform_catalog_service import PlatformCatalogService
from sqlalchemy import func, select


def _seed_org(*, allow_overage: bool = False) -> tuple[str, str]:
    email = f"overage-{uuid.uuid4().hex[:8]}@example.com"
    with get_sessionmaker()() as db:
        PlatformCatalogService.ensure_defaults(db)
        org = Organisation(
            name="Overage Consent Org",
            wallet_balance_pence=50_000,
            contact_email=email,
            allow_overage=allow_overage,
        )
        db.add(org)
        db.flush()
        user = User(email=email, password_hash=hash_password("pass123"), is_active=True)
        db.add(user)
        db.flush()
        db.add(OrganisationMembership(org_id=org.id, user_id=user.id))
        db.commit()
        return org.id, user.id


def test_enable_overage_stamps_consent_accepted_at():
    org_id, _user_id = _seed_org(allow_overage=False)
    with get_sessionmaker()() as db:
        result = OrgControlCenterActionsService.set_allow_overage(
            db, org_id, allow_overage=True, reason="test enable"
        )
        assert result["allow_overage"] is True
        assert result["overage_consent_accepted_at"] is not None
        org = db.get(Organisation, org_id)
        assert org.allow_overage is True
        assert org.overage_consent_accepted_at is not None


def test_settlement_blocks_subscription_overage_without_consent(monkeypatch):
    org_id, user_id = _seed_org(allow_overage=False)

    def _fake_costs(db, order, snapshot, usage, *, trigger):
        return {
            "amount_due_minor": 500,
            "final_charge_minor": 500,
            "catalog_cost_minor": 500,
            "is_subscription": True,
            "total_billable_minutes": 5,
            "included_minutes": 0,
            "extra_minutes": 5,
            "actual_units": 0,
        }

    monkeypatch.setattr(
        CampaignBillingSettlementService,
        "_compute_costs",
        staticmethod(_fake_costs),
    )

    with get_sessionmaker()() as db:
        order = ServiceOrder(
            org_id=org_id,
            user_id=user_id,
            service_code="survey",
            title="Overage blocked settle",
            status="running",
            payment_status="approved",
            payment_method="direct_debit",
            recipient_count=1,
            launch_billing_json=json.dumps(
                {
                    "channel": "ai_call",
                    "currency": "GBP",
                    "billing_phase": "held",
                    "payment_method": "direct_debit",
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
                phone="+447700900111",
                status="completed",
                result_json=json.dumps(
                    {"duration_seconds": 120, "billable_minutes": 2, "hangup_cause": "normal_clearing"}
                ),
            )
        )
        db.commit()
        order_id = order.id

    with get_sessionmaker()() as db:
        order = db.get(ServiceOrder, order_id)
        result = CampaignBillingSettlementService.settle_order(db, order, trigger="completion")
        assert result is None
        snap = CampaignBillingSettlementService._load_snapshot(db.get(ServiceOrder, order_id))
        assert snap.get("billing_phase") == "billing_failed"
        assert (snap.get("billing_failure") or {}).get("reason") == "overage_disabled"
        count = db.execute(
            select(func.count()).select_from(BillingInvoice).where(BillingInvoice.order_id == order_id)
        ).scalar_one()
        assert int(count) == 0
