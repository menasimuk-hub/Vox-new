"""Unit tests for Breezy HR helpers (score map + partner reference parsing)."""

from __future__ import annotations

from app.services.breezy_hr_connection_service import parse_partner_reference, score_to_breezy


def test_score_to_breezy_status_passed():
    assert score_to_breezy(90, "passed") == "very_good"
    assert score_to_breezy(72, "passed") == "good"


def test_score_to_breezy_status_rejected():
    assert score_to_breezy(20, "rejected") == "very_poor"
    assert score_to_breezy(45, "rejected") == "poor"


def test_score_to_breezy_review_or_score_only():
    assert score_to_breezy(55, "review") == "neutral"
    assert score_to_breezy(88, None) == "very_good"
    assert score_to_breezy(None, None) == "neutral"


def test_parse_partner_reference():
    assert parse_partner_reference("pos123:cand456") == ("pos123", "cand456")
    assert parse_partner_reference("cand-only") == (None, "cand-only")
    assert parse_partner_reference("") == (None, None)
