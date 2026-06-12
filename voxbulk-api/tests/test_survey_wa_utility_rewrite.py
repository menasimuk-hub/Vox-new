"""Tests for Meta UTILITY feedback survey BODY rewrite helpers."""

from __future__ import annotations

from app.services.survey_wa_utility_rewrite_service import (
    _extract_leading_emoji,
    _mentions_recent_interaction,
    _prepend_leading_emoji,
    _rule_based_utility_body,
    _topic_from_template_name,
    rewrite_body_for_utility,
)


def test_topic_from_template_name():
    assert _topic_from_template_name("voxbulk_survey_food_quality_abc_d85d5a") == "food quality"


def test_rule_based_adds_recent_visit_context():
    body = _rule_based_utility_body("How satisfied were you with our service?")
    assert _mentions_recent_interaction(body)
    assert "?" in body


def test_rule_based_preserves_leading_emoji():
    body = _rule_based_utility_body("😊 How satisfied were you with our service?")
    assert body.startswith("😊")
    assert _mentions_recent_interaction(body)


def test_rule_based_preserves_existing_utility_phrasing():
    original = "Following your recent visit, how was the food quality?"
    assert _rule_based_utility_body(original) == original


def test_extract_and_prepend_leading_emoji():
    assert _extract_leading_emoji("🎧 How was support?") == ("🎧", "How was support?")
    assert _prepend_leading_emoji("😊", "Following your recent visit, how was it?") == (
        "😊 Following your recent visit, how was it?"
    )
    assert _prepend_leading_emoji("😊", "😊 Already there") == "😊 Already there"


def test_rewrite_without_deepseek():
    class _FakeDb:
        pass

    out = rewrite_body_for_utility(
        _FakeDb(),
        original_body="😊 Overall, how satisfied were you?",
        button_labels=["Dissatisfied", "Satisfied", "Very satisfied"],
        template_name="voxbulk_survey_customer_service_rating_abc_de3a48",
        use_deepseek=False,
    )
    assert _mentions_recent_interaction(out)
    assert out.startswith("😊")
