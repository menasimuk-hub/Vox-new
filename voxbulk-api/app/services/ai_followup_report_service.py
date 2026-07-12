"""Build human-readable AI follow-up reason reports for dashboard results."""

from __future__ import annotations

import re
from typing import Any

from app.services.customer_feedback.feedback_ai_followup_service import LOW_ANSWERS

_CUSTOMER_LINE_RE = re.compile(r"^(user|customer|caller)\s*:\s*(.+)$", re.I)
_ASSISTANT_LINE_RE = re.compile(r"^(assistant|agent|ai)\s*:\s*", re.I)


def _is_rating_only_answer(value: str) -> bool:
    from app.services.survey_results_service import _is_negative_answer_value

    val = str(value or "").strip()
    if not val or val.lower() == "skip":
        return True
    low = val.lower()
    if _is_negative_answer_value(val) or low in LOW_ANSWERS or low == "no":
        return True
    if low in {"yes", "maybe", "good", "excellent", "average", "avg"}:
        return True
    if "excellent" in low or "good" in low or "spotless" in low or "smooth" in low:
        return True
    return False


def extract_wa_written_feedback(answers: list[dict[str, Any]], *, final_additional: str | None = None) -> list[dict[str, str]]:
    """Free-text or voice feedback from WA survey (not low rating labels)."""
    snippets: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in answers:
        if not isinstance(item, dict):
            continue
        role = str(item.get("step_role") or item.get("reply_type") or "").strip().lower()
        text = str(
            item.get("answer_text")
            or item.get("translated_text")
            or item.get("original_text")
            or item.get("answer")
            or ""
        ).strip()
        if not text or text.lower() == "skip" or _is_rating_only_answer(text):
            continue
        source = str(item.get("answer_source") or "").strip().lower() or "text"
        label = str(item.get("question") or item.get("topic") or item.get("template_name") or "Feedback").strip()
        is_reason_step = any(
            token in role for token in ("tell_us_more", "followup", "reason", "final_feedback", "improvement", "open_text")
        )
        if is_reason_step or source in {"voice", "voice_note"} or len(text) >= 12:
            key = f"{label}|{text[:120]}"
            if key in seen:
                continue
            seen.add(key)
            snippets.append({"question": label, "text": text, "source": source})
    final = str(final_additional or "").strip()
    if final and len(final) >= 8 and not _is_rating_only_answer(final):
        key = f"final|{final[:120]}"
        if key not in seen:
            snippets.append({"question": "Additional feedback", "text": final, "source": "text"})
    return snippets


def extract_customer_lines_from_transcript(transcript: str | None) -> str | None:
    raw = str(transcript or "").strip()
    if not raw:
        return None
    customer_parts: list[str] = []
    other_parts: list[str] = []
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        m = _CUSTOMER_LINE_RE.match(stripped)
        if m:
            customer_parts.append(m.group(2).strip())
            continue
        if _ASSISTANT_LINE_RE.match(stripped):
            continue
        other_parts.append(stripped)
    if customer_parts:
        return " ".join(customer_parts)[:800]
    if other_parts:
        return " ".join(other_parts)[:800]
    return raw[:800]


def describe_call_findings(
    *,
    transcript: str | None,
    transcript_excerpt: str | None,
    duration_seconds: int | None,
    status: str | None,
) -> str | None:
    excerpt = extract_customer_lines_from_transcript(transcript) or str(transcript_excerpt or "").strip() or None
    if excerpt and len(excerpt) >= 12:
        return excerpt
    st = str(status or "").strip().lower()
    dur = duration_seconds if isinstance(duration_seconds, int) else None
    if st == "completed":
        if dur is not None and dur < 10:
            return (
                "Customer answered the AI follow-up call but ended it almost immediately — "
                "they did not explain why they were unhappy on the call."
            )
        return "AI follow-up call completed but no transcript was recorded — reason not captured on the call."
    if st in {"no_answer", "busy", "voicemail"}:
        return f"AI follow-up call was not answered ({st.replace('_', ' ')}) — reason not captured on the call."
    if st == "opted_out":
        return "Customer opted out during the AI follow-up call."
    return None


def build_followup_reason_report(
    *,
    session_summary: dict[str, Any] | None,
    outcome: dict[str, Any] | None,
    status: str | None,
    business_context: str | None = None,
) -> dict[str, Any]:
    summary = session_summary if isinstance(session_summary, dict) else {}
    oc = outcome if isinstance(outcome, dict) else {}
    poor_answers = summary.get("poor_answers") if isinstance(summary.get("poor_answers"), list) else []
    written = summary.get("written_feedback") if isinstance(summary.get("written_feedback"), list) else []

    call_findings = str(oc.get("call_findings") or "").strip() or None
    if not call_findings:
        call_findings = describe_call_findings(
            transcript=oc.get("transcript") if isinstance(oc.get("transcript"), str) else None,
            transcript_excerpt=oc.get("transcript_excerpt") if isinstance(oc.get("transcript_excerpt"), str) else None,
            duration_seconds=oc.get("duration_seconds") if isinstance(oc.get("duration_seconds"), int) else None,
            status=status,
        )

    narrative_parts: list[str] = []
    if poor_answers:
        rating_bits = [f"{a.get('question', 'Topic')}: {a.get('answer', '—')}" for a in poor_answers[:6] if isinstance(a, dict)]
        if rating_bits:
            narrative_parts.append(
                "Low survey ratings (not the reason itself): " + "; ".join(rating_bits) + "."
            )
    if written:
        reason_bits = [f"{w.get('question', 'Feedback')}: {w.get('text', '')}" for w in written[:4] if isinstance(w, dict)]
        if reason_bits:
            narrative_parts.append("Reason given in the survey: " + "; ".join(reason_bits) + ".")
    else:
        narrative_parts.append(
            "The customer did not explain why in the WhatsApp survey — that is why the AI follow-up call was placed."
        )

    if call_findings:
        narrative_parts.append(f"What we learned from the AI call: {call_findings}")
    elif str(status or "").strip().lower() in {"completed", "dispatched", "scheduled"}:
        narrative_parts.append(
            "No reason has been captured from the AI call yet."
            if str(status or "").lower() != "completed"
            else describe_call_findings(
                transcript=None,
                transcript_excerpt=None,
                duration_seconds=oc.get("duration_seconds") if isinstance(oc.get("duration_seconds"), int) else None,
                status=status,
            )
            or "No reason captured from the AI call."
        )

    ctx = str(business_context or "").strip()
    if ctx:
        narrative_parts.append(f"Business context for the call: {ctx[:300]}")

    survey_written = None
    if written and isinstance(written[0], dict):
        survey_written = str(written[0].get("text") or "").strip() or None

    return {
        "survey_low_ratings": poor_answers,
        "survey_written_reason": survey_written,
        "survey_written_reasons": written,
        "call_findings": call_findings,
        "narrative": " ".join(n for n in narrative_parts if n),
    }
