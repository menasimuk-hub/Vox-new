from __future__ import annotations

import json
import logging
import re
import threading
import time
from collections import Counter
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.call_log import CallLog
from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.services.agents.base import AgentMessage
from app.services.platform_catalog_service import PlatformCatalogService, ServiceOrderService
from app.services.providers.openai_service import OpenAIProviderService
from app.services.telnyx_conversation_service import (
    _conversation_list,
    _extract_call_ids_from_conversation,
    fetch_conversation_insights,
    fetch_conversation_messages,
    transcript_entries_from_messages,
    transcript_from_entries,
)

logger = logging.getLogger(__name__)

LOG_PREFIX = "[survey-analysis]"
ANALYSIS_VERSION = "1"
MIN_TRANSCRIPT_CHARS = 20


def is_ai_call_survey_order(order: ServiceOrder) -> bool:
    if order.service_code != "survey":
        return False
    try:
        config = json.loads(order.config_json or "{}")
        return PlatformCatalogService.resolve_survey_channel(config) == "ai_call"
    except Exception:
        return False


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


def _log(event: str, **detail: Any) -> None:
    safe = {k: v for k, v in detail.items() if k not in {"transcript", "transcript_text"}}
    if "transcript_len" not in safe and "transcript" in detail:
        text = str(detail.get("transcript") or "")
        if text:
            safe["transcript_len"] = len(text)
    logger.info("%s %s", LOG_PREFIX, event, extra=safe)


_SURVEY_ANALYSIS_META = """You analyse a completed outbound phone survey call transcript.
Return ONLY valid JSON with this exact shape:
{
  "short_summary": "2-3 sentence plain-English summary of the survey call outcome",
  "sentiment": one of "positive", "neutral", "negative", "mixed",
  "satisfaction_score": number 1-10 or null if not stated or unclear,
  "recommend_score": number 0-10 (NPS-style likelihood to recommend) or null if not stated,
  "answers": [
    {"question": "survey question text", "answer": "respondent answer", "confidence": one of "high", "medium", "low"}
  ],
  "issues": ["concerns or problems raised by the respondent"],
  "tags": ["short topic tags for reporting, e.g. booking, wait_time, staff"],
  "completion_quality": one of "complete", "partial", "declined", "unclear",
  "key_themes": ["main themes from the conversation"]
}

Rules:
- British English.
- Only use facts stated in the transcript — do not invent scores or answers.
- Map script questions to answers where possible.
- If the respondent declined or hung up early, set completion_quality accordingly and leave scores null when unknown."""


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


def _normalize_sentiment(value: str | None) -> str:
    clean = str(value or "neutral").strip().lower()
    if clean in {"positive", "neutral", "negative", "mixed"}:
        return clean
    return "neutral"


def _normalize_completion_quality(value: str | None) -> str:
    clean = str(value or "unclear").strip().lower()
    if clean in {"complete", "partial", "declined", "unclear"}:
        return clean
    return "unclear"


def _optional_score(value: Any, *, min_val: float, max_val: float) -> float | None:
    if value is None or value == "":
        return None
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None
    if score < min_val or score > max_val:
        return None
    return score


def _normalize_analysis(data: dict[str, Any]) -> dict[str, Any]:
    answers_raw = data.get("answers")
    answers: list[dict[str, str]] = []
    if isinstance(answers_raw, list):
        for item in answers_raw:
            if not isinstance(item, dict):
                continue
            question = str(item.get("question") or "").strip()
            answer = str(item.get("answer") or "").strip()
            if not question and not answer:
                continue
            confidence = str(item.get("confidence") or "medium").strip().lower()
            if confidence not in {"high", "medium", "low"}:
                confidence = "medium"
            answers.append({"question": question, "answer": answer, "confidence": confidence})

    issues = data.get("issues")
    if not isinstance(issues, list):
        issues = []
    tags = data.get("tags")
    if not isinstance(tags, list):
        tags = []
    themes = data.get("key_themes")
    if not isinstance(themes, list):
        themes = []

    sentiment = _normalize_sentiment(str(data.get("sentiment") or ""))
    satisfaction = _optional_score(data.get("satisfaction_score"), min_val=1, max_val=10)
    recommend = _optional_score(data.get("recommend_score"), min_val=0, max_val=10)

    return {
        "short_summary": str(data.get("short_summary") or "").strip(),
        "sentiment": sentiment,
        "satisfaction_score": satisfaction,
        "recommend_score": recommend,
        "answers": answers,
        "extracted_answers": answers,
        "issues": [str(x).strip() for x in issues if str(x).strip()],
        "tags": [str(x).strip().lower() for x in tags if str(x).strip()],
        "completion_quality": _normalize_completion_quality(str(data.get("completion_quality") or "")),
        "key_themes": [str(x).strip() for x in themes if str(x).strip()],
        "analysis_version": ANALYSIS_VERSION,
    }


def _find_conversation_for_survey_call(
    db: Session,
    *,
    call_control_id: str,
    started_at: datetime | None,
) -> dict[str, Any] | None:
    cc = str(call_control_id or "").strip()
    if not cc:
        return None
    window_start = (started_at or datetime.utcnow()) - timedelta(minutes=10)
    params = {
        "created_at": f"gte.{window_start.strftime('%Y-%m-%dT%H:%M:%SZ')}",
        "order": "created_at.desc",
        "limit": 40,
    }
    for conv in _conversation_list(db, params=params):
        ids = _extract_call_ids_from_conversation(conv)
        if ids.get("call_control_id") == cc:
            return conv
        metadata = conv.get("metadata") if isinstance(conv.get("metadata"), dict) else {}
        if str(metadata.get("call_control_id") or "").strip() == cc:
            return conv
    return None


def _transcript_from_call_log(db: Session, call_control_id: str) -> tuple[str, dict[str, Any]]:
    cc = str(call_control_id or "").strip()
    if not cc:
        return "", {}
    log = db.execute(select(CallLog).where(CallLog.external_call_id == cc)).scalar_one_or_none()
    if not log:
        return "", {}
    text = str(log.transcript_text or "").strip()
    meta: dict[str, Any] = {"call_log_id": log.id}
    if log.answered_at and log.ended_at:
        meta["duration_seconds"] = max(0, int((log.ended_at - log.answered_at).total_seconds()))
    elif log.started_at and log.ended_at:
        meta["duration_seconds"] = max(0, int((log.ended_at - log.started_at).total_seconds()))
    return text, meta


def _telnyx_call_summary(db: Session, conversation_id: str) -> str:
    insights = fetch_conversation_insights(db, conversation_id)
    parts: list[str] = []
    for item in insights.get("items") or []:
        if not isinstance(item, dict):
            continue
        result_text = str(item.get("result") or "").strip()
        if result_text:
            parts.append(result_text)
    return "\n".join(parts).strip()


def fetch_survey_transcript_from_telnyx(
    db: Session,
    *,
    call_control_id: str,
    started_at: datetime | None,
) -> dict[str, Any]:
    """Fetch transcript and Telnyx metadata for a survey call. Returns partial dict for result_json merge."""
    _log("transcript_fetch_started", call_control_id=call_control_id)
    conversation = _find_conversation_for_survey_call(db, call_control_id=call_control_id, started_at=started_at)
    if not conversation:
        _log("transcript_fetch_failed", call_control_id=call_control_id, reason="conversation_not_found")
        return {"transcript_fetch_error": "conversation_not_found"}

    conversation_id = str(conversation.get("id") or "").strip()
    messages: list[dict[str, Any]] = []
    for attempt in range(3):
        messages, err = fetch_conversation_messages(db, conversation_id)
        if messages:
            break
        if attempt < 2:
            time.sleep(3)
        elif err:
            _log("transcript_fetch_failed", call_control_id=call_control_id, conversation_id=conversation_id, reason=err)
            return {
                "telnyx_conversation_id": conversation_id,
                "transcript_fetch_error": err,
            }

    entries = transcript_entries_from_messages(messages)
    transcript = transcript_from_entries(entries)
    call_summary = _telnyx_call_summary(db, conversation_id)
    ids = _extract_call_ids_from_conversation(conversation)

    payload: dict[str, Any] = {
        "telnyx_conversation_id": conversation_id,
        "transcript_source": "telnyx_conversation",
    }
    if ids.get("call_session_id"):
        payload["call_session_id"] = ids["call_session_id"]
    if transcript:
        payload["transcript"] = transcript
        payload["transcript_saved_at"] = datetime.utcnow().isoformat()
        _log(
            "transcript_saved",
            call_control_id=call_control_id,
            conversation_id=conversation_id,
            transcript_len=len(transcript),
            source="telnyx_conversation",
        )
    else:
        _log("transcript_fetch_failed", call_control_id=call_control_id, conversation_id=conversation_id, reason="empty_transcript")
        payload["transcript_fetch_error"] = "empty_transcript"

    if call_summary:
        payload["call_summary"] = call_summary
    return payload


def ensure_survey_transcript(
    db: Session,
    *,
    order: ServiceOrder,
    recipient: ServiceOrderRecipient,
    hangup_extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Idempotently ensure transcript is stored on recipient.result_json."""
    existing = _recipient_result(recipient)
    transcript = str(existing.get("transcript") or "").strip()
    if transcript and existing.get("transcript_saved_at"):
        return existing

    hangup_extra = hangup_extra or {}
    if not transcript:
        transcript = str(hangup_extra.get("transcript") or "").strip()

    call_control_id = str(
        existing.get("call_control_id") or hangup_extra.get("call_control_id") or ""
    ).strip()
    updates: dict[str, Any] = {}

    if not transcript and call_control_id:
        log_text, log_meta = _transcript_from_call_log(db, call_control_id)
        if log_text:
            transcript = log_text
            updates.update(log_meta)
            updates["transcript_source"] = "call_log"

    if len(transcript) < MIN_TRANSCRIPT_CHARS and call_control_id:
        telnyx_data = fetch_survey_transcript_from_telnyx(
            db,
            call_control_id=call_control_id,
            started_at=order.started_at or order.created_at,
        )
        updates.update({k: v for k, v in telnyx_data.items() if k != "transcript_fetch_error"})
        fetched = str(telnyx_data.get("transcript") or "").strip()
        if len(fetched) >= len(transcript):
            transcript = fetched

    if transcript and not existing.get("transcript_saved_at"):
        updates["transcript"] = transcript
        updates["transcript_saved_at"] = datetime.utcnow().isoformat()
        if "transcript_source" not in updates:
            updates["transcript_source"] = updates.get("transcript_source") or "webhook_or_call_log"
        _log(
            "transcript_saved",
            order_id=order.id,
            recipient_id=recipient.id,
            call_control_id=call_control_id,
            transcript_len=len(transcript),
            source=updates.get("transcript_source"),
        )

    duration = hangup_extra.get("duration_seconds")
    if duration is not None and "duration_seconds" not in existing:
        try:
            updates["duration_seconds"] = int(duration)
        except (TypeError, ValueError):
            pass

    if hangup_extra.get("call_summary") and not existing.get("call_summary"):
        updates["call_summary"] = hangup_extra["call_summary"]

    if updates:
        _set_recipient_result(db, recipient, updates)
        existing = _recipient_result(recipient)
    return existing


def extract_survey_analysis(
    db: Session,
    *,
    order: ServiceOrder,
    recipient: ServiceOrderRecipient,
    transcript: str,
    config: dict[str, Any],
) -> dict[str, Any]:
    clean = str(transcript or "").strip()
    if len(clean) < MIN_TRANSCRIPT_CHARS:
        return {
            "short_summary": "Transcript not available for analysis yet.",
            "sentiment": "neutral",
            "satisfaction_score": None,
            "recommend_score": None,
            "answers": [],
            "extracted_answers": [],
            "issues": [],
            "tags": [],
            "completion_quality": "unclear",
            "key_themes": [],
            "analysis_version": ANALYSIS_VERSION,
            "analysis_error": "transcript_too_short",
        }

    goal = str(config.get("goal") or "").strip()
    script = str(config.get("approved_script") or "").strip()
    org_name = str(config.get("organisation_name") or config.get("clinic_name") or "").strip()

    user_block = "\n".join(
        [
            f"Organisation: {org_name or 'unknown'}",
            f"Respondent: {recipient.name or 'unknown'}",
            f"Survey goal: {goal or 'not specified'}",
            f"Approved script / questions:\n{script or '(not provided)'}",
            f"Transcript:\n{clean}",
        ]
    )
    _log("deepseek_analysis_started", order_id=order.id, recipient_id=recipient.id, transcript_len=len(clean))
    result = OpenAIProviderService.complete(
        db,
        system_prompt=_SURVEY_ANALYSIS_META,
        messages=[AgentMessage(role="user", content=user_block)],
        max_tokens=1200,
        temperature=0.2,
        provider="deepseek",
    )
    normalized = _normalize_analysis(_parse_analysis_json(str(result.assistant_text or "")))
    _log(
        "deepseek_analysis_saved",
        order_id=order.id,
        recipient_id=recipient.id,
        sentiment=normalized.get("sentiment"),
        completion_quality=normalized.get("completion_quality"),
    )
    return normalized


def run_survey_analysis_if_needed(
    db: Session,
    *,
    order: ServiceOrder,
    recipient: ServiceOrderRecipient,
) -> dict[str, Any]:
    """Run DeepSeek analysis idempotently when transcript is ready."""
    existing = _recipient_result(recipient)
    if existing.get("analysis_saved_at") and str(existing.get("analysis_version") or "") == ANALYSIS_VERSION:
        analysis = existing.get("analysis")
        if isinstance(analysis, dict) and analysis.get("short_summary"):
            return existing

    transcript = str(existing.get("transcript") or "").strip()
    if len(transcript) < MIN_TRANSCRIPT_CHARS:
        return existing

    config = _order_config(order)
    try:
        analysis = extract_survey_analysis(db, order=order, recipient=recipient, transcript=transcript, config=config)
    except Exception as exc:
        _log(
            "deepseek_analysis_failed",
            order_id=order.id,
            recipient_id=recipient.id,
            error=str(exc)[:500],
        )
        logger.exception("%s deepseek_analysis_failed", LOG_PREFIX)
        _set_recipient_result(
            db,
            recipient,
            {
                "analysis_error": str(exc)[:500],
                "analysis_attempted_at": datetime.utcnow().isoformat(),
            },
        )
        return _recipient_result(recipient)

    payload = {
        "analysis": analysis,
        "analysis_saved_at": datetime.utcnow().isoformat(),
        "analysis_version": ANALYSIS_VERSION,
        "short_summary": analysis.get("short_summary"),
        "sentiment": analysis.get("sentiment"),
        "satisfaction_score": analysis.get("satisfaction_score"),
        "recommend_score": analysis.get("recommend_score"),
        "extracted_answers": analysis.get("extracted_answers") or analysis.get("answers") or [],
        "issues": analysis.get("issues") or [],
        "tags": analysis.get("tags") or [],
    }
    _set_recipient_result(db, recipient, payload)
    return _recipient_result(recipient)


def build_order_analysis_report(recipients: list[ServiceOrderRecipient]) -> dict[str, Any]:
    """Aggregate per-recipient analysis into order-level summary."""
    analyzed = 0
    pending_analysis = 0
    satisfaction_scores: list[float] = []
    recommend_scores: list[float] = []
    sentiment_counts: Counter[str] = Counter()
    issue_counts: Counter[str] = Counter()
    tag_counts: Counter[str] = Counter()
    nps_promoters = nps_passives = nps_detractors = 0

    for row in recipients:
        status = str(row.status or "").lower()
        result = _recipient_result(row)
        analysis = result.get("analysis") if isinstance(result.get("analysis"), dict) else {}

        if status == "completed":
            if result.get("analysis_saved_at"):
                analyzed += 1
            elif str(result.get("transcript") or "").strip():
                pending_analysis += 1
            else:
                pending_analysis += 1

        sentiment = str(analysis.get("sentiment") or result.get("sentiment") or "").strip().lower()
        if sentiment in {"positive", "neutral", "negative", "mixed"}:
            sentiment_counts[sentiment] += 1

        sat = analysis.get("satisfaction_score", result.get("satisfaction_score"))
        if sat is not None:
            try:
                satisfaction_scores.append(float(sat))
            except (TypeError, ValueError):
                pass

        rec = analysis.get("recommend_score", result.get("recommend_score"))
        if rec is not None:
            try:
                score = float(rec)
                recommend_scores.append(score)
                if score >= 9:
                    nps_promoters += 1
                elif score >= 7:
                    nps_passives += 1
                else:
                    nps_detractors += 1
            except (TypeError, ValueError):
                pass

        for issue in analysis.get("issues") or result.get("issues") or []:
            text = str(issue).strip().lower()
            if text:
                issue_counts[text] += 1
        for tag in analysis.get("tags") or result.get("tags") or []:
            text = str(tag).strip().lower()
            if text:
                tag_counts[text] += 1

    def _top(counter: Counter[str], limit: int = 5) -> list[dict[str, Any]]:
        return [{"label": label, "count": count} for label, count in counter.most_common(limit)]

    avg_sat = round(sum(satisfaction_scores) / len(satisfaction_scores), 2) if satisfaction_scores else None
    avg_rec = round(sum(recommend_scores) / len(recommend_scores), 2) if recommend_scores else None
    nps_total = nps_promoters + nps_passives + nps_detractors
    nps_score = round(((nps_promoters - nps_detractors) / nps_total) * 100, 1) if nps_total else None

    return {
        "analyzed_count": analyzed,
        "pending_analysis": pending_analysis,
        "average_satisfaction": avg_sat,
        "average_recommend_score": avg_rec,
        "nps": {
            "score": nps_score,
            "promoters": nps_promoters,
            "passives": nps_passives,
            "detractors": nps_detractors,
            "responses": nps_total,
        },
        "sentiment_counts": dict(sentiment_counts),
        "top_issues": _top(issue_counts),
        "top_tags": _top(tag_counts),
    }


def build_order_survey_report(order: ServiceOrder, recipients: list[ServiceOrderRecipient]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for row in recipients:
        status = str(row.status or "pending").lower()
        counts[status] = counts.get(status, 0) + 1
    return {
        "dispatch_at": datetime.utcnow().isoformat(),
        "provider": "telnyx_voice",
        "channel": "ai_call",
        "total": len(recipients),
        "counts": counts,
        "completed": counts.get("completed", 0),
        "no_answer": counts.get("no_answer", 0),
        "failed": counts.get("failed", 0),
        "busy": counts.get("busy", 0),
        "pending": counts.get("pending", 0),
        "calling": counts.get("calling", 0),
        "cancelled": counts.get("cancelled", 0),
        "analysis": build_order_analysis_report(recipients),
    }


def refresh_order_survey_report(db: Session, order: ServiceOrder) -> None:
    recipients = ServiceOrderService.get_recipients(db, order.id)
    order.report_json = json.dumps(build_order_survey_report(order, recipients), ensure_ascii=False)
    order.updated_at = datetime.utcnow()
    db.add(order)
    db.commit()
    _log("aggregate_updated", order_id=order.id, total=len(recipients))


class SurveyAnalysisService:
    @staticmethod
    def process_recipient_post_call(
        db: Session,
        *,
        order: ServiceOrder,
        recipient: ServiceOrderRecipient,
        terminal_status: str,
        hangup_extra: dict[str, Any] | None = None,
    ) -> None:
        """Finalize transcript + analysis for one survey call recipient."""
        if not is_ai_call_survey_order(order):
            return

        db.refresh(recipient)
        hangup_extra = dict(hangup_extra or {})
        hangup_extra.setdefault("terminal_status", terminal_status)

        if terminal_status == "completed":
            ensure_survey_transcript(db, order=order, recipient=recipient, hangup_extra=hangup_extra)
            db.refresh(recipient)
            run_survey_analysis_if_needed(db, order=order, recipient=recipient)
        elif terminal_status in {"no_answer", "failed", "busy", "skipped", "cancelled"}:
            # Store terminal metadata without DeepSeek for non-completed calls.
            payload: dict[str, Any] = {"terminal_status": terminal_status}
            if hangup_extra.get("call_control_id"):
                payload["call_control_id"] = hangup_extra["call_control_id"]
            if hangup_extra.get("hangup_cause"):
                payload["hangup_cause"] = hangup_extra["hangup_cause"]
            _set_recipient_result(db, recipient, payload)

        refresh_order_survey_report(db, order)

    @staticmethod
    def process_pending_analysis(db: Session, *, limit: int = 10) -> int:
        """Retry transcript fetch + analysis for completed recipients missing analysis."""
        processed = 0
        rows = list(
            db.execute(
                select(ServiceOrderRecipient)
                .join(ServiceOrder, ServiceOrder.id == ServiceOrderRecipient.order_id)
                .where(
                    ServiceOrder.service_code == "survey",
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
            if order is None or not is_ai_call_survey_order(order):
                continue
            result = _recipient_result(recipient)
            if result.get("analysis_saved_at") and str(result.get("analysis_version") or "") == ANALYSIS_VERSION:
                continue
            ensure_survey_transcript(db, order=order, recipient=recipient)
            db.refresh(recipient)
            updated = _recipient_result(recipient)
            if len(str(updated.get("transcript") or "")) < MIN_TRANSCRIPT_CHARS:
                continue
            run_survey_analysis_if_needed(db, order=order, recipient=recipient)
            refresh_order_survey_report(db, order)
            processed += 1
        return processed


def schedule_survey_analysis_retry(order_id: str, recipient_id: str, *, delay_seconds: int = 90) -> None:
    """Background retry when Telnyx transcript is not ready at hangup."""

    def _run() -> None:
        from app.core.database import get_sessionmaker

        time.sleep(max(30, int(delay_seconds)))
        try:
            with get_sessionmaker()() as db:
                order = db.get(ServiceOrder, order_id)
                recipient = db.get(ServiceOrderRecipient, recipient_id)
                if order is None or recipient is None:
                    return
                SurveyAnalysisService.process_recipient_post_call(
                    db,
                    order=order,
                    recipient=recipient,
                    terminal_status=str(recipient.status or "completed"),
                )
        except Exception:
            logger.exception("%s retry_failed", LOG_PREFIX, extra={"order_id": order_id, "recipient_id": recipient_id})

    threading.Thread(
        target=_run,
        daemon=True,
        name=f"survey-analysis-{recipient_id[:8]}",
    ).start()
