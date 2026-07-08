"""Tests for Products hub catalogue service — display/copy only."""

from app.models.plan import Plan
from app.services.products_hub_service import ProductsHubService


def test_is_dental_plan_excludes_legacy_codes():
    dental = Plan(code="practice", name="Practice", service_kind="dental", interval="monthly")
    assert ProductsHubService.is_dental_plan(dental) is True
    core = Plan(code="starter", name="Starter", service_kind="voxbulk", interval="monthly")
    assert ProductsHubService.is_dental_plan(core) is False


def test_decode_cf_code():
    tier, zone = ProductsHubService.decode_cf_code("cf_starter_us")
    assert tier == "starter"
    assert zone == "us"


def test_picker_label_feedback():
    plan = Plan(
        code="cf_starter_gb",
        name="Starter",
        service_kind="customer_feedback",
        interval="monthly",
    )
    parts = ProductsHubService.picker_parts(plan)
    assert "Customer Feedback" in parts["picker_label"]
    assert "Starter" in parts["picker_label"]
    assert "GB" in parts["picker_label"]


def test_picker_label_core():
    plan = Plan(code="pro", name="Pro", service_kind="voxbulk", interval="monthly")
    parts = ProductsHubService.picker_parts(plan)
    assert parts["picker_label"] == "Core platform · Pro · Global"


def test_feedback_preview_urls_use_unified_packages_page():
    plan = Plan(code="cf_growth_gb", name="Growth", service_kind="customer_feedback", interval="monthly")
    urls = ProductsHubService.preview_urls(plan)
    assert urls["dashboard"] == "/account/packages?tab=feedback&product=feedback&plan=cf_growth_gb"
    assert "product=feedback" in urls["website"]
