from app.services.service_script_generator import _order_cv_questions_first, _sync_script_questions


def test_order_cv_questions_first_moves_cv_questions_to_start():
    questions = [
        "Do you hold GDC registration?",
        "Are you willing to travel?",
        "Tell me about your role at Smile Dental on your CV.",
        "What achievement from your CV are you most proud of?",
    ]
    ordered = _order_cv_questions_first(questions)
    assert ordered[0].startswith("Tell me about your role")
    assert ordered[1].startswith("What achievement")
    assert ordered[2:] == questions[:2]


def test_sync_script_questions_rewrites_questions_block():
    script = "\n".join(
        [
            "OPENING DISCLOSURE",
            "Recorded line.",
            "",
            "INTRO",
            "Quick screening call.",
            "",
            "QUESTIONS",
            "1. Criteria question one",
            "2. Criteria question two",
            "3. Tell me about your experience on your CV.",
            "4. What gap stands out on your CV?",
            "",
            "CLOSING",
            "Thank you.",
        ]
    )
    synced = _sync_script_questions(
        script,
        "Quick screening call.",
        [
            "Criteria question one",
            "Criteria question two",
            "Tell me about your experience on your CV.",
            "What gap stands out on your CV?",
        ],
        "Thank you.",
    )
    assert "1. Tell me about your experience on your CV." in synced
    assert "3. Criteria question one" in synced
    assert "OPENING DISCLOSURE" in synced
