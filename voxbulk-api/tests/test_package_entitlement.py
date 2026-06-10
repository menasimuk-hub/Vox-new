"""Shared package pool entitlement — WA + AI consume one allowance."""

from __future__ import annotations

from datetime import datetime, timedelta

from app.models.org_usage_period import OrgUsagePeriod
from app.services.package_entitlement_service import PackageEntitlementService


def test_shared_pool_exhausted_zeros_ai_remaining():
    row = OrgUsagePeriod(
        org_id="org-1",
        period_start=datetime.utcnow(),
        period_end=datetime.utcnow() + timedelta(days=30),
        status="active",
        plan_code="starter",
        calls_included=429,
        calls_used=0,
        whatsapp_included=429,
        whatsapp_used=429,
    )
    ent = PackageEntitlementService.for_usage_row(row, plan_code="starter")
    assert ent["shared_package_pool"] is True
    assert ent["package_included"] == 429
    assert ent["package_used"] == 429
    assert ent["package_remaining"] == 0
    assert ent["calls_remaining"] == 0
    assert ent["whatsapp_remaining"] == 0


def test_payg_uses_separate_buckets():
    row = OrgUsagePeriod(
        org_id="org-1",
        period_start=datetime.utcnow(),
        period_end=datetime.utcnow() + timedelta(days=30),
        status="active",
        plan_code="payg",
        calls_included=100,
        calls_used=10,
        whatsapp_included=100,
        whatsapp_used=90,
    )
    ent = PackageEntitlementService.for_usage_row(row, plan_code="payg")
    assert ent["shared_package_pool"] is False
    assert ent["calls_remaining"] == 90
    assert ent["whatsapp_remaining"] == 10


def test_shared_pool_overage_allocates_after_package_exhausted():
    row = OrgUsagePeriod(
        org_id="org-1",
        period_start=datetime.utcnow(),
        period_end=datetime.utcnow() + timedelta(days=30),
        status="active",
        plan_code="starter",
        calls_included=429,
        calls_used=50,
        whatsapp_included=429,
        whatsapp_used=429,
        overage_per_min_pence=20,
    )
    from app.services.usage_wallet_service import UsageWalletService

    breakdown = UsageWalletService._overage_breakdown_pence(row)
    assert breakdown["call_minutes_overage"] == 50
    assert breakdown["wa_recipient_overage"] == 0
    assert breakdown["total_overage_pence"] == 50 * 20
