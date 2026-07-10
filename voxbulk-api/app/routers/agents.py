from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.agent_admin import require_agent_admin
from app.core.database import get_db
from app.models.agent import AgentAssignment, AgentDefinition
from app.models.category import Category
from app.models.organisation import Organisation
from app.models.user import User
from app.core.agent_services import AGENT_SERVICE_KEYS, AGENT_SERVICE_LABELS, normalize_service_key
from app.models.agent_service_assignment import AgentServiceAssignment
from app.services.agent_prompt_generator import generate_agent_prompts, generate_call_workflow, generate_system_prompt
from app.services.agents.base import AgentRunRequest, AgentRuntimeContext
from app.services.agents.manager import AgentManager
from app.services.agents.registry import AgentRegistry
from app.services.knowledge_base_service import (
    agent_knowledge_file_ids,
    get_kb_files_by_ids,
    refresh_agent_kb_context,
    set_agent_knowledge_files,
)
from app.services.survey_voice_agent_service import (
    _clear_other_defaults,
    _default_field,
    agent_to_voice_dict,
    get_platform_voice_settings,
    platform_settings_to_dict,
    update_platform_voice_settings,
)

router = APIRouter(prefix="/admin/agents", tags=["admin-agents"])

_PENDING_PROMPT = "(Not configured — use Generate with AI on the edit page.)"


def _slugify(raw: str) -> str:
    s = "".join(ch.lower() if ch.isalnum() else "-" for ch in str(raw or "").strip())
    while "--" in s:
        s = s.replace("--", "-")
    return s.strip("-") or "agent"


def _agent_out(db: Session, agent: AgentDefinition) -> dict:
    data = agent_to_voice_dict(agent)
    data["knowledge_file_ids"] = agent_knowledge_file_ids(db, agent.id)
    data["created_at"] = agent.created_at
    data["updated_at"] = agent.updated_at
    return data


def _service_assignment_out(row: AgentServiceAssignment) -> dict:
    return {
        "id": row.id,
        "org_id": row.org_id,
        "service_key": row.service_key,
        "agent_id": row.agent_id,
        "updated_at": row.updated_at,
    }


def _kb_ids_for_generate(db: Session, agent: AgentDefinition | None, file_ids: list[str]) -> list[str]:
    if file_ids:
        return file_ids
    if agent is not None:
        return agent_knowledge_file_ids(db, agent.id)
    return []


def _assignment_out(row: AgentAssignment) -> dict:
    return {"id": row.id, "agent_id": row.agent_id, "org_id": row.org_id, "category_id": row.category_id, "updated_at": row.updated_at}


def _apply_agent_payload(agent: AgentDefinition, payload: dict) -> None:
    if "name" in payload and str(payload.get("name") or "").strip():
        agent.name = str(payload["name"]).strip()
    if "slug" in payload and str(payload.get("slug") or "").strip():
        agent.slug = _slugify(payload["slug"])
    if "description" in payload:
        raw = payload.get("description")
        agent.description = str(raw).strip() if raw is not None and str(raw).strip() else None
    if "system_prompt" in payload:
        raw = str(payload.get("system_prompt") or "").strip()
        if raw:
            agent.system_prompt = raw
    if "call_workflow" in payload:
        raw = payload.get("call_workflow")
        agent.call_workflow = str(raw).strip() if raw is not None and str(raw).strip() else None
    if "is_active" in payload:
        agent.is_active = bool(payload["is_active"])

    text_fields = [
        "voice_label",
        "voice_type_label",
        "accent_region",
        "gender",
        "telnyx_assistant_id",
        "base_role",
        "service_survey_role",
        "service_interview_role",
        "service_lead_sales_role",
        "service_appointment_role",
        "opening_disclosure_template",
        "retry_policy_notes",
        "interruption_behavior_notes",
        "voicemail_behavior",
        "missed_call_email_template_interview",
        "missed_call_email_template_survey",
        "missed_call_followup_notes_interview",
        "opt_out_policy_notes",
        "default_model",
        "default_voice",
    ]
    for key in text_fields:
        if key in payload:
            raw = payload.get(key)
            value = str(raw).strip() if raw is not None and str(raw).strip() else None
            if key == "telnyx_assistant_id" and value:
                from app.services.telnyx_assistant_service import normalize_telnyx_assistant_id

                try:
                    value = normalize_telnyx_assistant_id(value)
                except ValueError:
                    pass
            setattr(agent, key, value)

    bool_fields = [
        "supports_survey",
        "supports_interview",
        "supports_lead_sales",
        "supports_appointment",
        "is_default_survey",
        "is_default_interview",
        "is_default_lead_sales",
        "is_default_appointment",
        "disclosure_for_survey",
        "disclosure_for_interview",
        "disclosure_for_appointment",
        "disclosure_mandatory",
        "allow_lookup_tool",
        "allow_booking_tool",
        "allow_reschedule_tool",
        "allow_cancel_tool",
    ]
    for key in bool_fields:
        if key in payload:
            setattr(agent, key, bool(payload[key]))

    agent.updated_at = datetime.utcnow()


def _generate_payload(body: dict) -> tuple[str, str, list[str], bool]:
    description = str(body.get("description") or "").strip()
    if not description:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="description is required")
    rewrite = bool(body.get("rewrite"))
    file_ids = [str(v).strip() for v in (body.get("knowledge_file_ids") or []) if str(v).strip()]
    agent_name = str(body.get("name") or body.get("agent_name") or "").strip()
    return description, agent_name, file_ids, rewrite


@router.get("")
def list_agents(db: Session = Depends(get_db), _admin=Depends(require_agent_admin)):
    AgentRegistry.ensure_default_agents(db)
    agents = list(db.execute(select(AgentDefinition).order_by(AgentDefinition.created_at.desc())).scalars())
    assignments = list(db.execute(select(AgentAssignment).where(AgentAssignment.org_id.is_not(None))).scalars())
    return {"agents": [_agent_out(db, a) for a in agents], "assignments": [_assignment_out(a) for a in assignments]}


@router.post("")
def create_agent(payload: dict, db: Session = Depends(get_db), _admin=Depends(require_agent_admin)):
    name = str(payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="name is required")
    slug = _slugify(payload.get("slug") or name)
    if db.execute(select(AgentDefinition.id).where(AgentDefinition.slug == slug)).scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Agent slug already exists")
    system_prompt = str(payload.get("system_prompt") or "").strip() or _PENDING_PROMPT
    now = datetime.utcnow()
    agent = AgentDefinition(name=name, slug=slug, system_prompt=system_prompt, created_at=now, updated_at=now)
    _apply_agent_payload(agent, payload)
    for service_key in ("survey", "interview", "lead_sales", "appointments"):
        field = _default_field(service_key)
        if field:
            _clear_other_defaults(db, agent, field)
    db.add(agent)
    db.commit()
    db.refresh(agent)
    file_ids = payload.get("knowledge_file_ids")
    if file_ids is not None:
        set_agent_knowledge_files(db, agent_id=agent.id, file_ids=list(file_ids))
    return _agent_out(db, agent)


@router.get("/services/catalog")
def agent_services_catalog(_admin=Depends(require_agent_admin)):
    return {
        "services": [{"key": key, "label": AGENT_SERVICE_LABELS[key]} for key in AGENT_SERVICE_KEYS],
    }


@router.get("/platform-voice-settings")
def get_platform_voice_settings_route(db: Session = Depends(get_db), _admin=Depends(require_agent_admin)):
    return platform_settings_to_dict(get_platform_voice_settings(db))


@router.put("/platform-voice-settings")
def update_platform_voice_settings_route(
    payload: dict,
    db: Session = Depends(get_db),
    _admin=Depends(require_agent_admin),
):
    return platform_settings_to_dict(update_platform_voice_settings(db, payload))


@router.get("/service-assignments")
def list_agent_service_assignments(
    org_id: str | None = None,
    db: Session = Depends(get_db),
    _admin=Depends(require_agent_admin),
):
    query = select(AgentServiceAssignment)
    if org_id:
        query = query.where(AgentServiceAssignment.org_id == org_id)
    rows = list(db.execute(query.order_by(AgentServiceAssignment.org_id, AgentServiceAssignment.service_key)).scalars())
    return {"assignments": [_service_assignment_out(r) for r in rows]}


@router.put("/service-assignments/organisation/{org_id}/{service_key}")
def set_agent_service_assignment(
    org_id: str,
    service_key: str,
    payload: dict,
    db: Session = Depends(get_db),
    _admin=Depends(require_agent_admin),
):
    if not db.execute(select(Organisation.id).where(Organisation.id == org_id)).scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    try:
        key = normalize_service_key(service_key)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    agent_id = str(payload.get("agent_id") or "").strip()
    if not db.execute(select(AgentDefinition.id).where(AgentDefinition.id == agent_id)).scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Agent required")
    row = db.execute(
        select(AgentServiceAssignment).where(
            AgentServiceAssignment.org_id == org_id,
            AgentServiceAssignment.service_key == key,
        )
    ).scalar_one_or_none()
    if row is None:
        row = AgentServiceAssignment(org_id=org_id, service_key=key, agent_id=agent_id)
    else:
        row.agent_id = agent_id
    row.updated_at = datetime.utcnow()
    db.add(row)
    db.commit()
    db.refresh(row)
    return _service_assignment_out(row)


@router.delete("/service-assignments/{assignment_id}")
def delete_agent_service_assignment(
    assignment_id: str,
    db: Session = Depends(get_db),
    _admin=Depends(require_agent_admin),
):
    row = db.execute(select(AgentServiceAssignment).where(AgentServiceAssignment.id == assignment_id)).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service assignment not found")
    removed = _service_assignment_out(row)
    db.delete(row)
    db.commit()
    return {"ok": True, "removed_assignment": removed}


@router.post("/generate-workflow")
def generate_workflow_draft(payload: dict, db: Session = Depends(get_db), _admin=Depends(require_agent_admin)):
    description, agent_name, file_ids, rewrite = _generate_payload(payload)
    files = get_kb_files_by_ids(db, file_ids)
    if str(payload.get("call_workflow") or "").strip() and not rewrite:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Workflow already exists. Send rewrite=true to replace.",
        )
    try:
        return generate_call_workflow(db, agent_name=agent_name or "New agent", description=description, knowledge_files=files)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e


@router.post("/{agent_id}/generate-workflow")
def generate_workflow_for_agent(
    agent_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    _admin=Depends(require_agent_admin),
):
    agent = db.execute(select(AgentDefinition).where(AgentDefinition.id == agent_id)).scalar_one_or_none()
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    description, agent_name, file_ids, rewrite = _generate_payload(payload)
    if not agent_name:
        agent_name = agent.name
    kb_ids = _kb_ids_for_generate(db, agent, file_ids)
    if str(agent.call_workflow or "").strip() and not rewrite:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Workflow already exists. Send rewrite=true to replace.",
        )
    files = get_kb_files_by_ids(db, kb_ids)
    try:
        return generate_call_workflow(
            db,
            agent_name=agent_name,
            description=description,
            knowledge_files=files,
            agent=agent,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e


@router.post("/generate-prompt")
def generate_prompt_draft(payload: dict, db: Session = Depends(get_db), _admin=Depends(require_agent_admin)):
    description, agent_name, file_ids, _rewrite = _generate_payload(payload)
    workflow = str(payload.get("call_workflow") or "").strip()
    if not workflow:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="call_workflow is required — generate workflow first")
    files = get_kb_files_by_ids(db, file_ids)
    try:
        return generate_system_prompt(
            db,
            agent_name=agent_name or "New agent",
            description=description,
            knowledge_files=files,
            call_workflow=workflow,
            arabic_fusha=bool(payload.get("arabic_fusha")) or None,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e


@router.post("/generate-prompt-legacy")
def generate_prompt_draft_legacy(payload: dict, db: Session = Depends(get_db), _admin=Depends(require_agent_admin)):
    description, agent_name, file_ids, _rewrite = _generate_payload(payload)
    files = get_kb_files_by_ids(db, file_ids)
    try:
        generated = generate_agent_prompts(db, agent_name=agent_name or "New agent", description=description, knowledge_files=files)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e
    return generated


@router.get("/{agent_id}")
def get_agent(agent_id: str, db: Session = Depends(get_db), _admin=Depends(require_agent_admin)):
    agent = db.execute(select(AgentDefinition).where(AgentDefinition.id == agent_id)).scalar_one_or_none()
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    return _agent_out(db, agent)


@router.put("/{agent_id}")
def update_agent(agent_id: str, payload: dict, db: Session = Depends(get_db), _admin=Depends(require_agent_admin)):
    agent = db.execute(select(AgentDefinition).where(AgentDefinition.id == agent_id)).scalar_one_or_none()
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    if "slug" in payload:
        slug = _slugify(payload["slug"])
        clash = db.execute(select(AgentDefinition.id).where(AgentDefinition.slug == slug, AgentDefinition.id != agent_id)).scalar_one_or_none()
        if clash:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Agent slug already exists")
    _apply_agent_payload(agent, payload)
    for service_key in ("survey", "interview", "lead_sales", "appointments"):
        field = _default_field(service_key)
        if field:
            _clear_other_defaults(db, agent, field)
    db.add(agent)
    db.commit()
    db.refresh(agent)
    if "knowledge_file_ids" in payload:
        set_agent_knowledge_files(db, agent_id=agent.id, file_ids=list(payload.get("knowledge_file_ids") or []))
    return _agent_out(db, agent)


@router.post("/{agent_id}/generate-prompt")
def generate_prompt_for_agent(agent_id: str, payload: dict, db: Session = Depends(get_db), _admin=Depends(require_agent_admin)):
    agent = db.execute(select(AgentDefinition).where(AgentDefinition.id == agent_id)).scalar_one_or_none()
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")

    description, agent_name, file_ids, rewrite = _generate_payload(payload)
    if not agent_name:
        agent_name = agent.name

    workflow = str(payload.get("call_workflow") or agent.call_workflow or "").strip()
    if not workflow:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="call_workflow is required — generate workflow first")

    kb_ids = _kb_ids_for_generate(db, agent, file_ids)
    files = get_kb_files_by_ids(db, kb_ids)
    try:
        return generate_system_prompt(
            db,
            agent_name=agent_name,
            description=description,
            knowledge_files=files,
            call_workflow=workflow,
            agent=agent,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e


@router.post("/{agent_id}/refresh-kb-context")
def refresh_kb_context_endpoint(agent_id: str, db: Session = Depends(get_db), _admin=Depends(require_agent_admin)):
    if not db.execute(select(AgentDefinition.id).where(AgentDefinition.id == agent_id)).scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    context = refresh_agent_kb_context(db, agent_id)
    return {"ok": True, "kb_context_cached": bool(context)}


@router.put("/assignments/business-type/{category_id}")
def assign_business_type_agent(category_id: str, payload: dict, db: Session = Depends(get_db), _admin=Depends(require_agent_admin)):
    if not db.execute(select(Category.id).where(Category.id == category_id)).scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
    agent_id = str(payload.get("agent_id") or "").strip()
    if not db.execute(select(AgentDefinition.id).where(AgentDefinition.id == agent_id)).scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Agent required")
    row = db.execute(select(AgentAssignment).where(AgentAssignment.category_id == category_id)).scalar_one_or_none()
    if row is None:
        row = AgentAssignment(category_id=category_id, agent_id=agent_id)
    row.agent_id = agent_id
    row.updated_at = datetime.utcnow()
    db.add(row)
    db.commit()
    db.refresh(row)
    return _assignment_out(row)


@router.post("/{agent_id}/test-webrtc")
def test_agent_webrtc(
    agent_id: str,
    payload: dict | None = None,
    db: Session = Depends(get_db),
    _admin=Depends(require_agent_admin),
):
    """Sync agent prompt to Telnyx and return WebRTC connect payload for a browser test call."""
    from app.core.agent_services import SERVICE_INTERVIEW, SERVICE_SURVEY, normalize_service_key
    from app.models.service_order import ServiceOrder, ServiceOrderRecipient
    from app.services.telnyx_assistant_service import normalize_telnyx_assistant_id, prepare_telnyx_webrtc_call
    from app.services.voice_agent_runtime import (
        build_service_opening_greeting,
        build_service_runtime_instructions,
        detect_interview_language,
    )

    payload = payload or {}
    agent = db.execute(select(AgentDefinition).where(AgentDefinition.id == agent_id)).scalar_one_or_none()
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    assistant_raw = str(agent.telnyx_assistant_id or "").strip()
    if not assistant_raw:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Telnyx Assistant ID is required")
    assistant_id = normalize_telnyx_assistant_id(assistant_raw)
    system_prompt = str(agent.system_prompt or "").strip()
    if not system_prompt or system_prompt.lower().startswith("(not configured"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="System prompt is required before testing")

    org_id = str(payload.get("org_id") or "").strip()
    if not org_id:
        org_id = db.execute(select(Organisation.id).order_by(Organisation.created_at.asc()).limit(1)).scalar_one_or_none() or ""
    org_name = ""
    if org_id:
        org = db.get(Organisation, org_id)
        org_name = str(org.name or "").strip() if org else ""

    service_raw = str(payload.get("service_key") or "").strip()
    service_key = normalize_service_key(service_raw) if service_raw else ""
    if not service_key:
        service_key = SERVICE_INTERVIEW if agent.supports_interview else SERVICE_SURVEY

    test_script = str(payload.get("test_script") or "").strip()
    default_script = (
        "OPENING\n"
        "Greet the candidate and confirm they can hear you.\n\n"
        "QUESTIONS\n"
        "1. Tell me briefly about your background.\n"
        "2. Why are you interested in this role?\n"
    )
    config: dict = {
        "approved_script": test_script or default_script,
        "role": str(payload.get("role") or "Test interview").strip(),
        "company_name": str(payload.get("company_name") or org_name or "VoxBulk").strip(),
        "organiser_name": str(payload.get("organiser_name") or org_name or "VoxBulk").strip(),
    }
    candidate_name = str(payload.get("candidate_first_name") or payload.get("candidate_name") or "Test User").strip()

    order = ServiceOrder(org_id=org_id or None, title=config["role"], service_code="interview")
    recipient = ServiceOrderRecipient(name=candidate_name)

    refresh_agent_kb_context(db, agent_id)

    instructions = build_service_runtime_instructions(
        db,
        order=order,
        config=config,
        recipient=recipient,
        agent=agent,
        service_key=service_key,
    )
    greeting = build_service_opening_greeting(
        db,
        agent=agent,
        config=config,
        recipient_name=candidate_name,
        service_key=service_key,
        org_id=org_id or None,
        order=order,
    )
    language = detect_interview_language(config, agent)

    try:
        prep = prepare_telnyx_webrtc_call(
            db,
            assistant_id,
            instructions,
            greeting=greeting or None,
            language=language,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    custom_headers = [
        {"name": "X-Agent-Test", "value": "true"},
        {"name": "X-Agent-Definition-Id", "value": str(agent.id)},
    ]
    return {
        "ok": True,
        "agent_id": prep.get("assistant_id") or assistant_id,
        "greeting": greeting,
        "custom_headers": custom_headers,
        "web_calls_enabled": bool(prep.get("web_calls_enabled")),
        "prompt_synced": bool(prep.get("prompt_synced")),
        "language": language,
    }


@router.post("/preview")
def preview_agent(payload: dict, db: Session = Depends(get_db), _admin=Depends(require_agent_admin)):
    org_id = str(payload.get("org_id") or "").strip()
    if not org_id:
        org_id = db.execute(select(Organisation.id).order_by(Organisation.created_at.asc()).limit(1)).scalar_one_or_none() or ""
    if not org_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="org_id required when no organisations exist")
    latest = str(payload.get("input") or payload.get("latest_user_utterance") or "").strip()
    if not latest:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="input required")
    try:
        result = AgentManager.handle_turn(
            db,
            AgentRunRequest(
                context=AgentRuntimeContext(org_id=org_id, user_id=None, agent_id=(payload.get("agent_id") or None), workflow_type="preview"),
                latest_user_utterance=latest,
                agent_id=(payload.get("agent_id") or None),
            ),
            synthesize_audio=bool(payload.get("synthesize_audio", False)),
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return {
        "agent_id": result.agent_id,
        "agent_slug": result.agent_slug,
        "assistant_text": result.assistant_text,
        "tool_calls": [t.__dict__ for t in result.tool_calls],
        "usage": result.usage,
    }


@router.delete("/{agent_id}")
def delete_agent(agent_id: str, db: Session = Depends(get_db), _admin=Depends(require_agent_admin)):
    agent = db.execute(select(AgentDefinition).where(AgentDefinition.id == agent_id)).scalar_one_or_none()
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    from app.models.agent_knowledge_file import AgentKnowledgeFile

    db.execute(delete(AgentKnowledgeFile).where(AgentKnowledgeFile.agent_id == agent_id))
    db.execute(delete(AgentAssignment).where(AgentAssignment.agent_id == agent_id))
    db.execute(delete(AgentServiceAssignment).where(AgentServiceAssignment.agent_id == agent_id))
    db.delete(agent)
    db.commit()
    return {"ok": True, "deleted_agent_id": agent_id}


@router.post("/{agent_id}/activate")
def activate_agent(agent_id: str, db: Session = Depends(get_db), _admin=Depends(require_agent_admin)):
    return update_agent(agent_id, {"is_active": True}, db, _admin)


@router.post("/{agent_id}/deactivate")
def deactivate_agent(agent_id: str, db: Session = Depends(get_db), _admin=Depends(require_agent_admin)):
    return update_agent(agent_id, {"is_active": False}, db, _admin)


@router.delete("/assignments/{assignment_id}")
def remove_agent_assignment(assignment_id: str, db: Session = Depends(get_db), _admin=Depends(require_agent_admin)):
    row = db.execute(select(AgentAssignment).where(AgentAssignment.id == assignment_id)).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent assignment not found")
    removed = _assignment_out(row)
    db.delete(row)
    db.commit()
    return {"ok": True, "removed_assignment": removed}


@router.put("/{agent_id}/organisation-assignments")
def set_agent_organisation_assignments(agent_id: str, payload: dict, db: Session = Depends(get_db), _admin=Depends(require_agent_admin)):
    if not db.execute(select(AgentDefinition.id).where(AgentDefinition.id == agent_id)).scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    org_ids = [str(v).strip() for v in (payload.get("org_ids") or []) if str(v).strip()]
    org_ids = list(dict.fromkeys(org_ids))
    if org_ids:
        existing_orgs = set(db.execute(select(Organisation.id).where(Organisation.id.in_(org_ids))).scalars())
        missing = [org_id for org_id in org_ids if org_id not in existing_orgs]
        if missing:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"message": "Some organisations were not found", "missing_org_ids": missing})
    db.execute(delete(AgentAssignment).where(AgentAssignment.agent_id == agent_id, AgentAssignment.org_id.is_not(None)))
    rows: list[AgentAssignment] = []
    for org_id in org_ids:
        row = db.execute(select(AgentAssignment).where(AgentAssignment.org_id == org_id)).scalar_one_or_none()
        if row is None:
            row = AgentAssignment(org_id=org_id, agent_id=agent_id)
        row.agent_id = agent_id
        row.updated_at = datetime.utcnow()
        db.add(row)
        rows.append(row)
    db.commit()
    for row in rows:
        db.refresh(row)
    return {"ok": True, "agent_id": agent_id, "assignments": [_assignment_out(row) for row in rows]}


@router.put("/assignments/organisation/{org_id}")
def assign_organisation_agent(org_id: str, payload: dict, db: Session = Depends(get_db), _admin=Depends(require_agent_admin)):
    if not db.execute(select(Organisation.id).where(Organisation.id == org_id)).scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    agent_id = str(payload.get("agent_id") or "").strip()
    if not db.execute(select(AgentDefinition.id).where(AgentDefinition.id == agent_id)).scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Agent required")
    row = db.execute(select(AgentAssignment).where(AgentAssignment.org_id == org_id)).scalar_one_or_none()
    if row is None:
        row = AgentAssignment(org_id=org_id, agent_id=agent_id)
    row.agent_id = agent_id
    row.updated_at = datetime.utcnow()
    db.add(row)
    db.commit()
    db.refresh(row)
    return _assignment_out(row)
