from __future__ import annotations

from app.abuu.services.agent_settings_seed import seed_agent_settings
from app.abuu.services.kb_service import answer_kb_question, detect_kb_topic, format_greeting, resolve_settings
from app.core.abuu_database import get_abuu_sessionmaker, run_abuu_migrations


def test_kb_answers_delivery_fee():
    run_abuu_migrations()
    with get_abuu_sessionmaker()() as db:
        seed_agent_settings(db)
        db.commit()
        settings = resolve_settings(db)
        answer = answer_kb_question(settings, "delivery_fee", "en")
    assert answer is not None
    assert "15.00" in answer or "15" in answer


def test_kb_no_invented_refund():
    run_abuu_migrations()
    with get_abuu_sessionmaker()() as db:
        settings = resolve_settings(db)
        answer = answer_kb_question(settings, "refund", "en")
    assert answer is None or "review" in answer.lower() or "24" in answer


def test_detect_kb_topic_hours():
    assert detect_kb_topic("what are your opening hours") == "hours"
    assert detect_kb_topic("ساعات العمل") == "hours"


def test_greeting_uses_name():
    run_abuu_migrations()
    with get_abuu_sessionmaker()() as db:
        seed_agent_settings(db)
        db.commit()
        settings = resolve_settings(db)
        msg = format_greeting(settings, first_name="Sara", lang="en")
    assert "Sara" in msg


def test_demo_settings_seed():
    run_abuu_migrations()
    with get_abuu_sessionmaker()() as db:
        result = seed_agent_settings(db)
        db.commit()
        settings = resolve_settings(db, restaurant_id="abuu-rest-chicken")
    assert result["global"] == 1
    assert settings.prep_minutes == 20
    assert settings.min_order_agorot == 3000
