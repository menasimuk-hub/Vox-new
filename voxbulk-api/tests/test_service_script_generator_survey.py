from __future__ import annotations

import pytest

from app.services.service_script_generator import generate_survey_script


@pytest.fixture()
def db_session():
    from app.core.database import Base, get_engine, get_sessionmaker
    import app.models  # noqa: F401

    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    session = get_sessionmaker()()
    try:
        yield session
    finally:
        session.close()


def test_generate_phone_survey_script_caps_at_four_questions(db_session, monkeypatch):
    payload = {
        "intro": "Thanks for taking a moment.",
        "questions": [f"Question {i}?" for i in range(1, 7)],
        "closing": "Thank you.",
        "script_text": "",
        "system_prompt": "Run the survey politely.",
        "expected_duration_minutes": 8,
    }

    monkeypatch.setattr(
        "app.services.service_script_generator._complete_json",
        lambda *_args, **_kwargs: __import__("json").dumps(payload),
    )

    result = generate_survey_script(
        db_session,
        goal="Customer satisfaction",
        contact_method="AI phone call",
        max_call_length="4 minutes",
        organisation_name="Acme Clinic",
        client_name="Acme Clinic",
    )

    assert len(result["questions"]) == 4
    assert result["expected_duration_minutes"] <= 5
    assert "Question 4?" in result["script_text"]
    assert "Question 5?" not in result["script_text"]
