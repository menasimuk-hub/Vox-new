from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_principal
from app.models.agent import AgentDefinition
from app.services.onboarding_service import OrganisationOnboardingService
from app.services.recovery_service import OrganisationService
from app.services.service_script_generator import generate_interview_script, generate_survey_script

router = APIRouter(prefix="/dashboard/service-scripts", tags=["dashboard-service-scripts"])


def _pick_org_name(ctx: dict, identity: dict, org) -> str:
    candidates = [
        str(ctx.get("organisation_name") or "").strip(),
        str(identity.get("organisation_name") or "").strip(),
        str(org.name if org else "").strip(),
        str(org.contact_name if org else "").strip(),
    ]
    for name in candidates:
        if name and "voxbulk" not in name.lower() and "retover" not in name.lower():
            return name
    return candidates[0] or "Your business"


def _client_branding(db: Session, org_id: str, payload: dict) -> dict:
    ctx = payload.get("client_context") if isinstance(payload.get("client_context"), dict) else {}
    org = OrganisationService.get_org(db, org_id)
    ai_cfg = OrganisationOnboardingService.ai_config(db, org_id)
    identity = ai_cfg.get("ai_identity") or {}
    
    # Client name is the customer/clinic calling on behalf of
    client_name = _pick_org_name(ctx, identity, org)
    org_name = "Voxbulk"

    agent_id = str(ctx.get("agent_id") or payload.get("agent_id") or "").strip()
    agent_name = ""
    if agent_id:
        agent = db.get(AgentDefinition, agent_id)
        if agent:
            agent_name = str(agent.name or agent.voice_label or "").strip()

    organiser = str(
        agent_name
        or ctx.get("survey_organiser_name")
        or ctx.get("contact_name")
        or (org.contact_name if org else "")
        or identity.get("assistant_name")
        or client_name
    ).strip()
    if "voxbulk" in organiser.lower():
        organiser = client_name
    assistant = str(ctx.get("assistant_name") or ctx.get("survey_organiser_name") or identity.get("assistant_name") or organiser).strip()
    if "voxbulk" in assistant.lower():
        assistant = organiser or client_name
    return {
        "organisation_name": org_name,
        "client_name": client_name,
        "assistant_name": assistant or organiser,
        "organiser_name": organiser or client_name,
        "terminology_label": str(ctx.get("terminology_label") or identity.get("terminology_label") or "customer").strip() or "customer",
        "contact_name": organiser,
    }


@router.post("/generate")
def generate_service_script(payload: dict, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    service_code = str(payload.get("service_code") or "").strip().lower()
    if service_code not in {"survey", "interview"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="service_code must be survey or interview")
    try:
        branding = _client_branding(db, principal.org_id, payload)
        if service_code == "survey":
            result = generate_survey_script(
                db,
                goal=str(payload.get("goal") or ""),
                contact_method=str(payload.get("contact_method") or "AI phone call"),
                max_call_length=str(payload.get("max_call_length") or "3 minutes"),
                organisation_name=branding["organisation_name"],
                assistant_name=branding["assistant_name"],
                organiser_name=branding["organiser_name"],
                client_name=branding.get("client_name", ""),
                terminology_label=branding["terminology_label"],
            )
        else:
            result = generate_interview_script(
                db,
                role=str(payload.get("role") or ""),
                criteria=str(payload.get("criteria") or ""),
                delivery=str(payload.get("delivery") or "ai_call"),
                organisation_name=branding["organisation_name"],
                assistant_name=branding["assistant_name"],
                organiser_name=branding["organiser_name"],
                client_name=branding.get("client_name", ""),
            )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"AI script generation failed: {e}") from e
    return {"ok": True, "service_code": service_code, **result}
