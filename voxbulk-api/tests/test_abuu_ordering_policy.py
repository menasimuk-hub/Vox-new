"""Tests for shared ordering policy — proceed when food intent is clear."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.abuu.waiter.ordering_policy import (
    dominant_categories,
    extract_food_query,
    has_strong_food_signal,
    is_generic_clarify_reply,
    should_block_turn_for_clarification,
)
from app.abuu.waiter.interpretation import WaiterInterpretation
from app.abuu.services.seed_service import AbuuSeedService


@pytest.fixture
def abuu_seeded(app_client):
    from app.core.abuu_database import get_abuu_sessionmaker

    with get_abuu_sessionmaker()() as db:
        AbuuSeedService.seed_restaurants_if_empty(db)
        db.commit()
        yield db


def test_strong_food_signal_with_protected_djaj():
    assert has_strong_food_signal(protected_tokens=["دجاج"], category_hints=["chicken"], stt_confidence=0.9)


def test_low_confidence_does_not_block_when_chicken_clear():
    assert (
        should_block_turn_for_clarification(
            reason="low_confidence",
            protected_tokens=["دجاج"],
            category_hints=["chicken"],
            stt_confidence=0.9,
        )
        is False
    )


def test_dominant_category_picks_chicken_over_noise():
    assert dominant_categories(["chicken", "salad", "chips"]) == ["chicken"]


def test_extract_food_query_from_long_greeting():
    text = "مرحبا كيف الحال؟ أريد أن أكل دجاج، ما لديك دجاج؟"
    q = extract_food_query(text, protected_tokens=["دجاج"], category_hints=["chicken"])
    assert "دجاج" in q


def test_generic_clarify_phrase_detected():
    assert is_generic_clarify_reply("ممكن توضّح شو بدك بالضبط؟")


def test_long_voice_chicken_does_not_need_clarification(abuu_seeded):
    db = abuu_seeded
    transcript = "مرحبا كيف الحال؟ أريد أن أكل دجاج، ما لديك دجاج؟"
    result = WaiterInterpretation.interpret(
        db,
        MagicMock(),
        transcript=transcript,
        stt_confidence=0.9,
        session=None,
        customer=None,
        lang="ar",
        is_voice=True,
    )
    assert "دجاج" in result.corrected_transcript
    assert "chicken" in result.category_hints
    assert result.should_block_turn() is False
    assert result.clarification_reason != "low_confidence" or not result.needs_clarification
