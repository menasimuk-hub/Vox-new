"""Profile matrix summary: scoped vs whole-account counts."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


def _remote(name: str, *, category: str = "UTILITY", status: str = "APPROVED", language: str = "en") -> dict:
    return {
        "name": name,
        "category": category,
        "status": status,
        "language": language,
        "id": f"meta-{name}",
        "template_id": f"tpl-{name}",
    }


@pytest.fixture
def mock_route():
    route = MagicMock()
    route.profile = MagicMock(name="Meta 99", meta_waba_id="959487190007928", meta_whatsapp_from="+447822002099")
    route.provider = "meta"
    route.is_meta = True
    route.is_telnyx = False
    route.config = {"waba_id": "959487190007928", "whatsapp_from": "+447822002099"}
    return route


def test_summarize_exposes_scoped_and_account_marketing(mock_route):
    from app.services.wa_template_sync_profile import summarize_for_connection_profile

    remote_all = [
        _remote("cfs_hotel_atmosphere_es_v1", category="MARKETING"),
        _remote("cfs_hotel_bed_comfort_en_v1", category="UTILITY"),
        _remote("was_employee_motivation_002_en", category="MARKETING"),
        _remote("hello_auth", category="AUTHENTICATION"),
    ]
    db = MagicMock()

    with (
        patch(
            "app.services.wa_template_sync_profile.resolve_whatsapp_route_for_sync",
            return_value=mock_route,
        ),
        patch(
            "app.services.telnyx_whatsapp_template_sync_service.TelnyxWhatsappTemplateSyncService.fetch_from_meta",
            return_value=remote_all,
        ),
    ):
        result = summarize_for_connection_profile(db, "profile-1", service_code="customer_feedback")

    assert result["ok"] is True
    s = result["summary"]
    assert s["marketing"] == 1
    assert s["profileMarketing"] == 2
    assert s["scoped"]["marketing"] == 1
    assert s["account"]["marketing"] == 2
    assert s["total"] == 2
    assert s["profileTotal"] == 4
    assert s["scoped"]["total"] == 2
    assert s["account"]["total"] == 4


def test_remote_count_block_totals():
    from app.services.wa_template_sync_profile import _remote_count_block

    block = _remote_count_block(
        {"utility": 3, "marketing": 2, "approved": 4, "pending": 1, "rejected": 0, "remote_total": 5}
    )
    assert block["utility"] == 3
    assert block["marketing"] == 2
    assert block["total"] == 5
