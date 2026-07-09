"""Tests for Meta UTILITY feedback survey BODY rewrite helpers."""

from __future__ import annotations

from app.services.survey_wa_utility_rewrite_service import (
    _extract_leading_emoji,
    _language_code_from_value,
    _mentions_recent_interaction,
    _needs_utility_clone_for_category_change,
    _prepend_leading_emoji,
    _remote_item_is_marketing,
    _rule_based_utility_body,
    _topic_from_template_name,
    parse_cfs_meta_name,
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
    assert _topic_from_template_name("cfs_hotel_atmosphere_es_v1") == "atmosphere"
    assert parse_cfs_meta_name("cfs_hotel_atmosphere_es_v1") == {
        "industry": "hotel",
        "topic_key": "atmosphere",
        "topic": "atmosphere",
        "lang": "es",
        "version": "1",
    }


def test_language_inferred_from_cfs_name_over_en_gb_default():
    assert _language_code_from_value("en_gb", template_name="cfs_hotel_atmosphere_es_v1") == "es"
    assert _language_code_from_value("en_gb", template_name="cfs_hotel_atmosphere_pl_v1") == "pl"
    assert _language_code_from_value("en_gb", template_name="cfs_hotel_atmosphere_en_v1") == "en"


def test_lang_variant_from_manifest_item_enriches_cfs_metadata():
    from app.services.survey_wa_utility_rewrite_service import lang_variant_from_manifest_item

    variant = lang_variant_from_manifest_item(
        {
            "remote_name": "cfs_hotel_atmosphere_es_v1",
            "language": "en_gb",
            "body_before": "🌆 ¿Cómo calificarías el ambiente y la atmósfera de nuestro hotel?",
            "buttons": ["Malo", "Regular", "Bueno"],
            "product": "feedback",
        }
    )
    assert variant.language == "es_gb"
    assert variant.industry_slug == "hotel"
    assert variant.topic_name == "atmosphere"
    assert variant.template_key == "atmosphere"


def test_rule_based_preserves_spanish_cfs_feedback_question():
    original = "🌆 ¿Cómo calificarías el ambiente y la atmósfera de nuestro hotel?"
    body = _rule_based_utility_body(
        original,
        topic_hint="atmosphere",
        industry_slug="hotel",
        language="es",
    )
    assert "¿Cómo calificarías" in body
    assert "how would you rate" not in body.lower()
    assert "cfs hotel atmosphere" not in body.lower()


def test_rewrite_preserves_spanish_cfs_without_llm():
    class _FakeDb:
        pass

    original = "🌆 ¿Cómo calificarías el ambiente y la atmósfera de nuestro hotel?"
    out = rewrite_body_for_utility(
        _FakeDb(),
        original_body=original,
        button_labels=["Malo", "Regular", "Bueno"],
        template_name="cfs_hotel_atmosphere_es_v1",
        industry_slug="hotel",
        topic_name="atmosphere",
        language="es",
        use_llm=False,
    )
    assert "¿Cómo calificarías" in out
    assert "how would you rate" not in out.lower()


def test_rule_based_rewrites_nps_wording_without_lint_violation():
    from app.services.wa_template_utility_lint import lint_utility_template

    body = _rule_based_utility_body(
        "Based on your experience, how likely are you to recommend us to a friend?",
        topic_hint="would recommend",
        industry_slug="logistics_delivery",
    )
    lint = lint_utility_template(body=body, buttons=["Yes", "No"], language="en_GB", meta_category="utility")
    assert lint.ok
    assert "your overall satisfaction" in body.lower()
    assert "how likely" not in body.lower()


def test_rule_based_rewrites_would_recommend_without_lint_violation():
    from app.services.wa_template_utility_lint import lint_utility_template

    body = _rule_based_utility_body(
        "Following your recent visit, would you recommend us to others?",
        topic_hint="would recommend",
        industry_slug="recruitment_staffing",
    )
    lint = lint_utility_template(body=body, buttons=["Yes", "No"], language="en_GB", meta_category="utility")
    assert lint.ok
    assert "your overall satisfaction" in body.lower()
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
    assert (
        suggest_next_was_seq_name("was_logistics_delivery_would_recommend_002_en_rb044", used_names=used)
        == "was_logistics_delivery_would_recommend_004_en"
    )
    assert (
        suggest_next_was_seq_name(
            "was_financial_services_would_recommend_002_en_r27a6_utu",
            used_names={"was_financial_services_would_recommend_003_en"},
        )
        == "was_financial_services_would_recommend_004_en"
    )
    assert suggest_next_was_seq_name("voxbulk_survey_food_abc_123", used_names=set()) is None


def test_rule_based_rewrites_repeat_purchase_intent():
    from app.services.wa_template_utility_lint import lint_utility_template

    body = _rule_based_utility_body(
        "Based on your recent visit, how likely are you to shop with us again?",
        topic_hint="repeat purchase intent",
        industry_slug="retail_ecommerce",
    )
    lint = lint_utility_template(body=body, buttons=["Yes", "No"], language="en_GB", meta_category="utility")
    assert lint.ok
    assert "how likely" not in body.lower()
    assert "shopping experience" in body.lower()
    assert "overall satisfaction" not in body.lower()


def test_rule_based_rewrites_employee_feeling_valued():
    body = _rule_based_utility_body(
        "Do you feel that your contributions are genuinely appreciated here?",
        topic_hint="feeling valued",
        industry_slug="employee_survey",
    )
    assert "how valued do you feel at work" in body.lower()


def test_normalize_leading_emoji_variation_selector():
    body = _rule_based_utility_body(
        "🗣️ At work, does your manager share information clearly?",
        topic_hint="manager communication",
        industry_slug="employee_survey",
    )
    assert not "🗣 ️" in body
    assert body.startswith("🗣")


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
