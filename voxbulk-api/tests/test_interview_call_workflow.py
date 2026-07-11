"""Canonical interview workflow must keep recording disclosure + patient closing."""

from app.services.interview_dialect_packs import interview_call_workflow_for_dialect


def test_english_workflow_has_recording_and_closing():
    flow = interview_call_workflow_for_dialect("GB")
    assert "this call is being recorded for quality purposes" in flow
    assert "be in touch about next steps" in flow
    assert "anything you'd like to add" in flow
    assert "Our team will review your answers and be in touch within {timeframe}" in flow
    assert "Do not hang up until this full closing has been spoken" in flow
    assert "do not rush the candidate" in flow.lower() or "Do not rush the candidate" in flow


def test_arabic_workflow_has_recording_add_anything_and_closing():
    flow = interview_call_workflow_for_dialect("EG")
    assert "مسجّلة لأغراض الجودة" in flow
    assert "حابب تضيف" in flow
    assert "مراجعة إجاباتك والتواصل معك خلال {timeframe}" in flow
    assert "لا تنهِ المكالمة قبل ما تخلص جملة الإغلاق" in flow
