"""Tests for optional final additional feedback before thank-you."""

from __future__ import annotations

from app.services.survey_wa_final_feedback_service import (
    DEFAULT_OPEN_TEXT_PROMPT,
    DEFAULT_YES_NO_QUESTION,
    build_final_feedback_branch,
    final_feedback_settings,
    parse_final_feedback_yes_no,
    persist_final_feedback_text,
    persist_final_feedback_yes_no,
    runtime_final_feedback_enabled,
)


def test_final_feedback_defaults_off():
    assert runtime_final_feedback_enabled({}) is False
    settings = final_feedback_settings({})
    assert settings["enabled"] is False
    assert settings["yes_no_question"] == DEFAULT_YES_NO_QUESTION
    assert settings["open_text_prompt"] == DEFAULT_OPEN_TEXT_PROMPT


def test_final_feedback_enabled_from_config():
    cfg = {
        "allow_final_additional_feedback": True,
        "builder_runtime": {
            "branches": {
                "final_additional_feedback": build_final_feedback_branch(enabled=True),
            }
        },
    }
    assert runtime_final_feedback_enabled(cfg) is True


def test_parse_yes_no_variants():
    assert parse_final_feedback_yes_no("Yes") == "Yes"
    assert parse_final_feedback_yes_no("no") == "No"
    assert parse_final_feedback_yes_no("2") == "No"
    assert parse_final_feedback_yes_no("1") == "Yes"
    assert parse_final_feedback_yes_no("maybe") is None


def test_persist_final_feedback_fields():
    payload: dict = {"wa_conversation": {"answers": []}}
    settings = final_feedback_settings({"allow_final_additional_feedback": True})
    persist_final_feedback_yes_no(payload, choice="Yes", settings=settings)
    assert payload["final_feedback_yes_no"] == "Yes"
    persist_final_feedback_text(payload, text="Staff were rude", settings=settings)
    assert payload["final_additional_feedback"] == "Staff were rude"
    roles = [a.get("step_role") for a in payload["wa_conversation"]["answers"]]
    assert "final_feedback_yes_no" in roles
    assert "final_feedback_text" in roles
    assert any(item.get("final_additional_feedback") for item in payload["extracted_answers"])


def test_builder_runtime_branch_shape():
    branch = build_final_feedback_branch(enabled=True)
    assert branch.get("enabled") is True
    assert branch.get("yes_no_question") == DEFAULT_YES_NO_QUESTION
    assert branch.get("open_text_prompt") == DEFAULT_OPEN_TEXT_PROMPT
