from app.services.billing_call_minutes import billable_call_minutes, call_outcome_label


def test_billable_call_minutes_rounding():
    assert billable_call_minutes(0) == 0
    assert billable_call_minutes(None) == 0
    assert billable_call_minutes(1) == 1
    assert billable_call_minutes(50) == 1
    assert billable_call_minutes(60) == 1
    assert billable_call_minutes(65) == 2
    assert billable_call_minutes(120) == 2
    assert billable_call_minutes(121) == 3


def test_call_outcome_label():
    assert call_outcome_label(status="completed") == "Completed (AI survey)"
    assert call_outcome_label(status="no_answer") == "No answer"
    assert call_outcome_label(status="busy") == "Busy"
    assert call_outcome_label(status="completed", voicemail=True) == "Voicemail / answering machine"
