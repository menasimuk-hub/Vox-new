from __future__ import annotations

from app.abuu.services.conversation_ai_service import classify_regex
from app.abuu.services.skill_definitions import (
    SKILL_ANSWER_KB,
    SKILL_GREET_CUSTOMER,
    SKILL_MENU_RECOMMEND,
    SKILL_RESTAURANT_SEARCH,
)
from app.abuu.services.skill_router import AbuuSkillRouter, TurnContext
from app.abuu.services.conversation_ai_service import SkillClassification


def test_skill_classify_greet():
    result = classify_regex("abuu", step=None, has_session=False)
    assert result.skill == SKILL_GREET_CUSTOMER


def test_skill_classify_menu_recommend():
    result = classify_regex("chicken please", step="awaiting_preference", has_session=True)
    assert result.skill == SKILL_MENU_RECOMMEND
    assert "chicken" in result.categories


def test_skill_classify_restaurant_list():
    result = classify_regex("show restaurants", step="awaiting_preference", has_session=True)
    assert result.skill == SKILL_RESTAURANT_SEARCH


def test_skill_classify_kb():
    result = classify_regex("what is the delivery fee", step="browsing", has_session=True)
    assert result.skill == SKILL_ANSWER_KB
    assert result.kb_topic == "delivery_fee"
