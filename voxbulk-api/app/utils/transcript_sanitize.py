"""Strip Telnyx / TTS markup from voice transcripts for display."""

from __future__ import annotations

import re

_EMOTION_SELF_CLOSE = re.compile(r"<emotion\b[^>]*/>\s*", re.IGNORECASE)
_EMOTION_PAIR = re.compile(r"<emotion\b[^>]*>.*?</emotion>\s*", re.IGNORECASE | re.DOTALL)
_MULTI_SPACE = re.compile(r"[ \t]{2,}")


def sanitize_transcript_markup(text: str) -> str:
    """Remove emotion tags and other inline markup; keep spoken text only."""
    clean = str(text or "")
    if not clean:
        return ""
    clean = _EMOTION_PAIR.sub("", clean)
    clean = _EMOTION_SELF_CLOSE.sub("", clean)
    clean = _MULTI_SPACE.sub(" ", clean)
    return clean.strip()


def sanitize_transcript_document(text: str) -> str:
    """Sanitize a full multi-line transcript (each line cleaned, structure preserved)."""
    lines: list[str] = []
    for raw in str(text or "").splitlines():
        line = sanitize_transcript_markup(raw)
        if line:
            lines.append(line)
    return "\n".join(lines)
