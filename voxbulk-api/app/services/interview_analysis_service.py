"""Post-call transcript analysis and aggregation for AI interview screening."""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from collections import Counter
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.services.agents.base import AgentMessage
from app.services.platform_catalog_service import ServiceOrderService
from app.services.providers.openai_service import OpenAIProviderService
from app.services.survey_analysis_service import (
    MIN_TRANSCRIPT_CHARS,
    ensure_survey_transcript,
    fetch_survey_transcript_from_telnyx,
)

logger = logging.getLogger(__name__)
LOG_PREFIX = "[interview-analysis]"
INTERVIEW_ANALYSIS_VERSION = "3"


def _log(event: str, **detail: Any) -> None:
    logger.info("%s %s", LOG_PREFIX, event, extra=detail)


def _order_config(order: ServiceOrder) -> dict[str, Any]:
    try:
        data = json.loads(order.config_json or "{}")
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _recipient_result(recipient: ServiceOrderRecipient) -> dict[str, Any]:
    try:
        data = json.loads(recipient.result_json or "{}")
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _set_recipient_result(db: Session, recipient: ServiceOrderRecipient, payload: dict[str, Any]) -> None:
    merged = _recipient_result(recipient)
    merged.update(payload)
    recipient.result_json = json.dumps(merged, ensure_ascii=False)
    db.add(recipient)
    db.commit()
    db.refresh(recipient)


_INTERVIEW_ANALYSIS_META = """You analyse a completed AI phone interview screening call transcript.
Return ONLY valid JSON with this exact shape:
{
  "short_summary": "2-3 sentence summary for the hiring manager",
  "score": integer 0-100 overall fit score,
  "culture_fit_score": integer 0-100,
  "recommendation": one of "Advance", "Hold", "Decline",
  "recommendation_summary": "1-2 sentences explaining the recommendation",
  "sentiment": one of "Enthusiastic", "Neutral", "Hesitant",
  "strengths": ["brief strength bullets"],
  "concerns": ["brief concern bullets"],
  "key_answers": [
    {"question": "screening question", "answer": "candidate answer", "quality": one of "strong", "adequate", "weak"}
  ],
  "competencies": [
    {"name": "Communication", "category": "Verbal clarity", "score_10": 1-10, "badge": "Strong|Good|Average|Weak", "note": "brief evidence"}
  ],
  "standout_quote": "best direct quote from candidate or empty string",
  "skill_gap": "main unverified skill gap for final round or empty string",
  "additional_candidate_details": ["brief bullet — useful facts volunteered outside formal Q&A, closing remarks when asked if there is anything else to add, e.g. languages, licences, availability, transport, tools/skills"],
  "completion_quality": one of "complete", "partial", "declined", "unclear"
}

Rules:
- British English.
- Base score and recommendation on role fit and screening criteria in the prompt.
- Do not invent facts not in the transcript.
- Provide 4-6 competency objects covering communication, problem solving, technical knowledge, leadership, culture, judgement.
- additional_candidate_details: include only materially useful facts the candidate volunteered outside the formal script questions, including anything they add when asked if there is anything else they would like to add at the end of the call (skills, certifications, availability, languages, transport, work permits if mentioned). Do not repeat items already captured in key_answers, strengths, or concerns. Return [] if none."""


def _parse_analysis_json(text: str) -> dict[str, Any]:
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


def _normalize_recommendation(value: str | None) -> str:
    clean = str(value or "Hold").strip()
    if clean.lower() in {"advance", "hold", "decline"}:
        return clean.title() if clean.lower() != "advance" else "Advance"
    mapping = {"yes": "Advance", "no": "Decline", "maybe": "Hold", "qualified": "Advance", "reject": "Decline"}
    return mapping.get(clean.lower(), "Hold")


def _normalize_sentiment(value: str | None) -> str:
    clean = str(value or "Neutral").strip()
    if clean in {"Enthusiastic", "Neutral", "Hesitant"}:
        return clean
    low = clean.lower()
    if low in {"positive", "enthusiastic", "excited"}:
        return "Enthusiastic"
    if low in {"negative", "hesitant", "reluctant"}:
        return "Hesitant"
    return "Neutral"


def _dedupe_additional_details(
    items: list[str],
    *,
    strengths: list[str],
    concerns: list[str],
    key_answers: list[dict[str, str]],
) -> list[str]:
    haystack: list[str] = []
    for value in strengths + concerns:
        clean = str(value or "").strip().lower()
        if clean:
            haystack.append(clean)
    for item in key_answers:
        for key in ("question", "answer"):
            clean = str(item.get(key) or "").strip().lower()
            if clean:
                haystack.append(clean)

    deduped: list[str] = []
    seen: set[str] = set()
    for raw in items:
        clean = str(raw or "").strip()
        if not clean:
            continue
        key = clean.lower()
        if key in seen:
            continue
        if any(key in existing or existing in key for existing in haystack if len(existing) >= 8):
            continue
        seen.add(key)
        deduped.append(clean)
    return deduped[:8]


def _normalize_analysis(data: dict[str, Any]) -> dict[str, Any]:
    try:
        score = int(float(data.get("score")))
    except (TypeError, ValueError):
        score = 50
    score = max(0, min(100, score))

    keys_raw = data.get("key_answers")
    key_answers: list[dict[str, str]] = []
    if isinstance(keys_raw, list):
        for item in keys_raw:
            if not isinstance(item, dict):
                continue
            key_answers.append(
                {
                    "question": str(item.get("question") or "").strip(),
                    "answer": str(item.get("answer") or "").strip(),
                    "quality": str(item.get("quality") or "adequate").strip().lower(),
                }
            )

    strengths = data.get("strengths") if isinstance(data.get("strengths"), list) else []
    concerns = data.get("concerns") if isinstance(data.get("concerns"), list) else []
    additional_raw = data.get("additional_candidate_details")
    if additional_raw is None:
        additional_raw = data.get("additional_observations") or data.get("extra_candidate_information")
    additional_items = additional_raw if isinstance(additional_raw, list) else []
    additional_candidate_details = _dedupe_additional_details(
        [str(x).strip() for x in additional_items if str(x).strip()],
        strengths=[str(x).strip() for x in strengths if str(x).strip()],
        concerns=[str(x).strip() for x in concerns if str(x).strip()],
        key_answers=key_answers,
    )

    return {
        "short_summary": str(data.get("short_summary") or "").strip(),
        "score": score,
        "culture_fit_score": max(0, min(100, int(float(data.get("culture_fit_score") or score)))),
        "recommendation": _normalize_recommendation(str(data.get("recommendation") or "")),
        "recommendation_summary": str(data.get("recommendation_summary") or data.get("short_summary") or "").strip(),
        "sentiment": _normalize_sentiment(str(data.get("sentiment") or "")),
        "strengths": [str(x).strip() for x in strengths if str(x).strip()],
        "concerns": [str(x).strip() for x in concerns if str(x).strip()],
        "key_answers": key_answers,
        "competencies": data.get("competencies") if isinstance(data.get("competencies"), list) else [],
        "standout_quote": str(data.get("standout_quote") or data.get("standout_moment") or "").strip(),
        "skill_gap": str(data.get("skill_gap") or "").strip(),
        "additional_candidate_details": additional_candidate_details,
        "completion_quality": str(data.get("completion_quality") or "unclear").strip().lower(),
        "analysis_version": INTERVIEW_ANALYSIS_VERSION,
    }


def extract_interview_analysis(
    db: Session,
    *,
    order: ServiceOrder,
    recipient: ServiceOrderRecipient,
    transcript: str,
    config: dict[str, Any],
) -> dict[str, Any]:
    clean = str(transcript or "").strip()
    role = str(config.get("role") or order.title or "the role").strip()
    criteria = str(config.get("screening_criteria") or config.get("criteria") or "").strip()
    script = str(config.get("approved_script") or "").strip()
    cv_snippet = ""
    intake = _recipient_result(recipient)
    if isinstance(intake.get("cv_text"), str):
        cv_snippet = intake["cv_text"][:2000]

    user_block = "\n\n".join(
        [
            f"Role: {role}",
            f"Screening criteria:\n{criteria or '(not specified)'}",
            f"Approved interview script:\n{script or '(not provided)'}",
            f"Candidate CV excerpt:\n{cv_snippet or '(not provided)'}",
            f"Transcript:\n{clean}",
        ]
    )
    result = OpenAIProviderService.complete(
        db,
        system_prompt=_INTERVIEW_ANALYSIS_META,
        messages=[AgentMessage(role="user", content=user_block)],
        max_tokens=2200,
        temperature=0.2,
        provider="deepseek",
    )
    return _normalize_analysis(_parse_analysis_json(str(result.assistant_text or "")))


def run_interview_analysis_if_needed(
    db: Session,
    *,
    order: ServiceOrder,
    recipient: ServiceOrderRecipient,
    force: bool = False,
) -> dict[str, Any]:
    existing = _recipient_result(recipient)
    if not force and existing.get("analysis_saved_at") and str(existing.get("analysis_version") or "") == INTERVIEW_ANALYSIS_VERSION:
        analysis = existing.get("analysis")
        if isinstance(analysis, dict) and analysis.get("short_summary"):
            return existing

    transcript = str(existing.get("transcript") or "").strip()
    if len(transcript) < MIN_TRANSCRIPT_CHARS:
        return existing

    config = _order_config(order)
    try:
        analysis = extract_interview_analysis(db, order=order, recipient=recipient, transcript=transcript, config=config)
    except Exception as exc:
        logger.exception("%s analysis_failed", LOG_PREFIX)
        _set_recipient_result(
            db,
            recipient,
            {"analysis_error": str(exc)[:500], "analysis_attempted_at": datetime.utcnow().isoformat()},
        )
        return _recipient_result(recipient)

    payload = {
        "analysis": analysis,
        "analysis_saved_at": datetime.utcnow().isoformat(),
        "analysis_version": INTERVIEW_ANALYSIS_VERSION,
        "score": analysis.get("score"),
        "recommendation": analysis.get("recommendation"),
        "sentiment": analysis.get("sentiment"),
        "short_summary": analysis.get("short_summary"),
    }
    _set_recipient_result(db, recipient, payload)
    return _recipient_result(recipient)


def build_order_interview_report(order: ServiceOrder, recipients: list[ServiceOrderRecipient]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    advance = hold = decline = 0
    scores: list[int] = []
    for row in recipients:
        status = str(row.status or "pending").lower()
        counts[status] = counts.get(status, 0) + 1
        result = _recipient_result(row)
        analysis = result.get("analysis") if isinstance(result.get("analysis"), dict) else {}
        rec = str(analysis.get("recommendation") or result.get("recommendation") or "").strip()
        if rec == "Advance":
            advance += 1
        elif rec == "Decline":
            decline += 1
        elif rec:
            hold += 1
        try:
            scores.append(int(analysis.get("score") or result.get("score") or 0))
        except (TypeError, ValueError):
            pass

    config = _order_config(order)
    delivery = str(config.get("delivery") or "ai_call").strip().lower()
    is_meeting = delivery == "ai_meeting"
    return {
        "dispatch_at": datetime.utcnow().isoformat(),
        "provider": "telnyx_voice",
        "channel": "ai_meeting" if is_meeting else "ai_call",
        "total": len(recipients),
        "counts": counts,
        "completed": counts.get("completed", 0),
        "no_answer": counts.get("no_answer", 0),
        "failed": counts.get("failed", 0),
        "advance_count": advance,
        "hold_count": hold,
        "decline_count": decline,
        "average_score": round(sum(scores) / len(scores), 1) if scores else None,
    }


def refresh_order_interview_report(db: Session, order: ServiceOrder) -> None:
    recipients = ServiceOrderService.get_recipients(db, order.id)
    order.report_json = json.dumps(build_order_interview_report(order, recipients), ensure_ascii=False)
    order.updated_at = datetime.utcnow()
    db.add(order)
    db.commit()


class InterviewAnalysisService:
    @staticmethod
    def process_recipient_post_call(
        db: Session,
        *,
        order: ServiceOrder,
        recipient: ServiceOrderRecipient,
        terminal_status: str,
        hangup_extra: dict[str, Any] | None = None,
    ) -> None:
        if order.service_code != "interview":
            return
        db.refresh(recipient)
        hangup_extra = dict(hangup_extra or {})
        if terminal_status == "completed":
            ensure_survey_transcript(db, order=order, recipient=recipient, hangup_extra=hangup_extra)
            db.refresh(recipient)

            from app.services.interview_early_exit_service import (
                interview_ready_for_completion_side_effects,
                maybe_reclassify_completed_interview_after_transcript,
            )

            corrected = maybe_reclassify_completed_interview_after_transcript(
                db, order=order, recipient=recipient
            )
            if corrected is not None:
                refresh_order_interview_report(db, order)
                return

            db.refresh(recipient)
            if not interview_ready_for_completion_side_effects(recipient=recipient):
                _set_recipient_result(
                    db,
                    recipient,
                    {
                        "session_outcome_provisional": True,
                        "session_outcome": "completed",
                    },
                )
                refresh_order_interview_report(db, order)
                return

            run_interview_analysis_if_needed(db, order=order, recipient=recipient)
            try:
                from app.services.interview_session_billing_service import meter_session_if_needed

                meter_session_if_needed(db, order, recipient)
            except Exception:
                logger.exception("%s session_usage_meter_failed", LOG_PREFIX)
            try:
                from app.services.interview_missed_call_email_service import (
                    maybe_send_interview_thank_you_email,
                )

                maybe_send_interview_thank_you_email(db, order=order, recipient=recipient)
            except Exception:
                logger.exception("%s thank_you_email_failed", LOG_PREFIX)
        elif terminal_status in {"no_answer", "failed", "busy", "skipped", "cancelled", "opted_out"}:
            payload: dict[str, Any] = {"terminal_status": terminal_status}
            if hangup_extra.get("call_control_id"):
                payload["call_control_id"] = hangup_extra["call_control_id"]
            _set_recipient_result(db, recipient, payload)
        refresh_order_interview_report(db, order)

    @staticmethod
    def process_pending_analysis(db: Session, *, limit: int = 10) -> int:
        processed = 0
        rows = list(
            db.execute(
                select(ServiceOrderRecipient)
                .join(ServiceOrder, ServiceOrder.id == ServiceOrderRecipient.order_id)
                .where(
                    ServiceOrder.service_code == "interview",
                    ServiceOrderRecipient.status == "completed",
                )
                .order_by(ServiceOrderRecipient.created_at.asc())
                .limit(limit * 3)
            ).scalars()
        )
        for recipient in rows:
            if processed >= limit:
                break
            order = db.get(ServiceOrder, recipient.order_id)
            if order is None or order.service_code != "interview":
                continue
            result = _recipient_result(recipient)
            if result.get("analysis_saved_at") and result.get("session_outcome_reviewed_at"):
                continue
            ensure_survey_transcript(db, order=order, recipient=recipient)
            db.refresh(recipient)

            from app.services.interview_early_exit_service import (
                maybe_reclassify_completed_interview_after_transcript,
            )

            corrected = maybe_reclassify_completed_interview_after_transcript(
                db, order=order, recipient=recipient
            )
            if corrected is not None:
                processed += 1
                continue

            if str(recipient.status or "").lower() != "completed":
                continue
            if len(str(_recipient_result(recipient).get("transcript") or "")) < MIN_TRANSCRIPT_CHARS:
                continue
            InterviewAnalysisService.process_recipient_post_call(
                db,
                order=order,
                recipient=recipient,
                terminal_status="completed",
            )
            processed += 1
        return processed


def schedule_interview_analysis_retry(order_id: str, recipient_id: str, *, delay_seconds: int = 90) -> None:
    def _run() -> None:
        from app.core.database import get_sessionmaker

        time.sleep(max(30, int(delay_seconds)))
        try:
            with get_sessionmaker()() as db:
                order = db.get(ServiceOrder, order_id)
                recipient = db.get(ServiceOrderRecipient, recipient_id)
                if order is None or recipient is None:
                    return
                InterviewAnalysisService.process_recipient_post_call(
                    db,
                    order=order,
                    recipient=recipient,
                    terminal_status=str(recipient.status or "completed"),
                )
        except Exception:
            logger.exception("%s retry_failed", LOG_PREFIX)

    threading.Thread(target=_run, daemon=True, name=f"interview-analysis-{recipient_id[:8]}").start()
