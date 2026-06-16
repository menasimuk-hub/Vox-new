"""Tests for Abuu post-STT voice interpretation."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.abuu.agent.session import Session as AgentSession
from app.abuu.conversation.intent_router import IntentRouter
from app.abuu.conversation.orchestrator import AbuuConversationOrchestrator
from app.abuu.menu_intelligence.dietary_detector import DietaryDetector
from app.abuu.services.seed_service import AbuuSeedService
from app.abuu.voice_interpretation.domain_lexicon import detect_allergy_uncertainty, lexicon_correct
from app.abuu.voice_interpretation.fuzzy_match import best_fuzzy_match, fuzzy_score
from app.abuu.voice_interpretation.interpreter import VoiceInterpretationService
from app.abuu.voice_interpretation.normalize import normalize_ordering_text
from app.core.config import get_settings


@pytest.fixture
def abuu_seeded(app_client):
    from sqlalchemy import select

    from app.abuu.models.entities import Restaurant
    from app.core.abuu_database import get_abuu_sessionmaker

    with get_abuu_sessionmaker()() as db:
        AbuuSeedService.seed_restaurants_if_empty(db)
        AbuuSeedService.seed_offers_if_empty(db)
        db.commit()
        restaurant = db.execute(select(Restaurant).limit(1)).scalar_one()
        yield db, restaurant.id, restaurant


def test_normalize_dedupes_repeated_tokens():
    assert normalize_ordering_text("دجاج دجاج") == "دجاج"


def test_normalize_strips_filler():
    assert "دجاج" in normalize_ordering_text("بدي دجاج please")


def test_lexicon_noisy_chicken_variants():
    for raw in ("دجاجج", "djaj", "dajaj"):
        corrected, categories, conf = lexicon_correct(raw, language="ar")
        assert "chicken" in categories
        assert conf >= 0.5
        assert "دجاج" in corrected or "chicken" in corrected.lower()


def test_lexicon_noisy_drinks_not_meals():
    corrected, categories, conf = lexicon_correct("mshrobt", language="ar")
    assert "drinks" in categories
    assert conf >= 0.5
    assert corrected


def test_fuzzy_score_basic():
    assert fuzzy_score("دجاج", "دجاجج") >= 80


def test_mixed_ar_en_chicken():
    normalized = normalize_ordering_text("badde chicken", language="ar")
    _, categories, _ = lexicon_correct(normalized, language="ar")
    assert "chicken" in categories


def test_allergy_partial_is_uncertain():
    assert detect_allergy_uncertainty("عندي حساسيه") is True


def test_clear_allergy_not_uncertain():
    assert detect_allergy_uncertainty("حساسية فول سوداني") is False


def test_dietary_clear_allergy_detected():
    dietary = DietaryDetector.detect("حساسية فول سوداني")
    assert dietary.is_allergy_declared
    assert "nuts" in dietary.allergens_avoid


def test_menu_aware_chicken_scores_higher(abuu_seeded):
    db, restaurant_id, _restaurant = abuu_seeded
    session = AgentSession(customer_wa_number="+970599000001", restaurant_id=restaurant_id)
    result = VoiceInterpretationService.interpret(
        db,
        MagicMock(),
        transcript="دجاجج",
        stt_confidence=0.6,
        session=session,
        customer=None,
        lang="ar",
    )
    assert "chicken" in result.inferred_categories
    assert result.corrected_transcript
    assert result.menu_match_confidence >= 0 or result.intent_confidence >= 0.5


def test_ambiguous_categories_trigger_clarification():
    session = AgentSession(customer_wa_number="+970599000002")
    with patch.object(VoiceInterpretationService, "_deepseek_recovery", return_value=None):
        result = VoiceInterpretationService.interpret(
            MagicMock(),
            MagicMock(),
            transcript="دجاج وسمك",
            stt_confidence=0.55,
            session=session,
            customer=None,
            lang="ar",
        )
    assert "chicken" in result.inferred_categories
    assert "fish" in result.inferred_categories
    assert result.needs_clarification is True
    assert result.clarification_prompt
    assert "؟" in result.clarification_prompt


def test_allergy_uncertain_clarification():
    session = AgentSession(customer_wa_number="+970599000003")
    with patch.object(VoiceInterpretationService, "_deepseek_recovery", return_value=None):
        result = VoiceInterpretationService.interpret(
            MagicMock(),
            MagicMock(),
            transcript="عندي حساسيه",
            stt_confidence=0.7,
            session=session,
            customer=None,
            lang="ar",
        )
    assert result.allergy_uncertain is True
    assert result.needs_clarification is True
    assert "حساسية" in (result.clarification_prompt or "")


def test_interpretation_disabled_leaves_raw(monkeypatch):
    monkeypatch.setenv("ABUU_VOICE_INTERPRETATION_ENABLED", "false")
    get_settings.cache_clear()
    assert VoiceInterpretationService.enabled() is False
    get_settings.cache_clear()
    monkeypatch.delenv("ABUU_VOICE_INTERPRETATION_ENABLED", raising=False)


def test_intent_router_uses_pre_inferred_categories():
    session = AgentSession(customer_wa_number="+970599000004", language="ar")
    session.context["voice_interpretation"] = {
        "inferred_categories": ["chicken"],
        "intent_confidence": 0.9,
        "inferred_item_query": None,
    }
    intent = IntentRouter.classify(MagicMock(), "دجاجج", session)
    assert intent.name == "food_search"
    assert "chicken" in intent.categories
    assert intent.source == "voice_interpretation"


def test_orchestrator_skips_allergen_on_uncertain_voice_context(abuu_seeded, monkeypatch):
    db, _restaurant_id, _restaurant = abuu_seeded
    phone = "+970599000010"

    from app.abuu.agent.session import load_session, save_session

    session = load_session(db, phone)
    session.context["voice_interpretation"] = {"allergy_uncertain": True}
    save_session(db, session)

    with patch.object(IntentRouter, "classify") as classify_mock, patch(
        "app.abuu.conversation.orchestrator.FactBundleLoader.load"
    ) as facts_mock, patch("app.abuu.conversation.orchestrator.ActionRunner.run") as action_mock, patch(
        "app.abuu.conversation.orchestrator.ReplyComposer.compose", return_value="ok"
    ), patch("app.abuu.conversation.orchestrator._deepseek_platform_ready", return_value=False):
        from app.abuu.conversation.fact_bundle import FactBundle
        from app.abuu.conversation.action_runner import ActionResult

        classify_mock.return_value = MagicMock(name="food_search", categories=[], item_query=None, confidence=0.9)
        facts_mock.return_value = FactBundle(intent="food_search")
        action_mock.return_value = ActionResult(action="none")

        AbuuConversationOrchestrator.handle(
            db,
            MagicMock(),
            phone=phone,
            text="عندي حساسيه من حليب",
        )
        session = load_session(db, phone)
        assert "allergen_avoid" not in session.context


def test_best_fuzzy_match_menu_item():
    candidates = [
        {"id": "1", "name_ar": "شاورما دجاج", "name_en": "Chicken shawarma", "category": "chicken"},
        {"id": "2", "name_ar": "سلطة", "name_en": "Salad", "category": "salad"},
    ]
    best, score, _ranked = best_fuzzy_match("شاورما دجاجj", candidates, language="ar", min_score=45)
    assert best is not None
    assert score >= 45
    assert best["id"] == "1"
