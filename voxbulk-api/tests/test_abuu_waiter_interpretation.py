"""Protected lexicon — كولا, دجاج, شاورما must not be destructively rewritten."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.abuu.voice_interpretation.domain_lexicon import lexicon_correct
from app.abuu.waiter.interpretation import WaiterInterpretation
from app.abuu.waiter.protected_lexicon import (
    category_hints_for_text,
    conservative_transcript,
    detect_protected_tokens,
    token_must_not_map_to,
)
from app.abuu.services.seed_service import AbuuSeedService


@pytest.fixture
def abuu_seeded(app_client):
    from sqlalchemy import select

    from app.abuu.models.entities import Restaurant
    from app.core.abuu_database import get_abuu_sessionmaker

    with get_abuu_sessionmaker()() as db:
        AbuuSeedService.seed_restaurants_if_empty(db)
        db.commit()
        restaurant = db.execute(select(Restaurant).limit(1)).scalar_one()
        yield db, restaurant


def test_cola_stays_cola_not_drinks_category_word():
    text = conservative_transcript("بدي كولا", language="ar")
    assert "كولا" in text
    assert "مشروبات" not in text
    hints = category_hints_for_text(text, language="ar")
    assert "drinks" in hints
    protected = detect_protected_tokens(text, language="ar")
    assert "كولا" in protected


def test_chicken_never_maps_to_meat():
    assert token_must_not_map_to("دجاج", "meat") is True
    assert token_must_not_map_to("دجاج", "لحم") is True
    text = conservative_transcript("بدي دجاج", language="ar")
    assert "دجاج" in text
    assert "لحم" not in text


def test_shawarma_stays_shawarma():
    text = conservative_transcript("شاورما دجاج", language="ar")
    assert "شاورما" in text
    protected = detect_protected_tokens(text, language="ar")
    assert "شاورما" in protected


def test_legacy_lexicon_still_maps_cola_for_direct_tests():
    """Document legacy destructive behavior — waiter path must not use this for transcript."""
    corrected, categories, _conf = lexicon_correct("كولا", language="ar")
    assert "drinks" in categories
    assert corrected  # legacy may rewrite; waiter uses conservative_transcript instead


def test_waiter_interpretation_preserves_cola(abuu_seeded):
    db, _restaurant = abuu_seeded
    result = WaiterInterpretation.interpret(
        db,
        MagicMock(),
        transcript="بدي كولا",
        stt_confidence=0.8,
        session=None,
        customer=None,
        lang="ar",
        is_voice=True,
    )
    assert "كولا" in result.corrected_transcript
    assert "مشروبات" not in result.corrected_transcript
    assert "drinks" in result.category_hints
    assert result.should_block_turn() is False


def test_long_greeting_chicken_voice_no_clarify(abuu_seeded):
    db, _restaurant = abuu_seeded
    result = WaiterInterpretation.interpret(
        db,
        MagicMock(),
        transcript="مرحبا كيف الحال؟ أريد أن أكل دجاج، ما لديك دجاج؟",
        stt_confidence=0.9,
        session=None,
        customer=None,
        lang="ar",
        is_voice=True,
    )
    assert result.should_block_turn() is False
    assert "chicken" in result.category_hints
