"""Callback-consent Yes/No matching must survive STT language flips + translation punctuation."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.customer_feedback.feedback_answer_service import is_opt_in_no, is_opt_in_yes


def test_latin_no_matches_when_session_language_is_arabic():
    db = MagicMock()
    with patch(
        "app.services.customer_feedback.feedback_answer_service.map_answer_to_english_label",
        return_value="no.",
    ) as mapped:
        assert is_opt_in_no(db, answer="No", tpl=None, detected_language="ar") is True
        assert is_opt_in_yes(db, answer="No", tpl=None, detected_language="ar") is False
        # Raw Latin match should short-circuit before translation.
        mapped.assert_not_called()


def test_translated_no_with_period_matches():
    db = MagicMock()
    with patch(
        "app.services.customer_feedback.feedback_answer_service.map_answer_to_english_label",
        return_value="no.",
    ):
        # Non-obvious token still goes through map + punctuation strip.
        assert is_opt_in_no(db, answer="لا شكرا", tpl=None, detected_language="ar") is True


def test_arabic_la_matches_no():
    db = MagicMock()
    assert is_opt_in_no(db, answer="لا", tpl=None, detected_language="ar") is True
    assert is_opt_in_yes(db, answer="نعم", tpl=None, detected_language="ar") is True
