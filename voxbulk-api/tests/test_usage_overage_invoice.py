"""Usage overage invoicing — split line items and WA metering boundaries."""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from app.models.org_usage_period import OrgUsagePeriod
from app.models.organisation import Organisation
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.services.usage_wallet_service import UsageWalletService


@pytest.fixture()
def db():
    from app.core.database import Base, get_engine, get_sessionmaker
    import app.models  # noqa: F401

    engine = get_engine()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    SessionLocal = get_sessionmaker()
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def _seed_usage_row(db, *, wa_used=0, wa_included=0, calls_used=0, calls_included=0):
    org = Organisation(name="Overage Org")
    db.add(org)
    db.flush()
    plan = Plan(
        code="overage_plan",
        name="Overage Plan",
        price_gbp_pence=1000,
        interval="month",
        calls_included=calls_included,
        whatsapp_included=wa_included,
        overage_per_min_pence=20,
        is_active=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(plan)
    db.flush()
    sub = Subscription(
        org_id=org.id,
        plan_id=plan.id,
        status="active",
        current_period_end=datetime.utcnow() + timedelta(days=30),
        payment_provider="manual_cash",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(sub)
    db.flush()
    row = OrgUsagePeriod(
        org_id=org.id,
        period_start=datetime.utcnow(),
        period_end=datetime.utcnow() + timedelta(days=30),
        status="active",
        plan_code=plan.code,
        calls_included=calls_included,
        calls_used=calls_used,
        whatsapp_included=wa_included,
        whatsapp_used=wa_used,
        overage_per_min_pence=20,
        overage_invoiced_pence=0,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(row)
    db.commit()
    return org, row


def test_overage_breakdown_splits_wa_and_call_minutes(db):
    org, row = _seed_usage_row(db, wa_used=2, wa_included=0, calls_used=3, calls_included=0)
    breakdown = UsageWalletService._overage_breakdown_pence(row, db, org.id)
    assert breakdown["wa_recipient_overage"] == 2
    assert breakdown["call_minutes_overage"] == 3
    assert breakdown["total_overage_pence"] == breakdown["wa_overage_pence"] + breakdown["call_overage_pence"]


def test_one_wa_survey_overage_is_one_unit_not_forty(db):
    org, row = _seed_usage_row(db, wa_used=1, wa_included=0)
    breakdown = UsageWalletService._overage_breakdown_pence(row, db, org.id)
    assert breakdown["wa_recipient_overage"] == 1
    assert breakdown["wa_overage_pence"] == 49
    assert breakdown["total_overage_pence"] == 49


@patch("app.services.billing_event_email_service.BillingEventEmailService.create_invoice")
@patch("app.services.usage_wallet_service.UsageWalletService._overage_breakdown_pence")
def test_maybe_invoice_overage_emits_split_line_items(mock_breakdown, mock_create_invoice, db):
    org, row = _seed_usage_row(db, wa_used=2, wa_included=0, calls_used=5, calls_included=0)
    mock_breakdown.return_value = {
        "call_minutes_overage": 5,
        "call_overage_pence": 100,
        "wa_recipient_overage": 2,
        "wa_overage_pence": 98,
        "total_overage_pence": 198,
        "wa_extra_pence": 49,
    }
    mock_create_invoice.return_value = (type("Inv", (), {"id": "inv-1"})(), True, False)
    with patch("app.services.gocardless_service.BillingService.collect_mandate_payment", return_value={}):
        UsageWalletService.maybe_invoice_overage(
            db,
            org_id=org.id,
            client_email="billing@example.com",
            row=row,
            min_invoice_pence=1,
        )
    line_items = mock_create_invoice.call_args.kwargs["line_items"]
    kinds = {item["kind"] for item in line_items}
    assert "wa_survey" in kinds
    assert "call_minutes" in kinds


def test_send_whatsapp_meter_usage_false_does_not_increment(db):
    from unittest.mock import MagicMock

    from app.services.telnyx_messaging_service import TelnyxMessagingService

    org, row = _seed_usage_row(db, wa_used=0, wa_included=10)
    mock_config = MagicMock()
    mock_config.whatsapp_from = "+441234567890"
    with patch.object(TelnyxMessagingService, "_config", return_value=mock_config):
        with patch.object(TelnyxMessagingService, "_from_numbers", return_value=(None, "+441234567890")):
            with patch.object(TelnyxMessagingService, "_request_message") as mock_req:
                mock_req.return_value = MagicMock(ok=True, status="sent", channel="whatsapp", detail="ok")
                TelnyxMessagingService.send_whatsapp(
                    db,
                    to_number="+447700900123",
                    body="Survey message",
                    org_id=org.id,
                    meter_usage=False,
                )
    db.refresh(row)
    assert int(row.whatsapp_used or 0) == 0
