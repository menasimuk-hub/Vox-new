from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.core.admin_rbac import require_platform_admin, resolve_admin_role
from app.core.database import get_db
from app.models.admin_user import AdminUser
from app.models.user import User
from app.schemas.support_ticket import CannedReplyCategoryIn, CannedReplyIn, TicketAssignIn, TicketReplyIn, TicketStatusUpdateIn
from app.services.support_ticket_service import (
    CannedReplyService,
    SupportTicketService,
    canned_category_to_dict,
    canned_reply_to_dict,
    message_to_dict,
    support_visible_categories,
    ticket_to_dict,
)

router = APIRouter(prefix="/admin/support", tags=["admin-support"])


def _role(db: Session, user: User) -> str:
    return resolve_admin_role(db, user)


@router.get("/kpis")
def admin_support_kpis(db: Session = Depends(get_db), admin: User = Depends(require_platform_admin)):
    return SupportTicketService.kpis(db, role=_role(db, admin))


@router.get("/admins")
def admin_support_assignable_admins(db: Session = Depends(get_db), admin: User = Depends(require_platform_admin)):
    role = _role(db, admin)
    if support_visible_categories(role) is not None:
        # Scoped roles can view current owner list but not browse all admins for reassignment.
        return []
    rows = list(db.query(AdminUser).filter(AdminUser.is_active == True).order_by(AdminUser.email.asc()).limit(200))  # noqa: E712
    return [{"id": r.id, "email": r.email, "role": "superadmin" if r.is_superuser else (r.role or "marketing")} for r in rows]


@router.get("/tickets")
def admin_list_tickets(
    status_filter: str | None = None,
    category: str | None = None,
    assigned_admin_user_id: str | None = None,
    organisation_id: str | None = None,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    admin: User = Depends(require_platform_admin),
):
    rows = SupportTicketService.list_admin_tickets(
        db,
        role=_role(db, admin),
        status=status_filter,
        category=category,
        assigned_admin_user_id=assigned_admin_user_id,
        organisation_id=organisation_id,
        search=search,
        limit=limit,
        offset=offset,
    )
    return [ticket_to_dict(db, r) for r in rows]


@router.get("/tickets/{ticket_id}")
def admin_get_ticket(ticket_id: int, db: Session = Depends(get_db), admin: User = Depends(require_platform_admin)):
    t = SupportTicketService.get_admin_ticket(db, role=_role(db, admin), ticket_id=ticket_id)
    if t is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")
    t.admin_unread = False
    db.add(t)
    db.commit()
    db.refresh(t)
    return {
        "ticket": ticket_to_dict(db, t),
        "messages": [message_to_dict(db, m) for m in SupportTicketService.messages(db, t.id, include_internal=True)],
        "events": [
            {
                "id": e.id,
                "ticket_id": e.ticket_id,
                "event_type": e.event_type,
                "actor_type": e.actor_type,
                "from_value": e.from_value,
                "to_value": e.to_value,
                "created_at": e.created_at,
            }
            for e in SupportTicketService.events(db, t.id)
        ],
    }


@router.get("/attachments/{attachment_id}")
def admin_download_attachment(attachment_id: int, db: Session = Depends(get_db), admin: User = Depends(require_platform_admin)):
    a = SupportTicketService.get_attachment(db, attachment_id)
    if a is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not found")
    if SupportTicketService.get_admin_ticket(db, role=_role(db, admin), ticket_id=a.ticket_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not found")
    return Response(
        content=a.data,
        media_type=a.content_type,
        headers={"Content-Disposition": f'attachment; filename="{a.filename}"'},
    )


@router.post("/tickets/{ticket_id}/reply")
def admin_reply_ticket(ticket_id: int, payload: TicketReplyIn, db: Session = Depends(get_db), admin: User = Depends(require_platform_admin)):
    t = SupportTicketService.get_admin_ticket(db, role=_role(db, admin), ticket_id=ticket_id)
    if t is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")
    t = SupportTicketService.admin_reply(db, ticket=t, admin_user=admin, message=payload.message, internal=payload.is_internal_note)
    return ticket_to_dict(db, t)


@router.post("/tickets/{ticket_id}/status")
def admin_set_ticket_status(ticket_id: int, payload: TicketStatusUpdateIn, db: Session = Depends(get_db), admin: User = Depends(require_platform_admin)):
    t = SupportTicketService.get_admin_ticket(db, role=_role(db, admin), ticket_id=ticket_id)
    if t is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")
    try:
        t = SupportTicketService.set_status(db, ticket=t, status=payload.status, actor=admin)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return ticket_to_dict(db, t)


@router.post("/tickets/{ticket_id}/assign")
def admin_assign_ticket(ticket_id: int, payload: TicketAssignIn, db: Session = Depends(get_db), admin: User = Depends(require_platform_admin)):
    role = _role(db, admin)
    if support_visible_categories(role) is not None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only full support admins can reassign tickets")
    t = SupportTicketService.get_admin_ticket(db, role=role, ticket_id=ticket_id)
    if t is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")
    try:
        t = SupportTicketService.assign(db, ticket=t, admin_id=payload.assigned_admin_user_id, actor=admin)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return ticket_to_dict(db, t)


@router.get("/canned/categories")
def admin_list_canned_categories(db: Session = Depends(get_db), _admin: User = Depends(require_platform_admin)):
    return [canned_category_to_dict(c) for c in CannedReplyService.list_categories(db)]


@router.post("/canned/categories")
def admin_create_canned_category(payload: CannedReplyCategoryIn, db: Session = Depends(get_db), _admin: User = Depends(require_platform_admin)):
    return canned_category_to_dict(CannedReplyService.upsert_category(db, category_id=None, name=payload.name, description=payload.description))


@router.put("/canned/categories/{category_id}")
def admin_update_canned_category(category_id: int, payload: CannedReplyCategoryIn, db: Session = Depends(get_db), _admin: User = Depends(require_platform_admin)):
    return canned_category_to_dict(CannedReplyService.upsert_category(db, category_id=category_id, name=payload.name, description=payload.description))


@router.delete("/canned/categories/{category_id}")
def admin_delete_canned_category(category_id: int, db: Session = Depends(get_db), _admin: User = Depends(require_platform_admin)):
    CannedReplyService.delete_category(db, category_id)
    return {"ok": True}


@router.get("/canned/replies")
def admin_list_canned_replies(
    search: str | None = None,
    category_id: int | None = None,
    active_only: bool = False,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_platform_admin),
):
    return [canned_reply_to_dict(db, r) for r in CannedReplyService.list_replies(db, search=search, category_id=category_id, active_only=active_only)]


@router.post("/canned/replies")
def admin_create_canned_reply(payload: CannedReplyIn, db: Session = Depends(get_db), _admin: User = Depends(require_platform_admin)):
    try:
        row = CannedReplyService.upsert_reply(db, reply_id=None, **payload.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return canned_reply_to_dict(db, row)


@router.put("/canned/replies/{reply_id}")
def admin_update_canned_reply(reply_id: int, payload: CannedReplyIn, db: Session = Depends(get_db), _admin: User = Depends(require_platform_admin)):
    try:
        row = CannedReplyService.upsert_reply(db, reply_id=reply_id, **payload.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return canned_reply_to_dict(db, row)


@router.delete("/canned/replies/{reply_id}")
def admin_delete_canned_reply(reply_id: int, db: Session = Depends(get_db), _admin: User = Depends(require_platform_admin)):
    CannedReplyService.delete_reply(db, reply_id)
    return {"ok": True}

