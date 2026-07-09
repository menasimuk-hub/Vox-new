"""Tests for Meta UTILITY feedback survey BODY rewrite helpers."""

from __future__ import annotations

from app.services.survey_wa_utility_rewrite_service import (
    _extract_leading_emoji,
    _mentions_recent_interaction,
    _needs_utility_clone_for_category_change,
    _prepend_leading_emoji,
    _remote_item_is_marketing,
    _rule_based_utility_body,
    _topic_from_template_name,
    rewrite_body_for_utility,
)
from app.services.wa_template_meta_sync import (
    is_utility_clone_template_name,
    suggest_utility_clone_template_name,
)
from seed_data.wa_survey_template_naming import suggest_next_was_seq_name


def test_remote_item_is_marketing():
    assert _remote_item_is_marketing({"category": "MARKETING", "status": "APPROVED"}) is True
    assert _remote_item_is_marketing({"category": "UTILITY", "status": "APPROVED"}) is False


def test_topic_from_template_name():
    assert _topic_from_template_name("voxbulk_survey_food_quality_abc_d85d5a") == "food quality"
    assert _topic_from_template_name("voxbulk_survey_would_recommend_standard") == "would recommend"
    assert _topic_from_template_name("was_logistics_delivery_would_recommend_002_en") == "would recommend"
    assert _topic_from_template_name("was_employee_career_progression_001_en") == "career progression"


def test_rule_based_rewrites_nps_wording_without_lint_violation():
    from app.services.wa_template_utility_lint import lint_utility_template

    body = _rule_based_utility_body(
        "Based on your experience, how likely are you to recommend us to a friend?",
        topic_hint="would recommend",
        industry_slug="logistics_delivery",
    )
    lint = lint_utility_template(body=body, buttons=["Yes", "No"], language="en_GB", meta_category="utility")
    assert lint.ok
    assert "recommend" not in body.lower() or "recent" in body.lower()


def test_rule_based_rewrites_would_recommend_without_lint_violation():
    from app.services.wa_template_utility_lint import lint_utility_template

    body = _rule_based_utility_body(
        "Following your recent visit, would you recommend us to others?",
        topic_hint="would recommend",
        industry_slug="recruitment_staffing",
    )
    lint = lint_utility_template(body=body, buttons=["Yes", "No"], language="en_GB", meta_category="utility")
    assert lint.ok
    assert "would you recommend" not in body.lower()


def test_suggest_utility_clone_template_name():
    assert (
        suggest_utility_clone_template_name("voxbulk_survey_staff_friendliness_abc_875f3a")
        == "voxbulk_survey_staff_friendliness_utu_875f3a"
    )
    assert is_utility_clone_template_name("voxbulk_survey_staff_friendliness_utu_875f3a")


def test_suggest_next_was_seq_name():
    used = {"was_logistics_delivery_would_recommend_003_en"}
    assert (
        suggest_next_was_seq_name("was_logistics_delivery_would_recommend_002_en", used_names=used)
        == "was_logistics_delivery_would_recommend_004_en"
    )
    assert suggest_next_was_seq_name("voxbulk_survey_food_abc_123", used_names=set()) is None


def test_needs_utility_clone_for_category_change():
    class _Row:
        status = "APPROVED"
        category = "MARKETING"
        name = "voxbulk_survey_staff_friendliness_abc_875f3a"
        telnyx_record_id = "remote-1"

    assert _needs_utility_clone_for_category_change(_Row()) is True

    class _UtilityRow(_Row):
        category = "UTILITY"

    assert _needs_utility_clone_for_category_change(_UtilityRow()) is True

    class _CloneRow(_Row):
        name = "voxbulk_survey_staff_friendliness_utu_875f3a"

    assert _needs_utility_clone_for_category_change(_CloneRow()) is False


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
        use_llm=False,
    )
    assert _mentions_recent_interaction(out)
    assert out.startswith("😊")
