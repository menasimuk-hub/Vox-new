from app.services.service_script_generator import _interview_meta, _order_cv_questions_first
from app.utils.script_language import detect_script_language, normalize_script_language_code


def test_detect_script_language_arabic_criteria():
    text = "ممرضة مسجلة\nخبرة في العناية بالأسنان ومهارات التواصل"
    assert detect_script_language(text) == "ar"


def test_detect_script_language_english_criteria():
    text = "Registered dental nurse\nStrong communication and chairside skills"
    assert detect_script_language(text) == "en"


def test_detect_script_language_mixed_mostly_arabic():
    text = "Nurse\nممرضة مسجلة مع خبرة في العناية بالأسنان والتواصل مع المرضى"
    assert detect_script_language(text) == "ar"


def test_detect_script_language_override():
    assert detect_script_language("hello", override="ar") == "ar"
    assert normalize_script_language_code("AR") == "ar"
    assert normalize_script_language_code("unknown") == "en"


def test_interview_meta_arabic_not_british_english():
    meta = _interview_meta(language_code="ar")
    assert "Arabic" in meta
    assert "British English" not in meta


def test_order_cv_questions_first_arabic_markers():
    questions = [
        "هل لديك تسجيل GDC؟",
        "هل أنت مستعد للسفر؟",
        "حدثني عن خبرتك في السيرة الذاتية في دور سابق.",
        "ما الإنجاز الذي تفخر به من سيرتك الذاتية؟",
    ]
    ordered = _order_cv_questions_first(questions)
    assert ordered[0].startswith("حدثني")
    assert ordered[1].startswith("ما الإنجاز")
