"""Tests for Meta UTILITY template lint."""

from __future__ import annotations

from app.services.wa_template_utility_lint import (
    clamp_utility_button_label,
    clamp_utility_button_labels,
    lint_utility_body,
    lint_utility_template,
    merge_lint_results,
)


def test_utility_body_fails_nps_recommend_likelihood():
    result = lint_utility_body(
        "📋 Based on your recent experience with us, how likely are you to recommend our service? "
        "Reply with one option below."
    )
    assert not result.ok
    assert any("recommend" in i.message.lower() for i in result.issues)


def test_utility_buttons_fail_would_recommend_labels():
    result = lint_utility_template(
        body="📋 How was overall satisfaction in your recent experience with us? Reply with one option below.",
        buttons=["Would Recommend", "Neutral", "Would Not Recommend"],
        language="en_GB",
        meta_category="utility",
    )
    assert not result.ok
    assert any(i.field.startswith("button_") for i in result.issues)


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


def test_utility_body_spanish_does_not_require_english_anchor():
    result = lint_utility_template(
        body="🌆 ¿Cómo calificarías el ambiente y la atmósfera de nuestro hotel?",
        buttons=["Malo", "Regular", "Bueno"],
        language="es_gb",
        meta_category="utility",
    )
    assert result.ok


def test_utility_body_polish_does_not_require_english_anchor():
    result = lint_utility_template(
        body="🌆 Jak oceniasz atmosferę i klimat naszego hotelu?",
        buttons=["Źle", "Średnio", "Dobrze"],
        language="pl_gb",
        meta_category="utility",
    )
    assert result.ok


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


def test_clamp_utility_button_label_shortens_long_options():
    assert len(clamp_utility_button_label("Very clean & hygienic")) <= 20
    assert clamp_utility_button_label("Exceeded expectations") == "Above expectations"
    assert clamp_utility_button_label("Completely transparent") == "Fully transparent"
    assert clamp_utility_button_label("Very warm & welcoming") == "Very welcoming"
    result = lint_utility_template(
        body="Following your recent visit, how clean was it?",
        buttons=clamp_utility_button_labels(
            ["Needs improvement", "Clean", "Very clean & hygienic"]
        ),
        meta_category="utility",
    )
    assert result.ok
