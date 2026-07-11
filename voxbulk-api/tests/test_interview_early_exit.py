"""Early-exit classification for interview sessions."""

from app.services.interview_early_exit_service import classify_interview_session_outcome


def test_not_free_is_reschedule():
    assert (
        classify_interview_session_outcome(
            duration_seconds=60,
            transcript="I'm not free right now, can I reschedule the appointment?",
        )
        == "reschedule"
    )


def test_recording_declined_is_hard_stop():
    assert (
        classify_interview_session_outcome(
            duration_seconds=40,
            transcript="No I don't consent to being recorded.",
        )
        == "recording_declined"
    )


def test_wrong_person_early():
    assert (
        classify_interview_session_outcome(
            duration_seconds=25,
            transcript="Sorry, wrong person, you have the wrong number.",
        )
        == "wrong_person"
    )


def test_short_silent_is_technical_abort():
    assert classify_interview_session_outcome(duration_seconds=40, transcript="") == "technical_abort"


def test_ambiguous_short_is_reschedule():
    assert classify_interview_session_outcome(duration_seconds=100, transcript="") == "reschedule"


def test_mid_interview_stop_stays_completed():
    long_transcript = (
        "First question: tell me about your experience. "
        "I worked five years in retail managing a team. "
        "Next question: can you describe a challenge you solved? "
        "We had stock issues and I fixed the process. "
        "I need to stop now and reschedule for later please."
    )
    assert (
        classify_interview_session_outcome(duration_seconds=240, transcript=long_transcript)
        == "completed"
    )


def test_substantial_duration_completed_without_transcript():
    assert classify_interview_session_outcome(duration_seconds=200, transcript=None) == "completed"
