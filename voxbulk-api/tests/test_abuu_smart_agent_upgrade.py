from __future__ import annotations

from app.abuu.agent.pending_action import is_cart_inquiry
from app.abuu.agent.voice_gate import voice_transcript_usable
from app.abuu.models.entities import Restaurant, RestaurantMenuItem
from app.abuu.services.abuu_voice_service import AbuuVoiceTranscription
from app.abuu.services.reply_service import conversational_menu_message


def test_voice_transcript_usable_rejects_empty():
    assert not voice_transcript_usable("")
    assert not voice_transcript_usable("   ")


def test_voice_transcript_usable_rejects_failed_voice():
    voice = AbuuVoiceTranscription(ok=False, transcript="hello", confidence=0.1)
    assert not voice_transcript_usable("hello", voice=voice)


def test_cart_inquiry_basket_phrases():
    assert is_cart_inquiry("show me basket")
    assert is_cart_inquiry("what is in my cart")
    assert is_cart_inquiry("شو عندي بالسلة")


def test_cart_inquiry_beats_menu_browse_when_explicit():
    assert is_cart_inquiry("show my basket menu", menu_browse=True)


def test_conversational_menu_message_is_numbered():
    restaurant = Restaurant(id="r1", name_en="Test", name_ar="تست")
    item = RestaurantMenuItem(
        id="i1",
        name_en="Kunafa",
        name_ar="كنافة",
        price_agorot=3500,
        category_id="c1",
    )
    text = conversational_menu_message(
        restaurant,
        [(1, item)],
        categories=["desserts"],
        lang="ar",
    )
    assert "1. كنافة" in text
    assert "•" not in text
    assert "1 2 3" in text or "مساعدة" in text
