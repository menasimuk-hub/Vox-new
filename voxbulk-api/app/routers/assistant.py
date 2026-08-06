from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.admin_rbac import require_platform_admin
from app.core.database import get_db
from app.core.dependencies import CurrentPrincipal, get_current_principal
from app.models.user import User
from app.schemas.assistant import (
    AssistantChatIn,
    AssistantChatOut,
    AssistantConfirmIn,
    AssistantConversationOut,
    AssistantFeedbackIn,
    AssistantInsightsOut,
    AssistantMessageOut,
    AssistantReportSupportIn,
    AssistantReportSupportOut,
    AssistantSuggestionOut,
    AssistantSuggestionStatusIn,
)
from app.services.assistant import conversation_service, help_chunk_sync_service
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


@router.get("/conversations", response_model=list[AssistantConversationOut])
def list_conversations(
    db: Session = Depends(get_db),
    principal: CurrentPrincipal = Depends(get_current_principal),
) -> list[AssistantConversationOut]:
    rows = conversation_service.list_conversations(db, principal.org_id, principal.user_id)
    return [
        AssistantConversationOut(
            id=r.id,
            title=r.title,
            created_at=r.created_at.isoformat() if r.created_at else "",
            updated_at=r.updated_at.isoformat() if r.updated_at else "",
        )
        for r in rows
    ]


@router.get("/conversations/{conversation_id}/messages", response_model=list[AssistantMessageOut])
def list_messages(
    conversation_id: str,
    db: Session = Depends(get_db),
    principal: CurrentPrincipal = Depends(get_current_principal),
) -> list[AssistantMessageOut]:
    conv = conversation_service.get_conversation(db, conversation_id, principal.user_id)
    if conv is None or conv.org_id != principal.org_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    import json

    msgs = conversation_service.get_messages(db, conversation_id)
    out: list[AssistantMessageOut] = []
    for m in msgs:
        sources = []
        if m.sources_json:
            try:
                sources = json.loads(m.sources_json)
            except Exception:
                sources = []
        out.append(
            AssistantMessageOut(
                id=m.id,
                role=m.role,
                content=m.content,
                source_type=m.source_type,
                sources=sources if isinstance(sources, list) else [],
                created_at=m.created_at.isoformat() if m.created_at else "",
            )
        )
    return out


@router.delete("/conversations/{conversation_id}")
def delete_conversation(
    conversation_id: str,
    db: Session = Depends(get_db),
    principal: CurrentPrincipal = Depends(get_current_principal),
) -> dict:
    ok = conversation_service.delete_conversation(db, conversation_id, principal.user_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    return {"ok": True}


@router.post("/messages/{message_id}/feedback")
def message_feedback(
    message_id: str,
    payload: AssistantFeedbackIn,
    db: Session = Depends(get_db),
    principal: CurrentPrincipal = Depends(get_current_principal),
) -> dict:
    try:
        return conversation_service.record_feedback(
            db,
            message_id=message_id,
            user_id=principal.user_id,
            org_id=principal.org_id,
            rating=payload.rating,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


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
    _admin: User = Depends(require_platform_admin),
    principal: CurrentPrincipal = Depends(get_current_principal),
) -> AssistantChatOut:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Admin assistant mutations are not enabled yet.",
    )


@admin_router.post("/help/rebuild-index")
def admin_rebuild_help_index(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_platform_admin),
) -> dict:
    return help_chunk_sync_service.rebuild_all(db)


@admin_router.get("/insights", response_model=AssistantInsightsOut)
def admin_assistant_insights(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_platform_admin),
) -> AssistantInsightsOut:
    data = conversation_service.insights_summary(db)
    return AssistantInsightsOut(**data)


@admin_router.get("/suggestions", response_model=list[AssistantSuggestionOut])
def admin_list_suggestions(
    status_filter: str | None = Query(default="pending", alias="status"),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_platform_admin),
) -> list[AssistantSuggestionOut]:
    rows = conversation_service.list_suggestions(db, status=status_filter)
    return [
        AssistantSuggestionOut(
            id=r.id,
            question=r.question,
            sample_answer=r.sample_answer,
            org_id=r.org_id,
            user_id=r.user_id,
            status=r.status,
            created_at=r.created_at.isoformat() if r.created_at else "",
        )
        for r in rows
    ]


@admin_router.patch("/suggestions/{suggestion_id}")
def admin_update_suggestion(
    suggestion_id: str,
    payload: AssistantSuggestionStatusIn,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_platform_admin),
) -> dict:
    row = conversation_service.set_suggestion_status(db, suggestion_id, payload.status)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Suggestion not found")
    return {"ok": True, "id": row.id, "status": row.status}
