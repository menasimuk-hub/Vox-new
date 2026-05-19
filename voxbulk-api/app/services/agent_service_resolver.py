from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.agent_services import normalize_service_key
from app.models.agent import AgentDefinition
from app.models.agent_service_assignment import AgentServiceAssignment


def resolve_agent_for_org_service(
    db: Session,
    *,
    org_id: str,
    service_key: str,
    require_active: bool = True,
) -> AgentDefinition | None:
    if not org_id:
        return None
    key = normalize_service_key(service_key)
    row = db.execute(
        select(AgentServiceAssignment).where(
            AgentServiceAssignment.org_id == org_id,
            AgentServiceAssignment.service_key == key,
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    agent = db.execute(select(AgentDefinition).where(AgentDefinition.id == row.agent_id)).scalar_one_or_none()
    if agent is None:
        return None
    if require_active and not agent.is_active:
        return None
    return agent


def list_service_assignments_for_org(db: Session, org_id: str) -> list[AgentServiceAssignment]:
    return list(
        db.execute(
            select(AgentServiceAssignment)
            .where(AgentServiceAssignment.org_id == org_id)
            .order_by(AgentServiceAssignment.service_key.asc())
        ).scalars()
    )
