"""Tests for Meta UTILITY template lint."""

from __future__ import annotations

from app.services.wa_template_utility_lint import (
    lint_utility_body,
    lint_utility_template,
    merge_lint_results,
)


def test_utility_body_passes_with_transaction_anchor():
    result = lint_utility_body(
        "😊 Following your recent visit, how satisfied are you with the service you received today?"
    )
    assert result.ok


def test_utility_body_fails_recommend_friend():
    result = lint_utility_body("😊 Would you recommend us to a friend?")
    assert not result.ok
    assert any("recommend" in i.message.lower() or "friend" in i.message.lower() for i in result.issues)


def test_utility_body_fails_missing_anchor():
    result = lint_utility_body("How satisfied were you with our service?")
    assert not result.ok


def test_utility_body_fails_loyalty():
    result = lint_utility_body("Following your recent visit, how valuable is our loyalty programme?")
    assert not result.ok


def test_utility_template_wrong_category():
    result = lint_utility_template(
        body="😊 Following your recent visit, how was the food quality today?",
        buttons=["Good", "Fair", "Poor"],
        meta_category="marketing",
    )
    assert not result.ok


def test_marketing_opt_in_excluded():
    result = lint_utility_template(
        body="Join our club for exclusive deals!",
        buttons=["Yes"],
        meta_category="marketing",
        template_key="marketing_opt_in",
    )
    assert result.ok


def test_merge_lint_results():
    a = lint_utility_body("Would you recommend us?")
    b = lint_utility_body("😊 Following your recent visit, how was it?")
    merged = merge_lint_results(a, b)
    assert not merged.ok
    assert len(merged.issues) >= 2
