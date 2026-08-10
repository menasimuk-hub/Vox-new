"""Smoke tests for CustomPackagesService (in-memory SQLite)."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.custom_package import CustomPackage, CustomPackageOrgAssignment
from app.models.organisation import Organisation
from app.services.billing_currency import CURRENCY_SYMBOLS, SUPPORTED_CURRENCIES, normalize_currency
from app.services.custom_packages_service import CustomPackagesError, CustomPackagesService, default_modules


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine, tables=[Organisation.__table__, CustomPackage.__table__, CustomPackageOrgAssignment.__table__])
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


def test_rejects_bad_interval(db):
    with pytest.raises(CustomPackagesError):
        CustomPackagesService.create_package(db, {"name": "X", "interval": "one_time", "currency": "GBP"})


def test_duplicate_clears_orgs(db):
    src = CustomPackagesService.create_package(
        db,
        {"name": "Src", "currency": "USD", "status": "active", "org_ids": ["org-1"], "price_minor": 100},
    )
    copy = CustomPackagesService.duplicate_package(db, src["id"])
    assert copy["status"] == "draft"
    assert copy["org_count"] == 0
    assert copy["currency"] == "USD"
