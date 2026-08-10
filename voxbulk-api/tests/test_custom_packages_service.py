"""Smoke tests for CustomPackagesService (in-memory SQLite)."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.custom_package import CustomPackage, CustomPackageOrgAssignment
from app.models.organisation import Organisation
from app.services.custom_packages_service import CustomPackagesError, CustomPackagesService, default_modules


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    org = Organisation(id="org-1", name="Tourist Co")
    session.add(org)
    session.commit()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def test_create_list_and_assign(db):
    item = CustomPackagesService.create_package(
        db,
        {
            "name": "Tourist Bundle",
            "interval": "monthly",
            "currency": "GBP",
            "price_minor": 124000,
            "status": "active",
            "modules": {
                "customer_feedback": {"enabled": True, "max_locations": 5},
                "survey": {"enabled": True, "whatsapp_recipients_included": 2000, "call_minutes_included": 300},
            },
            "allowlist": {"mode": "custom", "core": ["GB", "USA"], "extra": ["DE"]},
            "org_ids": ["org-1"],
        },
    )
    assert item["name"] == "Tourist Bundle"
    assert item["currency"] == "GBP"
    assert item["interval"] == "monthly"
    assert "customer_feedback" in item["enabled_services"]
    assert "survey" in item["enabled_services"]
    assert item["modules"]["survey"]["whatsapp_recipients_included"] == 2000
    assert item["org_count"] == 1
    assert item["allowlist_country_count"] == 3

    listed = CustomPackagesService.list_packages(db)
    assert len(listed) == 1

    for_org = CustomPackagesService.get_for_org(db, "org-1")
    assert for_org is not None
    assert for_org["id"] == item["id"]


def test_survey_defaults_merged():
    mods = default_modules()
    assert mods["survey"]["max_active_campaigns"] == 5
    assert "wa_extra_minor" in mods["customer_feedback"]
    assert "ai_followback" in mods
    assert "ai_followback" not in mods["customer_feedback"]
    assert mods["ai_followback"]["minutes_included"] == 0


def test_ai_followback_promotes_legacy_cf_and_strips_nested():
    from app.services.custom_packages_service import _merge_modules, ai_followback_config

    merged = _merge_modules(
        {
            "customer_feedback": {
                "enabled": True,
                "ai_followback": {
                    "minutes_included": 40,
                    "connection_fee_minor": 50,
                    "per_min_minor": 25,
                },
            }
        }
    )
    assert merged["ai_followback"]["minutes_included"] == 40
    assert merged["ai_followback"]["connection_fee_minor"] == 50
    assert "ai_followback" not in merged["customer_feedback"]
    assert ai_followback_config(merged)["per_min_minor"] == 25


def test_estimate_followback_charge_extra_cost_model():
    covered = CustomPackagesService.estimate_followback_charge(
        billable_mins=5,
        minutes_included=10,
        minutes_used=0,
        connection_fee_minor=100,
        per_min_minor=50,
        currency="GBP",
    )
    assert covered["amount_due_minor"] == 0
    assert covered["payment_method"] == "included"
    assert covered["covered_minutes"] == 5

    partial = CustomPackagesService.estimate_followback_charge(
        billable_mins=5,
        minutes_included=10,
        minutes_used=8,
        connection_fee_minor=100,
        per_min_minor=50,
        currency="GBP",
    )
    # 2 remaining included → 3 overage → connection 100 + 3*50 = 250
    assert partial["covered_minutes"] == 2
    assert partial["overage_minutes"] == 3
    assert partial["amount_due_minor"] == 250
    assert partial["payment_method"] == "wallet"


def test_rejects_bad_interval(db):
    with pytest.raises(CustomPackagesError):
        CustomPackagesService.create_package(db, {"name": "X", "interval": "one_time", "currency": "GBP"})


def test_org_dashboard_payload(db):
    CustomPackagesService.create_package(
        db,
        {
            "name": "Tourist Bundle",
            "interval": "monthly",
            "currency": "GBP",
            "price_minor": 124000,
            "status": "active",
            "modules": {
                "customer_feedback": {"enabled": True, "max_locations": 5, "wa_units_included": 100},
                "survey": {"enabled": True, "whatsapp_recipients_included": 500},
            },
            "org_ids": ["org-1"],
        },
    )
    payload = CustomPackagesService.org_dashboard_payload(db, "org-1")
    assert payload is not None
    assert payload["assigned"] is True
    assert payload["package"]["name"] == "Tourist Bundle"
    assert payload["billing"]["amount_next_payment_minor"] == 124000
    assert any(r["key"] == "wa_units" for r in payload["usage"]["rows"])
    assert any(r["key"] == "ai_followback_mins" and r["module"] == "ai_followback" for r in payload["usage"]["rows"])
    assert CustomPackagesService.org_dashboard_payload(db, "missing") is None


def test_duplicate_clears_orgs(db):
    src = CustomPackagesService.create_package(
        db,
        {"name": "Src", "currency": "USD", "status": "active", "org_ids": ["org-1"], "price_minor": 100},
    )
    copy = CustomPackagesService.duplicate_package(db, src["id"])
    assert copy["status"] == "draft"
    assert copy["org_count"] == 0
    assert copy["currency"] == "USD"

