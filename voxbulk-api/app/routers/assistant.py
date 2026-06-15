from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.admin_rbac import require_platform_admin
from app.core.database import get_db
from app.core.dependencies import CurrentPrincipal, get_current_principal
from app.models.user import User
from app.schemas.assistant import AssistantChatIn, AssistantChatOut, AssistantConfirmIn, AssistantReportSupportIn, AssistantReportSupportOut
from app.services.assistant.orchestrator import AssistantOrchestrator
from app.services.assistant.support_report_service import create_diagnostic_support_ticket

router = APIRouter(prefix="/assistant", tags=["assistant"])


@router.post("/chat", response_model=AssistantChatOut)
def customer_assistant_chat(
    payload: AssistantChatIn,
    db: Session = Depends(get_db),
    principal: CurrentPrincipal = Depends(get_current_principal),
) -> AssistantChatOut:
    return AssistantOrchestrator.handle_chat(db, principal=principal, payload=payload, is_admin=False)


@router.post("/confirm", response_model=AssistantChatOut)
def customer_assistant_confirm(
    payload: AssistantConfirmIn,
    db: Session = Depends(get_db),
    principal: CurrentPrincipal = Depends(get_current_principal),
) -> AssistantChatOut:
    return AssistantOrchestrator.handle_confirm(
        db,
        principal=principal,
        action_id=payload.action_id,
        confirmed=payload.confirmed,
    )


@router.post("/report-support", response_model=AssistantReportSupportOut)
def customer_assistant_report_support(
    payload: AssistantReportSupportIn,
    db: Session = Depends(get_db),
    principal: CurrentPrincipal = Depends(get_current_principal),
) -> AssistantReportSupportOut:
    return create_diagnostic_support_ticket(
        db,
        org_id=principal.org_id,
        user_id=principal.user_id,
        support_report_token=payload.support_report_token,
    )


admin_router = APIRouter(prefix="/admin/assistant", tags=["admin-assistant"])


@admin_router.post("/chat", response_model=AssistantChatOut)
def admin_assistant_chat(
    payload: AssistantChatIn,
    db: Session = Depends(get_db),
    admin: User = Depends(require_platform_admin),
) -> AssistantChatOut:
    org_id = (payload.context.organisation_id or "").strip()
    if not org_id:
        return AssistantChatOut(
            ok=True,
            primary_message="Admin assistant needs an organisation context. Provide organisation_id in context or open an organisation first.",
            confidence=0.9,
            intent="admin_general",
            next_actions=[],
        )
    principal = CurrentPrincipal(user_id=str(admin.id), org_id=org_id, token_payload={})
    return AssistantOrchestrator.handle_chat(db, principal=principal, payload=payload, is_admin=True)


@admin_router.post("/confirm", response_model=AssistantChatOut)
def admin_assistant_confirm(
    payload: AssistantConfirmIn,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_platform_admin),
    principal: CurrentPrincipal = Depends(get_current_principal),
) -> AssistantChatOut:
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Admin assistant mutations are not enabled yet.")
