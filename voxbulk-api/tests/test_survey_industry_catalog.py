"""WA Survey industry catalog — 14 industries × 20 survey types."""

from __future__ import annotations

from app.services.survey_industry_seed_service import INDUSTRY_CATALOG, LEGACY_INDUSTRY_SLUGS_TO_HIDE


def test_industry_catalog_has_fourteen_industries_with_twenty_services_each():
    assert len(INDUSTRY_CATALOG) == 14
    for item in INDUSTRY_CATALOG:
        services = item.get("services") or []
        assert len(services) == 20, f"{item['slug']} has {len(services)} services, expected 20"
        assert len({s.strip().lower() for s in services}) == 20, f"{item['slug']} has duplicate service names"


def test_expected_industry_slugs_present():
    slugs = {item["slug"] for item in INDUSTRY_CATALOG}
    assert slugs == {
        "healthcare_dental",
        "recruitment_staffing",
        "hospitality_food",
        "hotel_accommodation",
        "property_lettings",
        "retail_ecommerce",
        "automotive",
        "education_training",
        "legal_accountancy",
        "fitness_wellness",
        "financial_services",
        "logistics_delivery",
        "events_entertainment",
        "employee_survey",
    }


def test_legacy_industries_marked_for_hiding():
    catalog_slugs = {item["slug"] for item in INDUSTRY_CATALOG}
    assert catalog_slugs.isdisjoint(LEGACY_INDUSTRY_SLUGS_TO_HIDE)
