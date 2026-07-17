"""Canonical interview workflow: recording consent then time, with Tier A same-person rules."""

from app.services.interview_dialect_packs import interview_call_workflow_for_dialect


def test_english_workflow_has_recording_and_closing():
    flow = interview_call_workflow_for_dialect("GB")
    assert "this call is being recorded for quality purposes" in flow
    assert "be in touch about next steps" in flow
    assert "anything you'd like to add" in flow
    assert "Our team will review your answers and be in touch within {timeframe}" in flow
    assert "Do not hang up until this full closing has been spoken" in flow
    assert "do not rush the candidate" in flow.lower() or "Do not rush the candidate" in flow
    assert "decline recording" in flow.lower() or "do not consent" in flow.lower()
    assert "not free" in flow.lower() or "asks to reschedule" in flow.lower()
    # Recording consent before time ask; one gate per turn.
    rec_idx = flow.lower().index("being recorded for quality purposes")
    time_idx = flow.lower().index("is now a good time")
    assert rec_idx < time_idx
    assert "ONE gate question per turn" in flow or "one gate question" in flow.lower()
    assert "combining recording consent and the time ask" in flow.lower()
    # Tier A same-person / no substitute.
    assert "same person only" in flow.lower()
    assert "do not interview a substitute" in flow.lower()


def test_arabic_workflow_has_recording_add_anything_and_closing():
    flow = interview_call_workflow_for_dialect("EG")
    assert "مسجّلة لأغراض الجودة" in flow
    assert "حابب تضيف" in flow
    assert "مراجعة إجاباتك والتواصل معك خلال {timeframe}" in flow
    assert "لا تنهِ المكالمة قبل ما تخلص جملة الإغلاق" in flow
    rec_idx = flow.index("مسجّلة لأغراض الجودة")
    time_idx = flow.index("هل الوقت مناسب الآن")
    assert rec_idx < time_idx
    assert "نفس الشخص" in flow
    assert "بديل" in flow
