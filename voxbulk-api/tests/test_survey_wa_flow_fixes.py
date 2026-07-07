"""Unit tests for the survey-flow fixes:

- tell-us-more fires after every low-rated question (per-step, not one-shot)
- final-feedback answers carry a sort index so results stay in survey order
- text answers get translation enqueued on every save path
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.survey_results_service import (
    build_extracted_answer_entries,
    sort_survey_answer_items,
)
from app.services.survey_wa_final_feedback_service import (
    persist_final_feedback_text,
    persist_final_feedback_yes_no,
)
from app.services.survey_wa_open_text_state import (
    mark_tell_us_more_fired_for_step,
    tell_us_more_already_fired_for_step,
)


def test_tell_us_more_fires_per_step_not_once_per_session():
    conv: dict = {}

    # Nothing fired yet.
    assert tell_us_more_already_fired_for_step(conv, 1) is False

    # First low rating at step 1 fires tell-us-more.
    mark_tell_us_more_fired_for_step(conv, 1)
    assert tell_us_more_already_fired_for_step(conv, 1) is True

    # A later low rating at step 3 is still eligible (old one-shot gate would block it).
    assert tell_us_more_already_fired_for_step(conv, 3) is False
    mark_tell_us_more_fired_for_step(conv, 3)
    assert tell_us_more_already_fired_for_step(conv, 3) is True

    # Same step never fires twice.
    assert tell_us_more_already_fired_for_step(conv, 1) is True
    assert sorted(conv["tell_us_more_fired_steps"]) == [1, 3]


def test_tell_us_more_gate_ignores_legacy_asked_flag():
    # Legacy sessions only set tell_us_more_asked; the per-step gate must not
    # treat that as "already fired for this step".
    conv = {"tell_us_more_asked": True}
    assert tell_us_more_already_fired_for_step(conv, 2) is False


def test_final_feedback_answers_carry_sort_index():
    payload: dict = {
        "wa_conversation": {
            "answers": [
                {"question": "Q1", "answer": "Manageable", "answer_index": 0, "step_index": 1},
                {"question": "Q2", "answer": "Poor", "answer_index": 1, "step_index": 2},
            ]
        }
    }
    persist_final_feedback_yes_no(payload, choice="Yes", settings={})
    persist_final_feedback_text(payload, text="please call me", settings={})

    answers = payload["wa_conversation"]["answers"]
    assert answers[-2]["answer_index"] == 2
    assert answers[-1]["answer_index"] == 3


def test_results_keep_survey_order_without_index_collisions():
    payload: dict = {
        "wa_conversation": {
            "answers": [
                {"question": "Q1", "answer": "Manageable", "answer_index": 0},
                {"question": "Q2", "answer": "Poor", "answer_index": 1},
            ]
        }
    }
    persist_final_feedback_text(payload, text="thanks", settings={})
    answers = payload["wa_conversation"]["answers"]

    ordered = sort_survey_answer_items(answers)
    questions = [row["question"] for row in ordered]
    # Final feedback stays last, mid answers keep their order.
    assert questions[0] == "Q1"
    assert questions[1] == "Q2"
    assert questions[-1] == ordered[-1]["question"]

    extracted = build_extracted_answer_entries(answers)
    # No duplicated entries, one per answer.
    assert len(extracted) == len(answers)


def test_save_result_enqueues_translation_for_untranslated_text_only():
    from app.services import survey_whatsapp_conversation_service as svc

    recipient = MagicMock()
    recipient.id = "rec-1"
    payload = {
        "wa_conversation": {
            "answers": [
                # English rating -> no translation needed
                {"answer": "Poor", "answer_index": 0},
                # non-English typed answer -> should enqueue
                {"answer": "شكرا جزيلا", "answer_index": 1},
                # already translated -> skip
                {"answer": "hello", "translated_text": "hello", "translation_status": "completed", "answer_index": 2},
                # voice note -> handled by voice pipeline, skip
                {"answer": "مرحبا", "answer_source": "voice_note", "answer_index": 3},
            ]
        }
    }

    with patch(
        "app.services.survey_wa_translation_service.SurveyWaTranslationService.enqueue_answer_translation"
    ) as enqueue:
        svc._enqueue_text_answer_translation(recipient, payload)

    enqueued_indexes = [call.kwargs.get("answer_index") for call in enqueue.call_args_list]
    assert enqueued_indexes == [1]
