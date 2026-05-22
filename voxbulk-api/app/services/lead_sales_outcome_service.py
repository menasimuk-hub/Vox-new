from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.lead_sales_task import LeadSalesTask
from app.services.agents.base import AgentMessage
from app.services.providers.openai_service import OpenAIProviderService
from app.services.telnyx_conversation_service import (
    _conversation_list,
    _extract_call_ids_from_conversation,
    _looks_like_conversation_id,
    fetch_conversation_insights,
    fetch_conversation_messages,
    transcript_entries_from_messages,
    transcript_from_entries,
)

logger = logging.getLogger(__name__)

_OUTCOME_META = """You analyse a completed outbound sales call transcript.
Return ONLY valid JSON:
- "demo_agreed": boolean — true if they agreed to a demo or meeting
- "demo_scheduled_at": string or null — ISO datetime if a demo time was agreed
- "interested_to_buy": boolean — true if they want to purchase or move forward commercially
- "deal_stage": one of "won_intent", "demo_booked", "qualified", "follow_up", "not_interested", "no_answer"
- "outcome_summary": 2-4 sentences on what happened
- "next_step": short string — what sales should do next
- "objections": array of strings
- "sentiment": one of "enthusiastic", "neutral", "hesitant", "negative"
- "recommended_offer": one of "subscription", "survey", "interview" — which signup offer fits best based on what they discussed (dental plan trial vs free survey contacts vs free interviews)

British English. Only facts from the transcript."""


def _parse_outcome_json(text: str) -> dict[str, Any]:
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


def extract_sales_outcome(db: Session, *, transcript: str, task: LeadSalesTask) -> dict[str, Any]:
    clean = str(transcript or "").strip()
    if not clean:
        return {
            "demo_agreed": False,
            "interested_to_buy": False,
            "deal_stage": "no_answer",
            "outcome_summary": "No transcript available for this sales call yet.",
            "next_step": "Sync outcome from Telnyx or review the call in the portal.",
            "objections": [],
            "sentiment": "neutral",
            "recommended_offer": "subscription",
        }
    user_block = "\n".join(
        [
            f"Contact: {task.contact_name or 'unknown'}",
            f"Company: {task.company_name or 'unknown'}",
            f"Original interest: {task.interest_summary or task.sales_intent or 'unknown'}",
            f"Transcript:\n{clean}",
        ]
    )
    result = OpenAIProviderService.complete(
        db,
        system_prompt=_OUTCOME_META,
        messages=[AgentMessage(role="user", content=user_block)],
        max_tokens=900,
        temperature=0.2,
        provider="deepseek",
    )
    data = _parse_outcome_json(str(result.assistant_text or ""))
    stage = str(data.get("deal_stage") or "follow_up").strip().lower()
    allowed = {"won_intent", "demo_booked", "qualified", "follow_up", "not_interested", "no_answer"}
    if stage not in allowed:
        stage = "follow_up"
    sentiment = str(data.get("sentiment") or "neutral").strip().lower()
    if sentiment not in {"enthusiastic", "neutral", "hesitant", "negative"}:
        sentiment = "neutral"
    objections = data.get("objections")
    if not isinstance(objections, list):
        objections = []
    recommended = str(data.get("recommended_offer") or "subscription").strip().lower()
    if recommended not in {"subscription", "survey", "interview"}:
        recommended = "subscription"
    return {
        "demo_agreed": bool(data.get("demo_agreed")),
        "demo_scheduled_at": str(data.get("demo_scheduled_at") or "").strip() or None,
        "interested_to_buy": bool(data.get("interested_to_buy")),
        "deal_stage": stage,
        "outcome_summary": str(data.get("outcome_summary") or "").strip(),
        "next_step": str(data.get("next_step") or "").strip(),
        "objections": [str(x).strip() for x in objections if str(x).strip()],
        "sentiment": sentiment,
        "recommended_offer": recommended,
    }


def resolve_sales_task_conversation_id(db: Session, task: LeadSalesTask) -> str:
    for candidate in (task.telnyx_conversation_id, task.provider_call_id):
        conv_id = str(candidate or "").strip()
        if _looks_like_conversation_id(conv_id):
            return conv_id
    conversation = _find_conversation_for_sales_call(db, task)
    if conversation:
        return str(conversation.get("id") or "").strip()
    return ""


def get_sales_task_telnyx_insights(db: Session, task: LeadSalesTask) -> dict[str, Any]:
    conv_id = resolve_sales_task_conversation_id(db, task)
    if not conv_id:
        return {
            "task_id": task.id,
            "conversation_id": "",
            "error": None,
            "status": "none",
            "items": [],
            "message": (
                "Could not find a Telnyx conversation for this sales call. "
                "Use Refresh from Telnyx on the task page after the call completes."
            ),
        }
    if conv_id != str(task.telnyx_conversation_id or "").strip():
        task.telnyx_conversation_id = conv_id
        task.updated_at = datetime.utcnow()
        db.add(task)
        db.commit()
    payload = fetch_conversation_insights(db, conv_id)
    payload["task_id"] = task.id
    return payload


def _find_conversation_for_sales_call(db: Session, task: LeadSalesTask) -> dict[str, Any] | None:
    cc = str(task.provider_call_id or "").strip()
    if not cc:
        return None
    window_start = (task.call_started_at or task.scheduled_at or task.created_at) - timedelta(minutes=5)
    params = {
        "created_at": f"gte.{window_start.strftime('%Y-%m-%dT%H:%M:%SZ')}",
        "order": "created_at.desc",
        "limit": 40,
    }
    for conv in _conversation_list(db, params=params):
        ids = _extract_call_ids_from_conversation(conv)
        if ids.get("call_control_id") == cc or str(conv.get("metadata", {}).get("call_control_id") or "") == cc:
            return conv
    return None


def sync_sales_task_outcome(db: Session, task: LeadSalesTask) -> LeadSalesTask:
    conversation = _find_conversation_for_sales_call(db, task)
    transcript = str(task.sales_transcript_text or "").strip()
    if conversation:
        conv_id = str(conversation.get("id") or "").strip()
        task.telnyx_conversation_id = conv_id or task.telnyx_conversation_id
        messages: list[dict[str, Any]] = []
        for attempt in range(3):
            messages, _err = fetch_conversation_messages(db, conv_id)
            if messages:
                break
            if attempt < 2:
                time.sleep(5)
        if not messages:
            logger.warning(
                "sales_transcript_messages_empty_after_retries",
                extra={"task_id": task.id, "conversation_id": conv_id},
            )
        entries = transcript_entries_from_messages(messages)
        built = transcript_from_entries(entries)
        if built:
            transcript = built
            task.sales_transcript_text = built

    outcome = extract_sales_outcome(db, transcript=transcript, task=task)
    task.outcome_json = json.dumps(outcome, ensure_ascii=False)
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def schedule_post_call_automation_retry(task_id: str, *, delay_seconds: int = 180) -> None:
    """Retry sync + auto-offer when Telnyx transcript was not ready at hangup."""
    from app.workers.sales_tasks import retry_post_call_automation_task

    countdown = max(30, int(delay_seconds))

    def _run_retry() -> None:
        try:
            retry_post_call_automation_task(task_id)
        except Exception:
            logger.exception("post_call_automation_retry_failed", extra={"task_id": task_id})

    try:
        retry_post_call_automation_task.apply_async(args=[task_id], countdown=countdown)
        return
    except Exception as exc:
        logger.warning(
            "schedule_post_call_automation_retry_celery_failed",
            extra={"task_id": task_id, "error": str(exc)},
        )

    import threading
    import time

    def _delayed() -> None:
        time.sleep(countdown)
        _run_retry()

    threading.Thread(target=_delayed, daemon=True, name=f"sales-retry-{task_id[:8]}").start()


def finalize_sales_task_after_call(db: Session, task: LeadSalesTask, *, status: str = "completed") -> None:
    task.status = status if status in {"completed", "no_answer", "failed"} else "completed"
    task.call_completed_at = datetime.utcnow()
    task.updated_at = datetime.utcnow()
    db.add(task)
    db.commit()

    try:
        task = sync_sales_task_outcome(db, task)
    except Exception as exc:
        logger.exception("sales_outcome_sync_failed", extra={"task_id": task.id})
        task.last_error = f"Outcome sync failed: {exc}"[:2000]
        task.updated_at = datetime.utcnow()
        db.add(task)
        db.commit()
        db.refresh(task)

    automation_result: dict[str, Any] = {"skipped": True}
    transcript = str(task.sales_transcript_text or "").strip()
    if status == "completed" and not transcript:
        logger.info(
            "sales_post_call_no_transcript_yet",
            extra={"task_id": task.id, "status": status},
        )

    try:
        from app.services.sales_automation_service import SalesAutomationService

        automation_result = SalesAutomationService.run_post_call_automation(db, task, call_status=status)
    except Exception as exc:
        logger.exception("sales_post_call_automation_failed", extra={"task_id": task.id})
        task.last_error = f"Post-call automation failed: {exc}"[:2000]
        task.updated_at = datetime.utcnow()
        db.add(task)
        db.commit()

    db.refresh(task)
    if status == "completed" and not task.offer_sent_at:
        reason = str(automation_result.get("reason") or "").strip()
        skip_retry = reason in {
            "no_action_for_outcome",
            "offer_already_sent",
            "automation_disabled",
            "automation_paused",
            "no_contact_details",
        }
        if automation_result.get("skipped") and skip_retry:
            pass
        elif not automation_result.get("ok"):
            schedule_post_call_automation_retry(task.id)
        elif not transcript:
            # Transcript may land after hangup — re-sync outcome and send offer if still missing.
            schedule_post_call_automation_retry(task.id, delay_seconds=90)
