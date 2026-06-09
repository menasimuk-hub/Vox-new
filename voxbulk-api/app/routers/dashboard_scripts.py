from __future__ import annotations

import logging
import traceback

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

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
    agent = db.get(AgentDefinition, agent_id) if agent_id else None
    agent_name = ""
    if agent:
        agent_name = str(agent.name or agent.voice_label or "").strip()

    # Always use agent name if provided, otherwise fall back to configured organiser
    if agent_name:
        organiser = agent_name
        assistant = agent_name
    else:
        organiser = str(
            ctx.get("survey_organiser_name")
            or ctx.get("contact_name")
            or (org.contact_name if org else "")
            or identity.get("assistant_name")
            or client_name
        ).strip()
        assistant = str(ctx.get("assistant_name") or ctx.get("survey_organiser_name") or identity.get("assistant_name") or organiser).strip()
    
    # Clean up any platform brand names
    if "voxbulk" in organiser.lower():
        organiser = client_name
    if "voxbulk" in assistant.lower():
        assistant = organiser or client_name
    
    return {
        "organisation_name": org_name,
        "client_name": client_name,
        "assistant_name": assistant or organiser,
        "organiser_name": organiser or client_name,
        "terminology_label": str(ctx.get("terminology_label") or identity.get("terminology_label") or "customer").strip() or "customer",
        "contact_name": organiser,
        "agent": agent,
        "agent_id": agent_id,
        "order_config": ctx,
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
                max_call_length=str(payload.get("max_call_length") or "4 minutes"),
                organisation_name=branding["organisation_name"],
                assistant_name=branding["assistant_name"],
                organiser_name=branding["organiser_name"],
                client_name=branding.get("client_name", ""),
                terminology_label=branding["terminology_label"],
                agent=branding.get("agent"),
                org_id=principal.org_id,
                order_config=branding.get("order_config"),
            )
        else:
            if not str(payload.get("criteria") or "").strip():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Add screening criteria before generating the AI script",
                )
            if not str(payload.get("role") or payload.get("position") or "").strip():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Enter the position / role before generating the AI script",
                )
            result = generate_interview_script(
                db,
                role=str(payload.get("role") or payload.get("position") or ""),
                criteria=str(payload.get("criteria") or ""),
                delivery=str(payload.get("delivery") or "ai_call"),
                organisation_name=branding["organisation_name"],
                assistant_name=branding["assistant_name"],
                organiser_name=branding["organiser_name"],
                client_name=branding.get("client_name", ""),
                agent=branding.get("agent"),
                org_id=principal.org_id,
                order_config=branding.get("order_config"),
            )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"AI script generation failed: {e}") from e
    return {"ok": True, "service_code": service_code, **result}


@router.get("/wa-survey/industries")
def list_wa_survey_industries(db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    from app.services.industry_service import IndustryService

    return {"ok": True, "industries": IndustryService.list_industries(db)}


@router.get("/wa-survey/types")
def list_wa_survey_types(
    industry_id: str | None = None,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    from app.services.survey_type_service import SurveyTypeService

    types = [
        t
        for t in SurveyTypeService.list_types(db, industry_id=industry_id)
        if t.get("is_active") and not t.get("system_template_kind")
    ]
    return {"ok": True, "types": types}


@router.get("/wa-survey/system-templates")
def list_wa_survey_system_templates(
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    from app.services.survey_system_template_service import SurveySystemTemplateService

    return SurveySystemTemplateService.list_templates_for_builder(db)


@router.post("/wa-survey/validate-builder")
def validate_wa_survey_builder(
    payload: dict,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    from app.services.survey_builder_validation_service import (
        SurveyBuilderValidationError,
        SurveyBuilderValidationService,
    )

    body = payload or {}
    try:
        return SurveyBuilderValidationService.validate_builder_selection(
            db,
            industry_id=str(body.get("industry_id") or ""),
            selected_survey_type_ids=body.get("selected_survey_type_ids") or body.get("service_tag_ids") or [],
            welcome_template_id=body.get("welcome_template_id"),
            thank_you_template_id=body.get("thank_you_template_id"),
            selected_service_template_ids=body.get("selected_service_template_ids"),
            selected_middle_template_ids=body.get("selected_middle_template_ids"),
            require_approved=bool(body.get("require_approved")),
            privacy_mode=body.get("privacy_mode"),
            anonymous_responses=bool(body.get("anonymous_responses")),
        )
    except SurveyBuilderValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"message": str(e), "errors": e.errors}) from e


@router.get("/wa-survey/types/{survey_type_id}/step-bank")
def get_wa_survey_step_bank(
    survey_type_id: str,
    variant: str = "standard",
    privacy_mode: str | None = None,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    from app.services.survey_step_bank_service import SurveyStepBankService
    from app.services.survey_type_service import SurveyTypeService

    survey_type = SurveyTypeService.get_type(db, survey_type_id)
    if survey_type is None or not survey_type.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Survey type not found")
    return SurveyStepBankService.get_bank(
        db,
        survey_type=survey_type,
        variant=variant,
        privacy_mode=privacy_mode,
    )


@router.get("/wa-survey/types/{survey_type_id}/library-templates")
def list_wa_survey_library_templates(
    survey_type_id: str,
    privacy_mode: str | None = None,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    """Middle-step library templates linked to a survey type (dashboard builder Step 3)."""
    from app.services.survey_step_bank_service import MIDDLE_STEP_ROLES, normalize_step_role
    from app.services.survey_type_service import SurveyTypeService
    from app.services.survey_whatsapp_template_service import SurveyWhatsappTemplateService

    survey_type = SurveyTypeService.get_type(db, survey_type_id)
    if survey_type is None or not survey_type.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Survey type not found")
    rows = SurveyWhatsappTemplateService.list_for_survey_type(
        db,
        survey_type_id,
        privacy_mode=privacy_mode,
    )
    middle_roles = set(MIDDLE_STEP_ROLES)
    templates = [
        row
        for row in rows
        if normalize_step_role(str(row.get("step_role") or "")) in middle_roles
    ]
    if not templates:
        templates = [
            row
            for row in rows
            if normalize_step_role(str(row.get("step_role") or "")) not in {"start", "completion"}
        ]
    return {"ok": True, "survey_type_id": survey_type_id, "templates": templates}


@router.post("/wa-survey/generate")
def generate_wa_survey(payload: dict, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    from app.services.survey_builder_validation_service import (
        SurveyBuilderValidationError,
        SurveyBuilderValidationService,
    )
    from app.services.survey_generation_service import SurveyGenerationService
    from app.utils.json_safe import json_safe

    body = payload or {}
    logger.info(
        "generate_wa_survey entry org=%s user=%s keys=%s survey_type_id=%s welcome=%s thank_you=%s",
        principal.org_id,
        principal.user_id,
        sorted(body.keys()),
        body.get("survey_type_id"),
        body.get("welcome_template_id"),
        body.get("thank_you_template_id"),
    )
    try:
        branding = _client_branding(db, principal.org_id, body)
        page_count = body.get("page_count")
        selected = body.get("selected_step_roles")
        selected_type_ids = body.get("selected_survey_type_ids") or body.get("service_tag_ids")
        welcome_template_id = body.get("welcome_template_id")
        thank_you_template_id = body.get("thank_you_template_id")
        primary_survey_type_id = str(body.get("survey_type_id") or "")
        builder_config: dict | None = None
        if selected_type_ids or welcome_template_id or thank_you_template_id:
            builder_config = SurveyBuilderValidationService.validate_builder_selection(
                db,
                industry_id=str(body.get("industry_id") or ""),
                selected_survey_type_ids=selected_type_ids or ([primary_survey_type_id] if primary_survey_type_id else []),
                welcome_template_id=welcome_template_id,
                thank_you_template_id=thank_you_template_id,
                selected_service_template_ids=body.get("selected_service_template_ids"),
                selected_middle_template_ids=body.get("selected_middle_template_ids"),
                require_approved=False,
                allow_final_additional_feedback=bool(body.get("allow_final_additional_feedback", False)),
                privacy_mode=body.get("privacy_mode"),
                anonymous_responses=bool(body.get("anonymous_responses")),
            )
            primary_survey_type_id = str(builder_config.get("primary_survey_type_id") or primary_survey_type_id)
            type_ids = list(builder_config.get("selected_survey_type_ids") or [])
            if body.get("selected_middle_template_ids"):
                pairs = SurveyBuilderValidationService.parse_middle_template_pairs(
                    type_ids,
                    body.get("selected_middle_template_ids"),
                )
                if pairs:
                    builder_config["ordered_middle_template_ids"] = [tpl_id for _, tpl_id in pairs]
                    builder_config["builder_page_count"] = len(pairs) + 2
            elif body.get("selected_service_template_ids") and not builder_config.get("ordered_middle_template_ids"):
                pairs = SurveyBuilderValidationService.parse_middle_template_pairs(
                    type_ids,
                    body.get("selected_service_template_ids"),
                )
                if pairs:
                    builder_config["ordered_middle_template_ids"] = [tpl_id for _, tpl_id in pairs]
                    builder_config["builder_page_count"] = len(pairs) + 2
        parsed_page_count: int | None = None
        if page_count is not None:
            try:
                parsed_page_count = int(page_count)
            except (TypeError, ValueError) as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="page_count must be an integer",
                ) from e
        logger.info(
            "generate_wa_survey service_call survey_type=%s page_count=%s middle_ids=%s",
            primary_survey_type_id,
            parsed_page_count,
            (builder_config or {}).get("ordered_middle_template_ids"),
        )
        result = SurveyGenerationService.generate(
            db,
            survey_type_id=primary_survey_type_id,
            variant=str(body.get("variant") or "standard"),
            privacy_mode=str(body.get("privacy_mode") or "").strip() or None,
            length=str(body.get("length") or "standard"),
            page_count=parsed_page_count,
            auto_select_steps=bool(body.get("auto_select_steps", True)),
            selected_step_roles=[str(r) for r in selected] if isinstance(selected, list) else None,
            goal=str(body.get("goal") or ""),
            organisation_name=branding["organisation_name"],
            client_name=branding.get("client_name") or branding["organisation_name"],
            assistant_name=branding.get("assistant_name") or "",
            organiser_name=branding.get("organiser_name") or "",
            builder_config=builder_config,
            allow_unapproved_templates=True,
        )
        safe = json_safe(result)
        logger.info("generate_wa_survey ok page_count=%s wa_template_id=%s", safe.get("page_count"), safe.get("wa_template_id"))
        return safe
    except SurveyBuilderValidationError as e:
        logger.warning("generate_wa_survey validation failed: %s", e.errors)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": str(e), "errors": e.errors},
        ) from e
    except ValueError as e:
        logger.warning("generate_wa_survey value_error: %s", e)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("generate_wa_survey failed")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Survey generation failed: {type(e).__name__}: {e}",
        ) from e


def _parse_wa_survey_test_template_ids(body: dict) -> list[int]:
    raw_ids = body.get("template_ids")
    if isinstance(raw_ids, list) and raw_ids:
        parsed: list[int] = []
        for item in raw_ids:
            try:
                tid = int(item)
            except (TypeError, ValueError):
                continue
            if tid > 0 and tid not in parsed:
                parsed.append(tid)
        return parsed

    ordered: list[int] = []
    welcome_raw = body.get("welcome_template_id") or body.get("wa_template_id")
    if welcome_raw is not None and str(welcome_raw).strip():
        try:
            ordered.append(int(welcome_raw))
        except (TypeError, ValueError):
            pass

    middle_raw = body.get("middle_template_ids") or body.get("selected_middle_template_ids")
    if isinstance(middle_raw, list):
        for item in middle_raw:
            try:
                tid = int(item)
            except (TypeError, ValueError):
                continue
            if tid > 0:
                ordered.append(tid)
    elif isinstance(middle_raw, dict):
        for value in middle_raw.values():
            try:
                tid = int(value)
            except (TypeError, ValueError):
                continue
            if tid > 0:
                ordered.append(tid)

    thank_raw = body.get("thank_you_template_id")
    if thank_raw is not None and str(thank_raw).strip():
        try:
            ordered.append(int(thank_raw))
        except (TypeError, ValueError):
            pass

    deduped: list[int] = []
    for tid in ordered:
        if tid not in deduped:
            deduped.append(tid)
    return deduped


@router.post("/wa-survey/send-test")
def send_wa_survey_test(
    payload: dict,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    """Start a stateful WA survey test session — welcome only; replies drive the workflow."""
    from sqlalchemy import select

    from app.models.user import User
    from app.services.recovery_service import OrganisationService
    from app.services.survey_builder_test_service import SurveyBuilderTestService
    from app.services.survey_whatsapp_template_service import SurveyWhatsappTemplateError

    body = payload or {}
    order_id = str(body.get("order_id") or "").strip()
    template_ids = _parse_wa_survey_test_template_ids(body)
    logger.info(
        "send_wa_survey_test entry org=%s order_id=%s test_phone=%s template_ids=%s keys=%s",
        principal.org_id,
        order_id or None,
        body.get("test_phone"),
        template_ids,
        sorted(body.keys()),
    )
    if not order_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="order_id is required — complete Step 3 (Generate) so the survey draft is saved before testing.",
        )

    user = db.execute(select(User).where(User.id == principal.user_id)).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication credentials")

    org = OrganisationService.get_org(db, principal.org_id)
    to_number = str(body.get("test_phone") or "").strip()
    if not to_number and user:
        to_number = str(user.phone_e164 or user.phone_number or "").strip()
    if not to_number and org:
        to_number = str(getattr(org, "contact_phone", None) or "").strip()
    if not to_number:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Enter a test mobile number in E.164 format (e.g. +447700900123).",
        )

    branding = _client_branding(db, principal.org_id, body)
    first_name = str(body.get("first_name") or "there").strip() or "there"
    business_name = str(branding.get("client_name") or branding.get("organisation_name") or "Your business")

    try:
        result = SurveyBuilderTestService.start_wa_test_session(
            db,
            org_id=principal.org_id,
            user_id=principal.user_id,
            order_id=order_id,
            test_phone=to_number,
            first_name=first_name,
            business_name=business_name,
        )
        logger.info(
            "send_wa_survey_test session_started order_id=%s recipient_id=%s to=%s",
            result.get("order_id"),
            result.get("recipient_id"),
            result.get("to_number"),
        )
        return {"ok": True, **result}
    except SurveyWhatsappTemplateError as e:
        logger.warning("send_wa_survey_test rejected: %s", e)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("send_wa_survey_test failed")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"WhatsApp test send failed: {e}",
        ) from e
