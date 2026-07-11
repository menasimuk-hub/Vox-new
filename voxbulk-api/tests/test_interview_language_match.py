"""Interview language must match agent; brand tokens must not flip English → Arabic."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.voice_agent_runtime import (
    InterviewAgentLanguageMismatch,
    assert_interview_agent_language_match,
    call_should_use_arabic,
    detect_config_language,
    detect_interview_language,
    resolve_interview_language,
)


def _agent(*, slug: str, name: str, arabic_opening: bool = False) -> SimpleNamespace:
    return SimpleNamespace(
        slug=slug,
        name=name,
        voice_label=name,
        voice_type_label="",
        opening_disclosure_template="مرحباً، ممكن اتكلم مع {first_name}؟" if arabic_opening else "Hello, is this {first_name}?",
        system_prompt="British English interviewer." if not arabic_opening else "محاور عربي.",
    )


LEO = _agent(slug="interview-gb-leo", name="interview_GB-Leo")
JAMMAL = _agent(slug="interview-ar-jammal", name="interview_AR-Jammal", arabic_opening=True)

EN_SCRIPT_BBC = (
    "OPENING DISCLOSURE\nHello, is this there?\n\n"
    "INTRO\nDo you have about 10 minutes for a short screening interview "
    "about the video editor role with BBC عربي?\n\n"
    "QUESTIONS\n1. Tell me about a recent video editing project."
)

AR_SCRIPT = (
    "الإفصاح\nمرحبا، هل أنت أحمد؟\n\n"
    "المقدمة\nهل لديك عشر دقائق لمقابلة قصيرة؟\n\n"
    "الأسئلة\n1. حدثنا عن نفسك."
)


def test_resolve_prefers_explicit_english_with_bbc_token():
    config = {
        "script_language_code": "en",
        "approved_script": EN_SCRIPT_BBC,
    }
    assert resolve_interview_language(config) == "en"
    assert detect_interview_language(config, LEO) == "en"
    assert call_should_use_arabic(LEO, config=config) is False


def test_english_leo_with_bbc_token_no_explicit_lang_uses_ratio():
    config = {"approved_script": EN_SCRIPT_BBC}
    assert detect_config_language(config) == "en"
    assert resolve_interview_language(config) == "en"
    assert detect_interview_language(config, LEO) == "en"


def test_arabic_jammal_english_script_explicit_ar():
    config = {
        "script_language_code": "ar",
        "approved_script": "Hello world screening questions only in English text.",
    }
    assert detect_interview_language(config, JAMMAL) == "ar"
    assert call_should_use_arabic(JAMMAL, config=config) is True


def test_mismatch_english_interview_arabic_agent():
    config = {"script_language_code": "en", "approved_script": EN_SCRIPT_BBC}
    with pytest.raises(InterviewAgentLanguageMismatch, match="English"):
        assert_interview_agent_language_match(config, JAMMAL)


def test_mismatch_arabic_interview_english_agent():
    config = {"script_language_code": "ar", "approved_script": AR_SCRIPT}
    with pytest.raises(InterviewAgentLanguageMismatch, match="Arabic"):
        assert_interview_agent_language_match(config, LEO)


def test_require_agent():
    config = {"script_language_code": "en"}
    with pytest.raises(InterviewAgentLanguageMismatch, match="Select an AI voice agent"):
        assert_interview_agent_language_match(config, None, require_agent=True)


def test_majority_arabic_script_without_explicit_lang():
    config = {"approved_script": AR_SCRIPT}
    assert resolve_interview_language(config) == "ar"
    assert detect_interview_language(config, JAMMAL) == "ar"
