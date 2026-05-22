import json
import logging

logger = logging.getLogger(__name__)
import re
import secrets
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.frontpage_call_setting import FrontpageCallSetting
from app.models.frontpage_lead_call import FrontpageLeadCall
from app.services.agents.base import AgentMessage, AgentRuntimeContext
from app.services.agents.manager import AgentManager
from app.services.providers.openai_service import OpenAIProviderService

_REPO_ROOT = Path(__file__).resolve().parents[2]
RECORDINGS_ROOT = _REPO_ROOT / "data" / "frontpage-recordings"

_EXTRACT_META = """You analyse a website voice lead call transcript.
Return ONLY valid JSON with these fields:
- "contact_name": string or null
- "company_name": string or null
- "email": string or null
- "phone": string or null
- "phone_confirmed": boolean
- "interest_summary": short string (what they want)
- "next_step": short string (recommended sales follow-up)
- "recommendation": one of "advance", "hold", "decline"
- "sentiment": one of "enthusiastic", "neutral", "hesitant"
- "lead_payload": object with any extra structured facts for outbound sales (budget, timeline, role, objections, etc.)
- "wants_sales_call": boolean — true if they asked for a sales call, demo, pricing, a colleague to call them, or any callback ("call me", "call me back", "ring me", etc.)
- "scheduled_callback_at": ISO-8601 datetime string for agreed callback (local wall time if no offset), or null if ASAP / not specified
- "callback_timezone": IANA timezone e.g. Europe/London, Australia/Sydney, America/Toronto, or null
- "country": country name or ISO code if mentioned (UK, Australia, Canada, etc.), or null
- "callback_consent": boolean — true if they clearly agreed to be called on their confirmed mobile number (yes to callback, "call me", arrange a colleague to call, etc.). Do not require the exact legal consent script wording if agreement is obvious.
- "sales_intent": short string — what they want to buy or discuss on the sales call

British English. Be factual — only use information stated in the transcript. If the visitor requests an immediate or ASAP callback, set wants_sales_call and callback_consent true and leave scheduled_callback_at null."""


def ensure_recordings_root() -> Path:
    RECORDINGS_ROOT.mkdir(parents=True, exist_ok=True)
    return RECORDINGS_ROOT


def generate_lead_code() -> str:
    stamp = datetime.utcnow().strftime("%Y%m%d")
    suffix = secrets.token_hex(2).upper()
    return f"LD-{stamp}-{suffix}"


def parse_kb_file_ids(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return [str(item).strip() for item in data if str(item).strip()]


def dump_kb_file_ids(file_ids: list[str]) -> str:
    unique = []
    seen: set[str] = set()
    for fid in file_ids:
        clean = str(fid or "").strip()
        if clean and clean not in seen:
            seen.add(clean)
            unique.append(clean)
    return json.dumps(unique)


def resolve_frontpage_base_prompt(
    db: Session,
    *,
    settings: FrontpageCallSetting,
    agent: object | None = None,
) -> str:
    """Admin saved system prompt drives both Vapi overrides and Telnyx assistant sync."""
    custom = str(settings.system_prompt or "").strip()
    voice = str(settings.voice_provider or "vapi").strip().lower()
    provider_agent_id = str(settings.provider_agent_id or "").strip()

    if voice == "telnyx":
        if custom:
            return custom
        if provider_agent_id:
            try:
                from app.services.telnyx_assistant_service import telnyx_assistant_instructions

                telnyx_prompt = telnyx_assistant_instructions(db, provider_agent_id)
                if telnyx_prompt:
                    return telnyx_prompt
            except Exception:
                pass

    if custom:
        return custom
    if agent is not None and getattr(agent, "id", None):
        org_id = str(getattr(settings, "org_id", None) or "").strip()
        if not org_id:
            from sqlalchemy import select

            from app.models.organisation import Organisation

            org_id = db.execute(select(Organisation.id).order_by(Organisation.created_at.asc()).limit(1)).scalar_one_or_none() or ""
        if org_id:
            context = AgentRuntimeContext(
                org_id=str(org_id),
                user_id=None,
                agent_id=getattr(agent, "id", None),
                workflow_type="frontpage-talk-to-us",
            )
            return AgentManager.build_system_prompt(db, agent=agent, context=context).strip()
    return ""


def build_runtime_system_prompt(
    *,
    settings_prompt: str | None,
    kb_context: str | None = None,
    lead_context: str | None = None,
    include_kb: bool = True,
) -> str:
    """Assemble live voice prompt: saved script + optional cached KB + per-call visitor context."""
    parts: list[str] = []
    base = str(settings_prompt or "").strip()
    if base:
        parts.append(base)
    if include_kb:
        kb = str(kb_context or "").strip()
        if kb:
            from app.services.knowledge_base_service import kb_context_already_in_prompt

            if not kb_context_already_in_prompt(base, kb):
                parts.append(f"Reference facts (do not read verbatim — use only when relevant):\n{kb}")
    lead = str(lead_context or "").strip()
    if lead:
        parts.append(lead)
    return "\n\n".join(parts).strip() or AgentManager.format_lead_context(contact_name="there", company_name="their company", email="", phone=None)


def build_lead_runtime_prompt(
    settings: FrontpageCallSetting,
    *,
    settings_prompt: str | None = None,
    lead_context: str | None = None,
) -> str:
    """Website lead (Jode) runtime prompt: system prompt + lead-scoped KB cache + visitor context."""
    base = settings_prompt if settings_prompt is not None else settings.system_prompt
    return build_runtime_system_prompt(
        settings_prompt=base,
        kb_context=settings.kb_context,
        lead_context=lead_context,
        include_kb=True,
    )


def intake_call_opening_greeting(
    first_name: str,
    system_prompt: str,
    *,
    saved_greeting: str | None = None,
) -> str:
    """First line the intake agent speaks as soon as the browser call connects."""
    from app.services.telnyx_assistant_service import derive_greeting_from_prompt, personalize_greeting

    saved = str(saved_greeting or "").strip()
    if saved:
        line = personalize_greeting(saved, first_name=first_name)
    else:
        first = str(first_name or "").strip() or "there"
        derived = derive_greeting_from_prompt(system_prompt)
        if derived:
            line = derived.replace("Hi there,", f"Hi {first},").replace("Hi there", f"Hi {first}")
        else:
            line = f"Hi {first}, thanks for contacting VOXBULK. How can I help you today?"
    if "recorded" not in line.lower():
        line = f"{line} This call is recorded for quality — see voxbulk.com for privacy."
    return line


def recording_abs_path(rel_path: str) -> Path:
    return _REPO_ROOT / rel_path.replace("\\", "/")


def lead_source_out(row: FrontpageLeadCall, *, sales_task: dict | None = None) -> dict:
    lead_data = None
    if row.lead_data_json:
        try:
            lead_data = json.loads(row.lead_data_json)
        except json.JSONDecodeError:
            lead_data = {"raw": row.lead_data_json}
    has_local_recording = bool(row.recording_path)
    provider = str(row.voice_provider or "").strip().lower()
    has_vapi_call = provider == "vapi" and bool(str(row.provider_call_id or "").strip())
    has_telnyx_call = provider == "telnyx" and bool(str(row.provider_agent_id or "").strip())
    has_telnyx_transcript = provider == "telnyx" and bool(str(row.transcript_text or "").strip())
    recording_available = has_local_recording or has_vapi_call or has_telnyx_call
    if provider == "telnyx" and has_telnyx_call:
        recording_url = f"/admin/frontpage/lead-sources/{row.id}/recording"
    elif has_local_recording:
        recording_url = f"/admin/frontpage/lead-sources/{row.id}/recording"
    else:
        recording_url = None
    transcript_text = str(row.transcript_text or "").strip() or None
    agent_text = str(row.agent_response_text or "").strip() or None
    return {
        "id": row.id,
        "lead_code": row.lead_code,
        "contact_name": row.contact_name,
        "company_name": row.company_name,
        "email": row.email,
        "phone": row.phone,
        "status": row.status,
        "voice_provider": row.voice_provider,
        "provider_agent_id": row.provider_agent_id,
        "provider_call_id": row.provider_call_id,
        "duration_seconds": row.duration_seconds,
        "duration_label": _duration_label(row.duration_seconds),
        "recommendation": row.recommendation or "hold",
        "sentiment": row.sentiment or "neutral",
        "transcript_text": transcript_text,
        "agent_response_text": row.agent_response_text,
        "lead_data": lead_data,
        "recording_url": recording_url,
        "recording_available": recording_available,
        "transcript_available": bool(transcript_text) or has_vapi_call or has_telnyx_call or has_telnyx_transcript or bool(agent_text),
        "created_at": row.created_at,
        "completed_at": row.completed_at,
        "sales_task": sales_task,
        "wants_sales_call": bool((lead_data or {}).get("wants_sales_call")) if isinstance(lead_data, dict) else False,
        "scheduled_callback_at": (lead_data or {}).get("scheduled_callback_at") if isinstance(lead_data, dict) else None,
    }


def combined_lead_transcript(lead: FrontpageLeadCall) -> str:
    return "\n".join(
        part.strip()
        for part in (str(lead.transcript_text or ""), str(lead.agent_response_text or ""))
        if part and part.strip()
    )


def apply_lead_intelligence(
    db: Session,
    lead: FrontpageLeadCall,
    *,
    transcript: str | None = None,
) -> dict:
    """Run DeepSeek extraction on transcript and persist recommendation / lead_data_json."""
    combined = str(transcript if transcript is not None else combined_lead_transcript(lead)).strip()
    extracted = extract_lead_data(
        db,
        transcript=combined,
        contact_name=lead.contact_name,
        company_name=lead.company_name,
        email=lead.email,
        phone=lead.phone,
    )
    lead.recommendation = extracted.get("recommendation")
    lead.sentiment = extracted.get("sentiment")
    lead.lead_data_json = json.dumps(extracted)
    db.add(lead)
    db.commit()
    db.refresh(lead)
    return extracted


def enrich_lead_after_transcript_update(db: Session, lead: FrontpageLeadCall) -> dict:
    """Re-extract lead fields and auto-create a sales task when rules match."""
    extracted = apply_lead_intelligence(db, lead)
    try:
        from app.services.lead_sales_service import maybe_create_sales_task_from_lead

        task = maybe_create_sales_task_from_lead(db, lead, extracted)
        if task is None and should_log_sales_skip(extracted):
            logger.info(
                "sales_task_not_auto_created lead_id=%s wants_sales=%s consent=%s phone=%s",
                lead.id,
                extracted.get("wants_sales_call"),
                extracted.get("callback_consent"),
                bool(str(extracted.get("phone") or lead.phone or "").strip()),
            )
    except Exception:
        logger.exception("sales_task_auto_create_failed lead_id=%s", lead.id)
    return extracted


def should_log_sales_skip(extracted: dict) -> bool:
    """Log when extraction suggests sales interest but no task was created."""
    return bool(extracted.get("wants_sales_call") or extracted.get("callback_consent"))


def _duration_label(seconds: int | None) -> str:
    if seconds is None or seconds < 0:
        return "—"
    mins, secs = divmod(int(seconds), 60)
    return f"{mins}m {secs:02d}s"


def extract_lead_data(db: Session, *, transcript: str, contact_name: str | None, company_name: str, email: str, phone: str | None) -> dict:
    clean_transcript = str(transcript or "").strip()
    if not clean_transcript:
        return {
            "contact_name": contact_name,
            "company_name": company_name,
            "email": email,
            "phone": phone,
            "phone_confirmed": False,
            "interest_summary": "",
            "next_step": "Review lead details and call back.",
            "recommendation": "hold",
            "sentiment": "neutral",
            "lead_payload": {},
            "wants_sales_call": False,
            "scheduled_callback_at": None,
            "callback_timezone": None,
            "country": None,
            "callback_consent": False,
            "sales_intent": None,
        }
    user_block = "\n".join(
        [
            f"Known contact name: {contact_name or 'unknown'}",
            f"Known company: {company_name}",
            f"Known email: {email}",
            f"Known phone: {phone or 'unknown'}",
            f"Transcript:\n{clean_transcript}",
        ]
    )
    result = OpenAIProviderService.complete(
        db,
        system_prompt=_EXTRACT_META,
        messages=[AgentMessage(role="user", content=user_block)],
        max_tokens=900,
        temperature=0.2,
        provider="deepseek",
    )
    text = str(result.assistant_text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                data = json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                data = {}
        else:
            data = {}
        if not isinstance(data, dict):
            data = {}
        for key, pattern in (
            ("wants_sales_call", r'"wants_sales_call"\s*:\s*(true|false)'),
            ("callback_consent", r'"callback_consent"\s*:\s*(true|false)'),
            ("phone_confirmed", r'"phone_confirmed"\s*:\s*(true|false)'),
        ):
            if key not in data:
                match = re.search(pattern, text, re.I)
                if match:
                    data[key] = match.group(1).lower() == "true"
        for key in ("interest_summary", "next_step", "sales_intent", "recommendation", "sentiment"):
            if not data.get(key):
                match = re.search(rf'"{key}"\s*:\s*"([^"]*)"', text)
                if match:
                    data[key] = match.group(1)
    if not isinstance(data, dict):
        data = {}
    recommendation = str(data.get("recommendation") or "hold").strip().lower()
    if recommendation not in {"advance", "hold", "decline"}:
        recommendation = "hold"
    sentiment = str(data.get("sentiment") or "neutral").strip().lower()
    if sentiment not in {"enthusiastic", "neutral", "hesitant"}:
        sentiment = "neutral"
    payload = data.get("lead_payload")
    if not isinstance(payload, dict):
        payload = {}
    return {
        "contact_name": data.get("contact_name") or contact_name,
        "company_name": data.get("company_name") or company_name,
        "email": data.get("email") or email,
        "phone": data.get("phone") or phone,
        "phone_confirmed": bool(data.get("phone_confirmed")),
        "interest_summary": str(data.get("interest_summary") or "").strip(),
        "next_step": str(data.get("next_step") or "").strip(),
        "recommendation": recommendation,
        "sentiment": sentiment,
        "lead_payload": payload,
        "wants_sales_call": bool(data.get("wants_sales_call")),
        "scheduled_callback_at": str(data.get("scheduled_callback_at") or "").strip() or None,
        "callback_timezone": str(data.get("callback_timezone") or "").strip() or None,
        "country": str(data.get("country") or "").strip() or None,
        "callback_consent": bool(data.get("callback_consent")),
        "sales_intent": str(data.get("sales_intent") or "").strip() or None,
    }
