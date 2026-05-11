from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.admin_rbac import require_platform_admin, resolve_admin_role
from app.core.database import get_db
from app.models.agent import AgentAssignment, AgentDefinition
from app.models.category import Category
from app.models.organisation import Organisation
from app.models.user import User
from app.services.agents.base import AgentRunRequest, AgentRuntimeContext
from app.services.agents.manager import AgentManager
from app.services.agents.registry import AgentRegistry

router = APIRouter(prefix="/admin/agents", tags=["admin-agents"])


def require_agent_admin(user: User = Depends(require_platform_admin), db: Session = Depends(get_db)) -> User:
    role = resolve_admin_role(db, user)
    if role in {"superadmin", "technical"}:
        return user
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Agent management requires superadmin or technical admin")


def _slugify(raw: str) -> str:
    s = "".join(ch.lower() if ch.isalnum() else "-" for ch in str(raw or "").strip())
    while "--" in s:
        s = s.replace("--", "-")
    return s.strip("-") or "agent"


def _agent_out(agent: AgentDefinition) -> dict:
    return {
        "id": agent.id,
        "name": agent.name,
        "slug": agent.slug,
        "business_type": agent.business_type,
        "category_id": agent.category_id,
        "description": agent.description,
        "system_prompt": agent.system_prompt,
        "conversation_style": agent.conversation_style,
        "default_model": agent.default_model,
        "default_voice": agent.default_voice,
        "use_azure_tts": bool(agent.use_azure_tts),
        "use_azure_stt": bool(agent.use_azure_stt),
        "allow_booking_tool": bool(agent.allow_booking_tool),
        "allow_lookup_tool": bool(agent.allow_lookup_tool),
        "allow_reschedule_tool": bool(agent.allow_reschedule_tool),
        "allow_cancel_tool": bool(agent.allow_cancel_tool),
        "is_active": bool(agent.is_active),
        "is_template": bool(agent.is_template),
        "created_at": agent.created_at,
        "updated_at": agent.updated_at,
    }


def _assignment_out(row: AgentAssignment) -> dict:
    return {"id": row.id, "agent_id": row.agent_id, "org_id": row.org_id, "category_id": row.category_id, "updated_at": row.updated_at}


@router.get("")
def list_agents(db: Session = Depends(get_db), _admin=Depends(require_agent_admin)):
    AgentRegistry.ensure_default_agents(db)
    agents = list(db.execute(select(AgentDefinition).order_by(AgentDefinition.created_at.desc())).scalars())
    assignments = list(db.execute(select(AgentAssignment)).scalars())
    return {"agents": [_agent_out(a) for a in agents], "assignments": [_assignment_out(a) for a in assignments]}


@router.post("")
def create_agent(payload: dict, db: Session = Depends(get_db), _admin=Depends(require_agent_admin)):
    name = str(payload.get("name") or "").strip()
    system_prompt = str(payload.get("system_prompt") or "").strip()
    if not name or not system_prompt:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="name and system_prompt are required")
    slug = _slugify(payload.get("slug") or name)
    if db.execute(select(AgentDefinition.id).where(AgentDefinition.slug == slug)).scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Agent slug already exists")
    now = datetime.utcnow()
    agent = AgentDefinition(name=name, slug=slug, system_prompt=system_prompt, created_at=now, updated_at=now)
    _apply_agent_payload(agent, payload)
    db.add(agent)
    db.commit()
    db.refresh(agent)
    return _agent_out(agent)


def _apply_agent_payload(agent: AgentDefinition, payload: dict) -> None:
    for key in ["business_type", "category_id", "description", "conversation_style", "default_model", "default_voice"]:
        if key in payload:
            raw = payload.get(key)
            setattr(agent, key, str(raw).strip() if raw is not None and str(raw).strip() else None)
    if "name" in payload and str(payload.get("name") or "").strip():
        agent.name = str(payload["name"]).strip()
    if "slug" in payload and str(payload.get("slug") or "").strip():
        agent.slug = _slugify(payload["slug"])
    if "system_prompt" in payload and str(payload.get("system_prompt") or "").strip():
        agent.system_prompt = str(payload["system_prompt"]).strip()
    for key in [
        "use_azure_tts",
        "use_azure_stt",
        "allow_booking_tool",
        "allow_lookup_tool",
        "allow_reschedule_tool",
        "allow_cancel_tool",
        "is_active",
        "is_template",
    ]:
        if key in payload:
            setattr(agent, key, bool(payload[key]))
    agent.updated_at = datetime.utcnow()


@router.get("/{agent_id}")
def get_agent(agent_id: str, db: Session = Depends(get_db), _admin=Depends(require_agent_admin)):
    agent = db.execute(select(AgentDefinition).where(AgentDefinition.id == agent_id)).scalar_one_or_none()
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    return _agent_out(agent)


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
    db.add(agent)
    db.commit()
    db.refresh(agent)
    return _agent_out(agent)


@router.delete("/{agent_id}")
def delete_agent(agent_id: str, db: Session = Depends(get_db), _admin=Depends(require_agent_admin)):
    agent = db.execute(select(AgentDefinition).where(AgentDefinition.id == agent_id)).scalar_one_or_none()
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    db.execute(delete(AgentAssignment).where(AgentAssignment.agent_id == agent_id))
    db.delete(agent)
    db.commit()
    return {"ok": True, "deleted_agent_id": agent_id}


@router.post("/{agent_id}/activate")
def activate_agent(agent_id: str, db: Session = Depends(get_db), _admin=Depends(require_agent_admin)):
    return update_agent(agent_id, {"is_active": True}, db, _admin)


@router.post("/{agent_id}/deactivate")
def deactivate_agent(agent_id: str, db: Session = Depends(get_db), _admin=Depends(require_agent_admin)):
    return update_agent(agent_id, {"is_active": False}, db, _admin)


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


@router.delete("/assignments/organisation/{org_id}")
def remove_organisation_agent(org_id: str, db: Session = Depends(get_db), _admin=Depends(require_agent_admin)):
    row = db.execute(select(AgentAssignment).where(AgentAssignment.org_id == org_id)).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation assignment not found")
    db.delete(row)
    db.commit()
    return {"ok": True, "removed_org_id": org_id}


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
    if len(set(org_ids)) != len(org_ids):
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
                context=AgentRuntimeContext(org_id=org_id, user_id=None, agent_id=(payload.get("agent_id") or None), workflow_type=str(payload.get("workflow_type") or "preview")),
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
