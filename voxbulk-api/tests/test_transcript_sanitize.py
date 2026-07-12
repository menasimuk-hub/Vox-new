from app.utils.transcript_sanitize import sanitize_transcript_document, sanitize_transcript_markup


def test_sanitize_emotion_self_closing():
    raw = '<emotion value="grateful" />Thanks for calling back about the MOT delay.'
    assert sanitize_transcript_markup(raw) == "Thanks for calling back about the MOT delay."


def test_sanitize_emotion_in_transcript_line():
    doc = (
        "Agent: How can I help?\n"
        'Customer: <emotion value="frustrated" />The wait was far too long.'
    )
    clean = sanitize_transcript_document(doc)
    assert "<emotion" not in clean
    assert "The wait was far too long." in clean


def test_sanitize_preserves_speaker_lines():
    doc = 'Customer: <emotion value="grateful" />All sorted now, thank you.'
    clean = sanitize_transcript_document(doc)
    assert clean == "Customer: All sorted now, thank you."
