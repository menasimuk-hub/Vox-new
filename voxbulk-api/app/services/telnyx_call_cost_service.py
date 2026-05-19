from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.frontpage_lead_call import FrontpageLeadCall
from app.models.lead_sales_task import LeadSalesTask
from app.services.telnyx_conversation_service import _telnyx_request, fetch_conversation_by_id

SUPPORTED_DATE_RANGES = {
    "today",
    "yesterday",
    "last_7_days",
    "last_30_days",
    "this_month",
    "last_month",
}

SESSION_LEG_TYPES = ("webrtc", "call-control", "sip-trunking", "recording", "tts", "stt")
DETAIL_LABELS = {
    "ai-voice-assistant": "Conversational AI",
    "webrtc": "WebRTC",
    "call-control": "Call control",
    "sip-trunking": "Telephony (SIP)",
    "recording": "Recording",
    "tts": "Text-to-speech",
    "stt": "Speech-to-text",
}


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _parse_iso(value: str | None) -> datetime | None:
    clean = str(value or "").strip()
    if not clean:
        return None
    try:
        if clean.endswith("Z"):
            clean = clean[:-1] + "+00:00"
        return datetime.fromisoformat(clean.replace("Z", "+00:00"))
    except ValueError:
        return None


def _detail_records(
    db: Session,
    *,
    record_type: str,
    date_range: str | None = None,
    session_id: str | None = None,
    page_number: int = 1,
    page_size: int = 50,
) -> tuple[list[dict[str, Any]], dict[str, Any], str | None]:
    params: list[tuple[str, str]] = [
        ("filter[record_type]", record_type),
        ("page[number]", str(max(1, page_number))),
        ("page[size]", str(max(1, min(page_size, 50)))),
        ("sort[]", "-created_at"),
    ]
    if session_id:
        params.append(("filter[telnyx_session_id]", session_id))
    elif date_range:
        params.append(("filter[date_range]", date_range))
    body, err = _telnyx_request(db, "GET", "/detail_records", params=params, timeout=35.0)
    if err:
        return [], {}, err
    if not isinstance(body, dict):
        return [], {}, "Telnyx returned an unexpected detail-records payload"
    rows = body.get("data")
    meta = body.get("meta") if isinstance(body.get("meta"), dict) else {}
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else [], meta, None


def _paginate_detail_records(
    db: Session,
    record_type: str,
    *,
    date_range: str,
    max_pages: int = 20,
    page_size: int = 50,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    page = 1
    while page <= max_pages:
        batch, meta, err = _detail_records(
            db,
            record_type=record_type,
            date_range=date_range,
            page_number=page,
            page_size=page_size,
        )
        if err:
            break
        rows.extend(batch)
        total_pages = int(meta.get("total_pages") or 1)
        if page >= total_pages or not batch:
            break
        page += 1
    return rows


def _session_legs_index_for_range(
    db: Session,
    date_range: str,
    *,
    max_pages: int = 4,
) -> dict[str, list[dict[str, Any]]]:
    index: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record_type in SESSION_LEG_TYPES:
        for row in _paginate_detail_records(
            db,
            record_type,
            date_range=date_range,
            max_pages=max_pages,
        ):
            session_id = str(row.get("telnyx_session_id") or row.get("session_id") or "").strip()
            if not session_id:
                continue
            tagged = dict(row)
            tagged["record_type"] = record_type
            index[session_id].append(tagged)
    return index


def _fetch_assistant_names(db: Session) -> dict[str, str]:
    body, err = _telnyx_request(db, "GET", "/ai/assistants", params={"page[size]": 100}, timeout=25.0)
    if err or not isinstance(body, dict):
        return {}
    rows = body.get("data")
    if not isinstance(rows, list):
        return {}
    names: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        assistant_id = str(row.get("id") or "").strip()
        if not assistant_id:
            continue
        names[assistant_id] = str(row.get("name") or assistant_id).strip() or assistant_id
    return names


def _looks_like_phone(value: str) -> bool:
    clean = str(value or "").strip()
    return clean.startswith("+") and clean[1:].replace(" ", "").isdigit()


def _looks_like_webrtc_target(value: str) -> bool:
    clean = str(value or "").strip().lower()
    return "@assistant-" in clean and ".sip.telnyx" in clean


def _infer_transport(conversation: dict[str, Any] | None, legs: list[dict[str, Any]]) -> str:
    if any(str(leg.get("record_type") or "") == "webrtc" for leg in legs):
        return "web"
    metadata = conversation.get("metadata") if isinstance(conversation, dict) else {}
    if isinstance(metadata, dict):
        agent_target = str(metadata.get("telnyx_agent_target") or metadata.get("to") or "")
        if _looks_like_webrtc_target(agent_target):
            return "web"
    if any(bool(leg.get("is_webrtc")) for leg in legs if str(leg.get("record_type") or "") == "sip-trunking"):
        return "web"
    for leg in legs:
        if str(leg.get("record_type") or "") == "sip-trunking":
            cld = str(leg.get("cld") or leg.get("dest_number") or "")
            if _looks_like_webrtc_target(cld):
                return "web"
            if _looks_like_phone(cld):
                return "phone"
    return "phone"


def _infer_destination(
    conversation: dict[str, Any] | None,
    legs: list[dict[str, Any]],
    ai_row: dict[str, Any],
) -> str:
    metadata = conversation.get("metadata") if isinstance(conversation, dict) else {}
    if isinstance(metadata, dict):
        end_user = str(metadata.get("telnyx_end_user_target") or metadata.get("to") or "").strip()
        if _looks_like_phone(end_user):
            return end_user
    for leg in legs:
        record_type = str(leg.get("record_type") or "")
        for key in ("dest_number", "cld", "caller_number", "cli"):
            value = str(leg.get(key) or "").strip()
            if _looks_like_phone(value):
                return value
            if record_type == "webrtc" and _looks_like_webrtc_target(value):
                continue
    conversation_id = str(ai_row.get("conversation_id") or "").strip()
    if conversation_id:
        return conversation_id[:13] + "…"
    return "—"


def _format_duration(seconds: int | float | None) -> int:
    try:
        return max(0, int(round(float(seconds or 0))))
    except (TypeError, ValueError):
        return 0


def _sum_leg_costs(legs: list[dict[str, Any]]) -> float:
    return round(sum(_safe_float(leg.get("cost")) for leg in legs), 6)


def _local_source_links(db: Session, conversation_id: str, call_control_id: str) -> dict[str, Any]:
    conv = str(conversation_id or "").strip()
    control = str(call_control_id or "").strip()

    if conv:
        lead = db.execute(
            select(FrontpageLeadCall)
            .where(FrontpageLeadCall.provider_call_id == conv)
            .order_by(FrontpageLeadCall.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        if lead is not None:
            return {
                "source_type": "intake",
                "source_label": "Website intake",
                "source_id": lead.id,
                "contact_name": lead.contact_name or lead.company_name,
            }

    task_filters = []
    if conv:
        task_filters.append(LeadSalesTask.telnyx_conversation_id == conv)
        task_filters.append(LeadSalesTask.provider_call_id == conv)
    if control:
        task_filters.append(LeadSalesTask.provider_call_id == control)
    if task_filters:
        task = db.execute(
            select(LeadSalesTask)
            .where(or_(*task_filters))
            .order_by(LeadSalesTask.updated_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        if task is not None:
            return {
                "source_type": "sales",
                "source_label": "Lead sales outbound",
                "source_id": task.id,
                "contact_name": task.contact_name or task.company_name,
            }
    return {"source_type": None, "source_label": None, "source_id": None, "contact_name": None}


def _fetch_conversations_map(db: Session, conversation_ids: list[str]) -> dict[str, dict[str, Any]]:
    clean_ids = [cid for cid in dict.fromkeys(str(x or "").strip() for x in conversation_ids) if cid]
    results: dict[str, dict[str, Any]] = {}
    for cid in clean_ids:
        conv = fetch_conversation_by_id(db, cid)
        if conv:
            results[cid] = conv
    return results


def _component_rows(ai_row: dict[str, Any], legs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    ai_type = "ai-voice-assistant"
    rows.append(
        {
            "record_type": ai_type,
            "label": DETAIL_LABELS[ai_type],
            "cost": round(_safe_float(ai_row.get("cost")), 6),
            "currency": str(ai_row.get("currency") or "USD"),
            "duration_sec": _format_duration(ai_row.get("duration_sec") or ai_row.get("billed_sec")),
            "rate": ai_row.get("rate"),
            "details": {
                "llm_model": ai_row.get("llm_model"),
                "stt_model": ai_row.get("stt_model"),
                "tts_provider": ai_row.get("tts_provider"),
                "tts_model_id": ai_row.get("tts_model_id"),
                "tts_voice_id": ai_row.get("tts_voice_id"),
                "billed_sec": ai_row.get("billed_sec"),
            },
        }
    )
    for leg in legs:
        record_type = str(leg.get("record_type") or "").strip()
        if not record_type:
            continue
        rows.append(
            {
                "record_type": record_type,
                "label": DETAIL_LABELS.get(record_type, record_type.replace("-", " ").title()),
                "cost": round(_safe_float(leg.get("cost")), 6),
                "currency": str(leg.get("currency") or ai_row.get("currency") or "USD"),
                "duration_sec": _format_duration(
                    leg.get("call_sec") or leg.get("duration_sec") or leg.get("billed_sec")
                ),
                "rate": leg.get("rate"),
                "details": {
                    key: leg.get(key)
                    for key in (
                        "direction",
                        "cli",
                        "cld",
                        "dest_number",
                        "caller_number",
                        "connection_name",
                        "is_webrtc",
                        "country_code",
                        "billed_sec",
                    )
                    if leg.get(key) not in (None, "")
                },
            }
        )
    return rows


def _serialize_call_row(
    ai_row: dict[str, Any],
    *,
    assistant_names: dict[str, str],
    session_legs: dict[str, list[dict[str, Any]]],
    conversations: dict[str, dict[str, Any]],
    local_source: dict[str, Any] | None = None,
) -> dict[str, Any]:
    session_id = str(ai_row.get("telnyx_session_id") or "").strip()
    conversation_id = str(ai_row.get("conversation_id") or "").strip()
    assistant_id = str(ai_row.get("assistant_id") or "").strip()
    legs = list(session_legs.get(session_id, []))
    conversation = conversations.get(conversation_id)
    ai_cost = round(_safe_float(ai_row.get("cost")), 6)
    leg_cost = round(_sum_leg_costs(legs), 6)
    total_cost = round(ai_cost + leg_cost, 6)
    transport = _infer_transport(conversation, legs)
    destination = _infer_destination(conversation, legs, ai_row)
    duration_sec = _format_duration(ai_row.get("duration_sec") or ai_row.get("billed_sec"))
    created_at = str(ai_row.get("created_at") or ai_row.get("completed_at") or "")
    local = local_source or {}
    agent_name = assistant_names.get(assistant_id) or assistant_id or "Unknown agent"
    return {
        "id": session_id or conversation_id or str(ai_row.get("call_control_id") or ""),
        "session_id": session_id,
        "conversation_id": conversation_id,
        "call_control_id": str(ai_row.get("call_control_id") or ""),
        "assistant_id": assistant_id,
        "agent_name": agent_name,
        "destination": destination,
        "duration_sec": duration_sec,
        "duration_label": _duration_label(duration_sec),
        "transport": transport,
        "transport_label": "WebRTC" if transport == "web" else "Phone",
        "ai_cost": ai_cost,
        "telephony_cost": leg_cost,
        "total_cost": total_cost,
        "currency": str(ai_row.get("currency") or "USD"),
        "created_at": created_at,
        "completed_at": str(ai_row.get("completed_at") or ""),
        "source_type": local.get("source_type"),
        "source_label": local.get("source_label"),
        "source_id": local.get("source_id"),
        "contact_name": local.get("contact_name"),
        "llm_model": ai_row.get("llm_model"),
        "connected": bool(ai_row.get("connected")),
    }


def _duration_label(seconds: int) -> str:
    mins, secs = divmod(max(0, int(seconds)), 60)
    return f"{mins}:{secs:02d}"


def list_call_costs(
    db: Session,
    *,
    date_range: str = "last_30_days",
    page: int = 1,
    page_size: int = 25,
    transport: str | None = None,
    search: str | None = None,
) -> dict[str, Any]:
    clean_range = str(date_range or "last_30_days").strip()
    if clean_range not in SUPPORTED_DATE_RANGES:
        clean_range = "last_30_days"
    page_number = max(1, int(page or 1))
    page_size = max(1, min(int(page_size or 25), 50))

    ai_rows, meta, err = _detail_records(
        db,
        record_type="ai-voice-assistant",
        date_range=clean_range,
        page_number=page_number,
        page_size=page_size,
    )
    if err:
        raise ValueError(err)

    assistant_names = _fetch_assistant_names(db)
    session_legs = _session_legs_index_for_range(db, clean_range, max_pages=2)

    items: list[dict[str, Any]] = []
    for ai_row in ai_rows:
        conversation_id = str(ai_row.get("conversation_id") or "")
        call_control_id = str(ai_row.get("call_control_id") or "")
        local = _local_source_links(db, conversation_id, call_control_id)
        row = _serialize_call_row(
            ai_row,
            assistant_names=assistant_names,
            session_legs=session_legs,
            conversations={},
            local_source=local,
        )
        if transport in {"web", "phone"} and row["transport"] != transport:
            continue
        if search:
            needle = search.strip().lower()
            haystack = " ".join(
                str(row.get(key) or "")
                for key in (
                    "agent_name",
                    "destination",
                    "contact_name",
                    "source_label",
                    "conversation_id",
                    "session_id",
                )
            ).lower()
            if needle not in haystack:
                continue
        items.append(row)

    summary_rows = _paginate_detail_records(db, "ai-voice-assistant", date_range=clean_range, max_pages=5)
    summary_items = [
        _serialize_call_row(
            row,
            assistant_names=assistant_names,
            session_legs=session_legs,
            conversations={},
        )
        for row in summary_rows
    ]
    total_cost = round(sum(item["total_cost"] for item in summary_items), 4)
    web_calls = sum(1 for item in summary_items if item["transport"] == "web")
    phone_calls = sum(1 for item in summary_items if item["transport"] == "phone")

    return {
        "date_range": clean_range,
        "summary": {
            "total_calls": int(meta.get("total_results") or len(summary_items)),
            "total_cost": total_cost,
            "currency": str((summary_items[0]["currency"] if summary_items else "USD") or "USD"),
            "web_calls": web_calls,
            "phone_calls": phone_calls,
            "avg_cost": round(total_cost / len(summary_items), 4) if summary_items else 0,
        },
        "items": items,
        "pagination": {
            "page": page_number,
            "page_size": page_size,
            "total_pages": int(meta.get("total_pages") or 1),
            "total_results": int(meta.get("total_results") or len(items)),
        },
    }


def get_call_cost_detail(db: Session, session_id: str) -> dict[str, Any]:
    clean_session = str(session_id or "").strip()
    if not clean_session:
        raise ValueError("Session id is required")

    ai_rows, _, err = _detail_records(
        db,
        record_type="ai-voice-assistant",
        session_id=clean_session,
        page_size=5,
    )
    if err:
        raise ValueError(err)
    if not ai_rows:
        raise ValueError("Call not found in Telnyx detail records")

    ai_row = ai_rows[0]
    legs: list[dict[str, Any]] = []
    for record_type in SESSION_LEG_TYPES:
        batch, _, leg_err = _detail_records(
            db,
            record_type=record_type,
            session_id=clean_session,
            page_size=20,
        )
        if leg_err:
            continue
        for leg in batch:
            tagged = dict(leg)
            tagged["record_type"] = record_type
            legs.append(tagged)

    conversation_id = str(ai_row.get("conversation_id") or "").strip()
    conversation = fetch_conversation_by_id(db, conversation_id) if conversation_id else None
    assistant_names = _fetch_assistant_names(db)
    local = _local_source_links(db, conversation_id, str(ai_row.get("call_control_id") or ""))
    call = _serialize_call_row(
        ai_row,
        assistant_names=assistant_names,
        session_legs={clean_session: legs},
        conversations={conversation_id: conversation} if conversation else {},
        local_source=local,
    )
    components = _component_rows(ai_row, legs)
    metadata = conversation.get("metadata") if isinstance(conversation, dict) else {}
    return {
        "call": call,
        "components": components,
        "conversation": {
            "id": conversation_id,
            "created_at": conversation.get("created_at") if isinstance(conversation, dict) else None,
            "last_message_at": conversation.get("last_message_at") if isinstance(conversation, dict) else None,
            "metadata": metadata if isinstance(metadata, dict) else {},
            "number_of_messages": conversation.get("number_of_messages") if isinstance(conversation, dict) else None,
        },
        "raw": {
            "ai_voice_assistant": ai_row,
            "legs": legs,
        },
    }
