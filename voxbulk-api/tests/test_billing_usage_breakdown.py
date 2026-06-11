"""Tests for billing usage breakdown API."""

from __future__ import annotations

import json

from app.services.billing_usage_breakdown_service import BillingUsageBreakdownService
from app.services.gocardless_service import BillingService


def test_usage_breakdown_lists_launched_order(app_db):
    db, org_id, user_id = app_db
    org = BillingService.get_org(db, org_id)
    assert org is not None

    from app.models.service_order import ServiceOrder

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


def test_usage_breakdown_row_lookup(app_db):
    db, org_id, user_id = app_db
    org = BillingService.get_org(db, org_id)
    from app.models.service_order import ServiceOrder

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
            {"channel": "ai_call", "unit": "minutes", "units_billable": 15, "wallet_charge_minor": 1500, "payment_method": "wallet"}
        ),
    )
    db.add(order)
    db.commit()

    row = BillingUsageBreakdownService.get_row(db, org_id, "usage-order-2")
    assert row is not None
    assert row["service_code"] == "interview"
    assert row["billing_source"] == "wallet"
    assert row["cost_minor"] == 1500
