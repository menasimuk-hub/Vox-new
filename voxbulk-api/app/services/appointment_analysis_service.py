"""Post-call DeepSeek analysis for appointment confirmation calls."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.appointment import Appointment
from app.services.agents.base import AgentMessage
from app.services.appointment_log_service import append_log

_ANALYSIS_PROMPT = """Extract appointment call outcome as JSON only:
{
  "outcome": "confirmed|rescheduled|no_answer|voicemail|cancelled",
  "rescheduled_to": null or ISO datetime string,
  "summary": "one sentence",
  "confidence": "high|medium|low"
}
Use outcome=no_answer or voicemail only when the transcript clearly indicates that."""


def _parse_json(text: str) -> dict[str, Any]:
    clean = str(text or "").strip()
    if clean.startswith("```"):
        clean = re.sub(r"^```(?:json)?\s*", "", clean)
        clean = re.sub(r"\s*```$", "", clean)
    try:
        data = json.loads(clean)
    except json.JSONDecodeError:
        start = clean.find("{")
        end = clean.rfind("}")
        data = json.loads(clean[start : end + 1]) if start >= 0 and end > start else {}
    return data if isinstance(data, dict) else {}


def _mock_analysis(transcript: str) -> dict[str, Any]:
    lower = transcript.lower()
    if "reschedule" in lower or "change" in lower:
        return {"outcome": "rescheduled", "rescheduled_to": None, "summary": "Caller requested reschedule.", "confidence": "medium"}
    if "cancel" in lower:
        return {"outcome": "cancelled", "rescheduled_to": None, "summary": "Caller cancelled.", "confidence": "medium"}
    if "voicemail" in lower or len(transcript.strip()) < 8:
        return {"outcome": "voicemail", "rescheduled_to": None, "summary": "Voicemail or no conversation.", "confidence": "low"}
    return {"outcome": "confirmed", "rescheduled_to": None, "summary": "Appointment confirmed.", "confidence": "medium"}


def _normalize(data: dict[str, Any]) -> dict[str, Any]:
    outcome = str(data.get("outcome") or "confirmed").strip().lower()
    if outcome not in {"confirmed", "rescheduled", "no_answer", "voicemail", "cancelled"}:
        outcome = "confirmed"
    rescheduled_to = data.get("rescheduled_to")
    parsed_dt = None
    if rescheduled_to:
        try:
            parsed_dt = datetime.fromisoformat(str(rescheduled_to).replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            parsed_dt = None
    return {
        "outcome": outcome,
        "rescheduled_to": parsed_dt,
        "summary": str(data.get("summary") or "").strip() or None,
        "confidence": str(data.get("confidence") or "medium").strip().lower(),
    }


def process_post_call(db: Session, *, appointment: Appointment, transcript: str) -> dict[str, Any]:
    clean = str(transcript or "").strip()
    use_mock = os.getenv("APPOINTMENT_ANALYSIS_MOCK", "").strip().lower() in {"1", "true", "yes"}

    if use_mock or len(clean) < 12:
        normalized = _normalize(_mock_analysis(clean))
    else:
        try:
            from app.services.providers.openai_service import OpenAIProviderService

            result = OpenAIProviderService.complete(
                db,
                system_prompt=_ANALYSIS_PROMPT,
                messages=[AgentMessage(role="user", content=f"Transcript:\n{clean}")],
                max_tokens=400,
                temperature=0.1,
                provider="deepseek",
            )
            normalized = _normalize(_parse_json(str(result.assistant_text or "")))
        except Exception:
            normalized = _normalize(_mock_analysis(clean))

    append_log(
        db,
        appointment_id=appointment.id,
        event_type="call_analyzed",
        detail=normalized,
    )
    return normalized
