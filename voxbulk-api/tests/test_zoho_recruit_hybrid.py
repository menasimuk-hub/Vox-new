"""Zoho Recruit hybrid helpers: recipient id + writeback status mapping."""

from __future__ import annotations

from types import SimpleNamespace

from app.services.partner_service import recommendation_to_status
from app.services.zoho_recruit_connection_service import (
    _candidate_row_from_zoho,
    recipient_zoho_candidate_id,
)


def test_recommendation_to_status_bands():
    assert recommendation_to_status("advance", 40) == "passed"
    assert recommendation_to_status("reject", 90) == "rejected"
    assert recommendation_to_status(None, 80) == "passed"
    assert recommendation_to_status(None, 40) == "rejected"
    assert recommendation_to_status(None, 60) == "review"


def test_recipient_zoho_candidate_id_from_result_json():
    r = SimpleNamespace(result_json='{"zoho_recruit_candidate_id": "Z123"}')
    assert recipient_zoho_candidate_id(r) == "Z123"
    assert recipient_zoho_candidate_id(SimpleNamespace(result_json="{}")) == ""


def test_candidate_row_maps_phone_missing():
    row = _candidate_row_from_zoho(
        {
            "id": "1",
            "Full_Name": "Ada Lovelace",
            "Email": "ada@example.com",
            "Candidate_Status": "Qualified",
        }
    )
    assert row is not None
    assert row["id"] == "1"
    assert row["phone_missing"] is True
    assert row["stage"] == "Qualified"
