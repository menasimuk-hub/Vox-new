from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.frontpage_lead_call import FrontpageLeadCall
from app.models.lead_sales_setting import LeadSalesSetting
from app.models.lead_sales_task import LeadSalesTask
from app.services.frontpage_lead_service import dump_kb_file_ids, parse_kb_file_ids
from app.services.knowledge_base_service import (
    KB_SCOPE_SALES,
    build_kb_context_text,
    get_kb_files_by_ids,
    sanitize_kb_file_ids,
)
from app.services.lead_sales_prompt_generator import generate_lead_sales_prompt
from app.services.telnyx_api_key import normalize_telnyx_e164, telnyx_outbound_caller_id
from app.services.telnyx_assistant_service import normalize_telnyx_assistant_id, sync_telnyx_assistant_instructions
from app.services.telnyx_voice_service import TelnyxVoiceAdapter, _telnyx_config, _decode_client_state
from app.utils.callback_timezone import resolve_callback_timezone


TASK_STATUSES = {"scheduled", "calling", "paused", "completed", "failed", "cancelled", "no_answer"}


def get_lead_sales_settings(db: Session) -> LeadSalesSetting:
    row = db.get(LeadSalesSetting, "default")
    if row is None:
        row = LeadSalesSetting(id="default", updated_at=datetime.utcnow())
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def refresh_lead_sales_kb(row: LeadSalesSetting, db: Session) -> None:
    ids = sanitize_kb_file_ids(db, parse_kb_file_ids(row.kb_file_ids), scope=KB_SCOPE_SALES)
    row.kb_file_ids = dump_kb_file_ids(ids)
    files = get_kb_files_by_ids(db, ids, scope=KB_SCOPE_SALES)
    row.kb_context = build_kb_context_text(files) or None


def lead_sales_settings_out(row: LeadSalesSetting) -> dict[str, Any]:
    return {
        "telnyx_assistant_id": row.telnyx_assistant_id,
        "prompt_description": row.prompt_description,
        "system_prompt": row.system_prompt,
        "kb_file_ids": parse_kb_file_ids(row.kb_file_ids),
        "kb_context_chars": len(row.kb_context or ""),
        "calling_hour_start": int(row.calling_hour_start or 9),
        "calling_hour_end": int(row.calling_hour_end or 18),
        "calling_days": str(row.calling_days or "1,2,3,4,5"),
        "assistant_configured": bool(str(row.telnyx_assistant_id or "").strip()),
        "master_prompt_configured": bool(str(row.system_prompt or "").strip()),
        "sales_automation_enabled": bool(getattr(row, "sales_automation_enabled", True)),
        "sales_auto_plan_code": str(getattr(row, "sales_auto_plan_code", None) or "dental_1"),
        "sales_auto_trial_days": int(getattr(row, "sales_auto_trial_days", None) or 15),
        "sales_auto_offer_type": str(getattr(row, "sales_auto_offer_type", None) or "dental_trial"),
        "sales_auto_survey_contacts": int(getattr(row, "sales_auto_survey_contacts", None) or 3),
        "sales_auto_interview_contacts": int(getattr(row, "sales_auto_interview_contacts", None) or 3),
        "sales_template_subscription_id": getattr(row, "sales_template_subscription_id", None),
        "sales_template_survey_id": getattr(row, "sales_template_survey_id", None),
        "sales_template_interview_id": getattr(row, "sales_template_interview_id", None),
        "sales_followup_days": int(getattr(row, "sales_followup_days", None) or 7),
        "updated_at": row.updated_at,
    }


def _sales_playbook_block(settings: LeadSalesSetting) -> str:
    parts = []
    master = str(settings.system_prompt or "").strip()
    if master:
        parts.append(f"Master sales script (follow this closely):\n{master}")
    playbook = str(settings.prompt_description or "").strip()
    if playbook:
        parts.append(f"Operator notes:\n{playbook}")
    kb = str(settings.kb_context or "").strip()
    if kb:
        parts.append(f"Sales knowledge base (Adam library only — authoritative):\n{kb}")
    return "\n\n".join(parts)


def sync_lead_sales_telnyx_assistant(db: Session, settings: LeadSalesSetting | None = None) -> dict[str, object]:
    """Push Adam master script + sales KB cache to the Telnyx sales assistant."""
    settings = settings or get_lead_sales_settings(db)
    refresh_lead_sales_kb(settings, db)
    agent_id = str(settings.telnyx_assistant_id or "").strip()
    sync_prompt = _sales_playbook_block(settings).strip()
    if not agent_id:
        return {"telnyx_synced": False, "telnyx_sync_warning": "Telnyx sales assistant ID is not set"}
    if not sync_prompt:
        return {"telnyx_synced": False, "telnyx_sync_warning": "Master sales script is empty"}
    try:
        sync_telnyx_assistant_instructions(db, agent_id, sync_prompt, enable_web_calls=False)
        return {"telnyx_synced": True, "telnyx_sync_warning": None}
    except Exception as exc:
        return {"telnyx_synced": False, "telnyx_sync_warning": str(exc)}


def get_sales_task_for_lead(db: Session, lead_id: str) -> LeadSalesTask | None:
    return db.execute(select(LeadSalesTask).where(LeadSalesTask.lead_id == lead_id).limit(1)).scalar_one_or_none()


def sales_task_brief(task: LeadSalesTask | None) -> dict[str, Any] | None:
    if task is None:
        return None
    return {
        "id": task.id,
        "status": task.status,
        "scheduled_at": task.scheduled_at,
        "call_done": task.status in {"completed", "failed", "no_answer"},
        "outcome_label": _outcome_label(_parse_outcome(task), task.status),
    }


def effective_callback_timezone(task: LeadSalesTask, *, country: str | None = None) -> str:
    return resolve_callback_timezone(
        explicit=task.callback_timezone,
        phone=task.phone,
        country=country,
    )


def _within_calling_hours(task: LeadSalesTask, settings: LeadSalesSetting) -> tuple[bool, str | None]:
    tz_name = effective_callback_timezone(task)
    try:
        local = datetime.utcnow().replace(tzinfo=timezone.utc).astimezone(ZoneInfo(tz_name))
    except Exception:
        local = datetime.utcnow().replace(tzinfo=timezone.utc)
    allowed_days = {int(x) for x in str(settings.calling_days or "1,2,3,4,5").split(",") if str(x).strip().isdigit()}
    if allowed_days and local.isoweekday() not in allowed_days:
        return False, f"Outside calling days for {tz_name}"
    start_h = int(settings.calling_hour_start or 9)
    end_h = int(settings.calling_hour_end or 18)
    if not (start_h <= local.hour < end_h):
        return False, f"Outside calling hours ({start_h}:00–{end_h}:00 {tz_name})"
    return True, None


def _parse_outcome(row: LeadSalesTask) -> dict[str, Any] | None:
    raw = str(row.outcome_json or "").strip()
    if not raw:
        return None
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None


def _table_status_label(task: LeadSalesTask, settings: LeadSalesSetting) -> str:
    if task.status == "calling":
        return "Calling now"
    if task.status == "paused":
        return "Paused"
    if task.status == "cancelled":
        return "Cancelled"
    if task.status == "no_answer":
        return "No answer — call again manually"
    if task.status == "failed":
        err = str(task.last_error or "").strip()
        return f"Failed{': ' + err[:80] if err else ''}"
    if task.status == "completed":
        label = _outcome_label(_parse_outcome(task), task.status)
        return label or "Call completed"
    if task.status == "scheduled":
        if not str(task.telnyx_assistant_id or settings.telnyx_assistant_id or "").strip():
            return "Needs Telnyx assistant ID"
        ok, err = _within_calling_hours(task, settings)
        if not ok:
            return err or "Outside calling hours"
        if task.scheduled_at and task.scheduled_at > datetime.utcnow():
            return "Scheduled — waiting for callback time"
        return "Ready to call"
    return str(task.status or "unknown")


def lead_sales_task_out(
    row: LeadSalesTask,
    *,
    lead_code: str | None = None,
    settings: LeadSalesSetting | None = None,
) -> dict[str, Any]:
    outcome = _parse_outcome(row)
    if settings is None:
        settings = LeadSalesSetting(
            id="default",
            calling_hour_start=9,
            calling_hour_end=18,
            calling_days="1,2,3,4,5",
            updated_at=datetime.utcnow(),
        )
    within_hours, hours_note = _within_calling_hours(row, settings)
    return {
        "id": row.id,
        "lead_id": row.lead_id,
        "lead_code": lead_code,
        "status": row.status,
        "call_done": row.status in {"completed", "failed", "no_answer"},
        "contact_name": row.contact_name,
        "company_name": row.company_name,
        "email": row.email,
        "phone": row.phone,
        "interest_summary": row.interest_summary,
        "sales_intent": row.sales_intent,
        "scheduled_at": row.scheduled_at,
        "callback_timezone": row.callback_timezone,
        "callback_consent": row.callback_consent,
        "telnyx_assistant_id": row.telnyx_assistant_id,
        "sales_prompt": row.sales_prompt,
        "sales_prompt_version": row.sales_prompt_version,
        "provider_call_id": row.provider_call_id,
        "last_error": row.last_error,
        "paused_at": row.paused_at,
        "call_started_at": row.call_started_at,
        "call_completed_at": row.call_completed_at,
        "telnyx_conversation_id": row.telnyx_conversation_id,
        "sales_transcript_text": row.sales_transcript_text,
        "outcome": outcome,
        "outcome_label": _outcome_label(outcome, row.status),
        "status_label": _table_status_label(row, settings),
        "within_calling_hours": within_hours,
        "calling_hours_note": hours_note,
        "offer_promo_code": row.offer_promo_code,
        "offer_sent_at": row.offer_sent_at,
        "offer_send_log": _parse_json_field(row.offer_send_log_json),
        "automation_paused": bool(getattr(row, "automation_paused", False)),
        "automation": None,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _parse_json_field(raw: str | None) -> dict[str, Any] | None:
    if not raw:
        return None
    try:
        import json

        val = json.loads(raw)
        return val if isinstance(val, dict) else None
    except Exception:
        return None


def _outcome_label(outcome: dict[str, Any] | None, status: str) -> str | None:
    if status == "no_answer":
        return "No answer"
    if status not in {"completed", "failed"}:
        return None
    if not outcome:
        return "Call done — sync results"
    if outcome.get("demo_agreed"):
        return "Demo booked"
    if outcome.get("interested_to_buy"):
        return "Interested to buy"
    stage = str(outcome.get("deal_stage") or "").strip().lower()
    if stage == "not_interested":
        return "Not interested"
    if stage == "won_intent":
        return "Ready to buy"
    if stage == "qualified":
        return "Qualified"
    return "Call completed"


def _parse_scheduled_at(value: str | None, tz_name: str | None) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    tz = str(tz_name or "UTC").strip() or "UTC"
    try:
        local = dt.replace(tzinfo=ZoneInfo(tz))
        return local.astimezone(timezone.utc).replace(tzinfo=None)
    except Exception:
        return dt


def sales_call_opening_greeting(task: LeadSalesTask) -> str:
    """First line the sales agent speaks as soon as the callee answers."""
    from app.services.telnyx_assistant_service import derive_greeting_from_prompt

    first = str(task.contact_name or "").strip().split()[0] if str(task.contact_name or "").strip() else "there"
    prompt = str(task.sales_prompt or "")
    derived = derive_greeting_from_prompt(prompt)
    if derived:
        line = (
            derived.replace("Hi there,", f"Hi {first},")
            .replace("Hi there", f"Hi {first}")
            .replace("thanks for reaching out", "thanks for taking our call")
        )
    else:
        line = f"Hi {first}, this is a follow-up from VoxBulk about your recent enquiry. Is now still a good time?"
    if "recorded" not in line.lower():
        line = f"{line} This call is recorded for quality — see voxbulk.com for privacy."
    return line


def _scheduled_label(task: LeadSalesTask) -> str:
    if not task.scheduled_at:
        return "As soon as possible"
    tz = str(task.callback_timezone or "UTC").strip() or "UTC"
    try:
        local = task.scheduled_at.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(tz))
        return local.strftime("%Y-%m-%d %H:%M") + f" ({tz})"
    except Exception:
        return task.scheduled_at.isoformat(sep=" ", timespec="minutes") + " UTC"


def should_auto_create_sales_task(extracted: dict[str, Any]) -> bool:
    phone = str(extracted.get("phone") or "").strip()
    if not phone:
        return False
    if extracted.get("callback_consent") is False:
        return False
    wants = bool(extracted.get("wants_sales_call"))
    if not wants:
        return False
    consent = bool(extracted.get("callback_consent"))
    scheduled = bool(str(extracted.get("scheduled_callback_at") or "").strip())
    advance = str(extracted.get("recommendation") or "").strip().lower() == "advance"
    # Sales task when they want a callback and gave consent; scheduled time or "advance" is a bonus, not required.
    return consent or scheduled or advance


def _build_task_from_lead(
    db: Session,
    lead: FrontpageLeadCall,
    extracted: dict[str, Any],
    *,
    settings: LeadSalesSetting,
) -> LeadSalesTask:
    scheduled = _parse_scheduled_at(
        str(extracted.get("scheduled_callback_at") or ""),
        str(extracted.get("callback_timezone") or ""),
    )
    if scheduled is None:
        scheduled = datetime.utcnow() + timedelta(hours=2)

    payload = extracted.get("lead_payload")
    if not isinstance(payload, dict):
        payload = {}

    assistant_id = str(settings.telnyx_assistant_id or "").strip() or None
    transcript = "\n".join(
        part.strip()
        for part in (str(lead.transcript_text or ""), str(lead.agent_response_text or ""))
        if part and part.strip()
    )
    task = LeadSalesTask(
        id=str(uuid.uuid4()),
        lead_id=lead.id,
        status="scheduled",
        contact_name=str(extracted.get("contact_name") or lead.contact_name or "").strip() or lead.contact_name,
        company_name=str(extracted.get("company_name") or lead.company_name or "").strip() or lead.company_name,
        email=str(extracted.get("email") or lead.email or "").strip() or lead.email,
        phone=str(extracted.get("phone") or lead.phone or "").strip() or lead.phone,
        interest_summary=str(extracted.get("interest_summary") or "").strip() or None,
        sales_intent=str(extracted.get("sales_intent") or extracted.get("interest_summary") or "").strip() or None,
        scheduled_at=scheduled,
        callback_timezone=resolve_callback_timezone(
            explicit=str(extracted.get("callback_timezone") or "").strip() or None,
            phone=str(extracted.get("phone") or lead.phone or "").strip() or None,
            country=str(extracted.get("country") or "").strip() or None,
        ),
        callback_consent=bool(extracted.get("callback_consent")),
        telnyx_assistant_id=assistant_id,
        sales_prompt_version=1,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    task.sales_prompt = generate_lead_sales_prompt(
        db,
        contact_name=task.contact_name or "there",
        company_name=task.company_name or "their company",
        interest_summary=task.interest_summary or "",
        sales_intent=task.sales_intent or "",
        lead_payload=payload,
        transcript_excerpt=transcript,
        playbook=_sales_playbook_block(settings),
        scheduled_label=_scheduled_label(task),
    )
    return task


def maybe_create_sales_task_from_lead(db: Session, lead: FrontpageLeadCall, extracted: dict[str, Any]) -> LeadSalesTask | None:
    if lead.status != "completed":
        return None
    existing = db.execute(select(LeadSalesTask).where(LeadSalesTask.lead_id == lead.id).limit(1)).scalar_one_or_none()
    if existing is not None:
        return None
    if not should_auto_create_sales_task(extracted):
        return None
    settings = get_lead_sales_settings(db)
    if not str(settings.telnyx_assistant_id or "").strip():
        return None
    task = _build_task_from_lead(db, lead, extracted, settings=settings)
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def create_sales_task_from_lead(db: Session, lead_id: str) -> tuple[LeadSalesTask, bool]:
    lead = db.get(FrontpageLeadCall, lead_id)
    if lead is None:
        raise ValueError("Lead not found")
    existing = get_sales_task_for_lead(db, lead_id)
    if existing is not None:
        return existing, True
    extracted: dict[str, Any] = {}
    if lead.lead_data_json:
        try:
            extracted = json.loads(lead.lead_data_json)
        except json.JSONDecodeError:
            extracted = {}
    if not isinstance(extracted, dict):
        extracted = {}
    extracted.setdefault("wants_sales_call", True)
    if not extracted.get("phone"):
        extracted["phone"] = lead.phone
    settings = get_lead_sales_settings(db)
    if not str(settings.telnyx_assistant_id or "").strip():
        raise ValueError("Set the Telnyx sales assistant ID on Lead Sales settings first")
    task = _build_task_from_lead(db, lead, extracted, settings=settings)
    db.add(task)
    db.commit()
    db.refresh(task)
    return task, False


def regenerate_sales_prompt(db: Session, task: LeadSalesTask) -> LeadSalesTask:
    settings = get_lead_sales_settings(db)
    refresh_lead_sales_kb(settings, db)
    db.add(settings)
    lead = db.get(FrontpageLeadCall, task.lead_id)
    payload: dict[str, Any] = {}
    transcript = ""
    if lead:
        if lead.lead_data_json:
            try:
                data = json.loads(lead.lead_data_json)
                if isinstance(data, dict):
                    payload = data.get("lead_payload") if isinstance(data.get("lead_payload"), dict) else data
            except json.JSONDecodeError:
                payload = {}
        transcript = "\n".join(
            part.strip()
            for part in (str(lead.transcript_text or ""), str(lead.agent_response_text or ""))
            if part and part.strip()
        )
    task.sales_prompt = generate_lead_sales_prompt(
        db,
        contact_name=task.contact_name or "there",
        company_name=task.company_name or "their company",
        interest_summary=task.interest_summary or "",
        sales_intent=task.sales_intent or "",
        lead_payload=payload if isinstance(payload, dict) else {},
        transcript_excerpt=transcript,
        playbook=_sales_playbook_block(settings),
        scheduled_label=_scheduled_label(task),
    )
    task.sales_prompt_version = int(task.sales_prompt_version or 0) + 1
    task.updated_at = datetime.utcnow()
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def prepare_sales_outbound_call(
    db: Session,
    task: LeadSalesTask,
    *,
    settings: LeadSalesSetting | None = None,
) -> tuple[str, str, str]:
    """Sync prompt + greeting to Telnyx before the phone rings."""
    settings = settings or get_lead_sales_settings(db)
    assistant_id = str(task.telnyx_assistant_id or settings.telnyx_assistant_id or "").strip()
    if not assistant_id:
        raise ValueError("Telnyx sales assistant ID is not configured")
    prompt = str(task.sales_prompt or "").strip()
    if not prompt:
        task = regenerate_sales_prompt(db, task)
        prompt = str(task.sales_prompt or "").strip()
    if not prompt:
        raise ValueError("Sales prompt is empty — regenerate the prompt first")
    greeting = sales_call_opening_greeting(task)
    sync_telnyx_assistant_instructions(
        db,
        assistant_id,
        prompt,
        greeting=greeting,
        enable_web_calls=False,
    )
    return assistant_id, prompt, greeting


def execute_sales_outbound_call(db: Session, task: LeadSalesTask) -> LeadSalesTask:
    if task.status == "paused":
        raise ValueError("Task is paused — resume it before calling")
    if task.status in {"cancelled", "completed", "no_answer"}:
        raise ValueError(f"Task is {task.status}")

    settings = get_lead_sales_settings(db)
    ok_hours, hours_err = _within_calling_hours(task, settings)
    if not ok_hours:
        raise ValueError(hours_err or "Outside calling hours")

    phone = str(task.phone or "").strip()
    if not phone:
        raise ValueError("Lead has no phone number for outbound call")

    assistant_id, _prompt, greeting = prepare_sales_outbound_call(db, task, settings=settings)
    config = _telnyx_config(db)
    from_number = telnyx_outbound_caller_id(config)
    if not from_number:
        raise ValueError("Telnyx outbound caller ID is not configured in Integrations")

    result = TelnyxVoiceAdapter.start_outbound_call(
        to_number=normalize_telnyx_e164(phone),
        from_number=from_number,
        config=config,
        client_state={
            "lead_sales_task_id": task.id,
            "telnyx_assistant_id": normalize_telnyx_assistant_id(assistant_id),
            "sales_prepared": True,
            "sales_greeting": greeting,
        },
    )
    now = datetime.utcnow()
    if not result.ok:
        task.status = "failed"
        task.last_error = result.detail or result.status or "Outbound call failed"
        task.updated_at = now
        db.add(task)
        db.commit()
        db.refresh(task)
        raise ValueError(task.last_error)

    task.status = "calling"
    task.provider_call_id = result.external_id
    task.call_started_at = now
    task.last_error = None
    task.updated_at = now
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def pause_sales_task(db: Session, task: LeadSalesTask) -> LeadSalesTask:
    if task.status == "calling" and task.provider_call_id:
        try:
            config = _telnyx_config(db)
            TelnyxVoiceAdapter.hangup_call(call_control_id=task.provider_call_id, config=config)
        except Exception:
            pass
    task.status = "paused"
    task.paused_at = datetime.utcnow()
    task.updated_at = datetime.utcnow()
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def resume_sales_task(db: Session, task: LeadSalesTask) -> LeadSalesTask:
    if task.status != "paused":
        raise ValueError("Only paused tasks can be resumed")
    task.status = "scheduled"
    task.paused_at = None
    task.updated_at = datetime.utcnow()
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def cancel_sales_task(db: Session, task: LeadSalesTask) -> LeadSalesTask:
    if task.status == "calling" and task.provider_call_id:
        try:
            config = _telnyx_config(db)
            TelnyxVoiceAdapter.hangup_call(call_control_id=task.provider_call_id, config=config)
        except Exception:
            pass
    task.status = "cancelled"
    task.updated_at = datetime.utcnow()
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def process_due_lead_sales_tasks(db: Session) -> int:
    now = datetime.utcnow()
    rows = list(
        db.execute(
            select(LeadSalesTask)
            .where(LeadSalesTask.status == "scheduled")
            .where(LeadSalesTask.scheduled_at.is_not(None))
            .where(LeadSalesTask.scheduled_at <= now)
            .order_by(LeadSalesTask.scheduled_at.asc())
            .limit(10)
        ).scalars()
    )
    settings = get_lead_sales_settings(db)
    started = 0
    for task in rows:
        try:
            ok_hours, _ = _within_calling_hours(task, settings)
            if not ok_hours:
                continue
            execute_sales_outbound_call(db, task)
            started += 1
        except Exception as exc:
            task.last_error = str(exc)
            task.updated_at = datetime.utcnow()
            db.add(task)
            db.commit()
    return started


def handle_lead_sales_telnyx_event(db: Session, payload: dict[str, Any]) -> None:
    data = payload.get("data") or payload
    event_type = str(data.get("event_type") or payload.get("event_type") or "").lower()
    record = data.get("payload") if isinstance(data.get("payload"), dict) else data
    call_id = str(record.get("call_control_id") or record.get("call_leg_id") or record.get("id") or "").strip()
    if not call_id:
        return

    client_state_raw = record.get("client_state")
    parsed = _decode_client_state(client_state_raw) if isinstance(client_state_raw, str) else None
    if not parsed:
        return
    task_id = str(parsed.get("lead_sales_task_id") or "").strip()
    assistant_id = str(parsed.get("telnyx_assistant_id") or "").strip()
    if not task_id:
        return

    task = db.get(LeadSalesTask, task_id)
    if task is None:
        return

    if "answered" in event_type:
        if assistant_id:
            config = _telnyx_config(db)
            prepared = bool(parsed.get("sales_prepared"))
            greeting = str(parsed.get("sales_greeting") or "").strip() or sales_call_opening_greeting(task)
            prompt = str(task.sales_prompt or "").strip()
            if not prepared and not prompt:
                task.last_error = "Sales prompt missing on answer — regenerate before calling"
                task.updated_at = datetime.utcnow()
                db.add(task)
                db.commit()
                return
            result = TelnyxVoiceAdapter.start_ai_assistant(
                call_control_id=call_id,
                assistant_id=assistant_id,
                config=config,
                instructions=prompt or None,
                greeting=greeting,
                prepared=prepared,
            )
            if not result.ok and prepared:
                result = TelnyxVoiceAdapter.start_ai_assistant(
                    call_control_id=call_id,
                    assistant_id=assistant_id,
                    config=config,
                    instructions=prompt or None,
                    greeting=greeting,
                    prepared=False,
                )
            if not result.ok:
                task.last_error = f"AI assistant did not start: {result.detail or result.status}"
                task.updated_at = datetime.utcnow()
                db.add(task)
                db.commit()
            elif result.payload and isinstance(result.payload, dict):
                data = result.payload.get("data") if isinstance(result.payload.get("data"), dict) else result.payload
                conv_id = str((data or {}).get("conversation_id") or "").strip()
                if conv_id:
                    task.telnyx_conversation_id = conv_id
                task.last_error = None
                task.updated_at = datetime.utcnow()
                db.add(task)
                db.commit()
        return

    if "hangup" in event_type or "ended" in event_type:
        from app.services.lead_sales_outcome_service import finalize_sales_task_after_call

        hangup_cause = str(record.get("hangup_cause") or record.get("sip_hangup_cause") or "").lower()
        no_answer_causes = {"no_answer", "originator_cancel", "timeout", "unallocated_number", "user_busy"}
        if any(c in hangup_cause for c in no_answer_causes) or "no answer" in hangup_cause:
            finalize_sales_task_after_call(db, task, status="no_answer")
        else:
            finalize_sales_task_after_call(db, task, status="completed")


def update_sales_task(db: Session, task: LeadSalesTask, payload: dict[str, Any]) -> LeadSalesTask:
    for key in ("contact_name", "company_name", "email", "phone", "interest_summary", "sales_intent", "callback_timezone"):
        if key in payload:
            setattr(task, key, str(payload.get(key) or "").strip() or None)
    if "phone" in payload and "callback_timezone" not in payload:
        task.callback_timezone = resolve_callback_timezone(
            explicit=task.callback_timezone,
            phone=task.phone,
        )
    elif "callback_timezone" in payload:
        task.callback_timezone = resolve_callback_timezone(
            explicit=str(payload.get("callback_timezone") or "").strip() or None,
            phone=task.phone,
        )
    if "callback_consent" in payload:
        task.callback_consent = bool(payload.get("callback_consent"))
    if "scheduled_at" in payload and payload.get("scheduled_at"):
        parsed = _parse_scheduled_at(str(payload.get("scheduled_at")), task.callback_timezone)
        if parsed:
            task.scheduled_at = parsed
    task.updated_at = datetime.utcnow()
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def delete_sales_task(db: Session, task: LeadSalesTask) -> None:
    if task.status == "calling" and task.provider_call_id:
        try:
            config = _telnyx_config(db)
            TelnyxVoiceAdapter.hangup_call(call_control_id=task.provider_call_id, config=config)
        except Exception:
            pass
    db.delete(task)
    db.commit()
