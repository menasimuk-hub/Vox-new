from app.services.interview_ats_service import (
    compute_ats_input_hash,
    sanitize_cv_text,
    _parse_ats_score,
)


def test_sanitize_cv_text_strips_control_chars():
    raw = "Hello\x00\x07World\n\n  skills  "
    assert "\x00" not in sanitize_cv_text(raw)
    assert "Hello" in sanitize_cv_text(raw)


def test_compute_ats_hash_stable():
    h1 = compute_ats_input_hash(cv_text="same cv", job_description="Backend dev")
    h2 = compute_ats_input_hash(cv_text="same cv", job_description="Backend dev")
    h3 = compute_ats_input_hash(cv_text="other", job_description="Backend dev")
    assert h1 == h2
    assert h1 != h3


def test_parse_ats_score_json():
    assert _parse_ats_score('{"ats_score": 91}') == 91
    assert _parse_ats_score('{"ats_score": 142}') == 100
