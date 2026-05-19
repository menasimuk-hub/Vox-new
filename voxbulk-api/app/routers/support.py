from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_principal
from app.schemas.support_ticket import TicketCreateIn, TicketReplyIn
from app.services.notification_service import NotificationService, notification_to_dict
from app.services.support_ticket_service import SupportTicketService, message_to_dict, ticket_to_dict

router = APIRouter(prefix="/support/tickets", tags=["support-tickets"])

MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024
ALLOWED_ATTACHMENT_TYPES = {"application/pdf", "image/jpeg", "image/png", "image/gif", "image/webp"}


async def _read_attachments(files: list[UploadFile] | None) -> list[dict]:
    out: list[dict] = []
    for f in files or []:
        if not f.filename:
            continue
        data = await f.read()
        content_type = (f.content_type or "").lower()
        if content_type not in ALLOWED_ATTACHMENT_TYPES:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Attachments must be PDF or image files")
        if len(data) > MAX_ATTACHMENT_BYTES:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Attachment max size is 5 MB")
        out.append({"filename": f.filename, "content_type": content_type, "size_bytes": len(data), "data": data})
    return out


@router.get("")
def list_my_tickets(
    status_filter: str | None = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    rows = SupportTicketService.list_customer_tickets(
        db,
        org_id=principal.org_id,
        user_id=principal.user_id,
        status=status_filter,
        limit=limit,
        offset=offset,
    )
    return [ticket_to_dict(db, r) for r in rows]


@router.post("")
def create_my_ticket(payload: TicketCreateIn, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    try:
        t = SupportTicketService.create_ticket(
            db,
            org_id=principal.org_id,
            user_id=principal.user_id,
            category=payload.category,
            subject=payload.subject,
            message=payload.message,
            branch_id=payload.branch_id,
            priority=payload.priority,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return ticket_to_dict(db, t)


@router.post("/upload")
async def create_my_ticket_with_uploads(
    category: str = Form(...),
    subject: str = Form(...),
    message: str = Form(...),
    attachments: list[UploadFile] | None = File(default=None),
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    try:
        t = SupportTicketService.create_ticket(
            db,
            org_id=principal.org_id,
            user_id=principal.user_id,
            category=category,
            subject=subject,
            message=message,
            attachments=await _read_attachments(attachments),
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return ticket_to_dict(db, t)


@router.get("/attachments/{attachment_id}")
def download_my_attachment(attachment_id: int, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    a = SupportTicketService.get_attachment(db, attachment_id)
    if a is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not found")
    t = SupportTicketService.get_customer_ticket(db, org_id=principal.org_id, user_id=principal.user_id, ticket_id=a.ticket_id)
    if t is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not found")
    return Response(
        content=a.data,
        media_type=a.content_type,
        headers={"Content-Disposition": f'attachment; filename="{a.filename}"'},
    )


@router.get("/notifications")
def my_support_notifications(db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    rows = NotificationService.list_user_notifications(
        db,
        org_id=principal.org_id,
        user_id=principal.user_id,
        unread_only=True,
        limit=20,
    )
    return [notification_to_dict(row) for row in rows]


@router.get("/{ticket_id}")
def get_my_ticket(ticket_id: int, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    t = SupportTicketService.get_customer_ticket(db, org_id=principal.org_id, user_id=principal.user_id, ticket_id=ticket_id)
    if t is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")
    t.customer_unread = False
    db.add(t)
    db.commit()
    db.refresh(t)
    NotificationService.mark_ticket_read(db, org_id=principal.org_id, user_id=principal.user_id, ticket_id=t.id)
    return {
        "ticket": ticket_to_dict(db, t),
        "messages": [message_to_dict(db, m) for m in SupportTicketService.messages(db, t.id, include_internal=False)],
        "events": [],
    }


@router.post("/{ticket_id}/reply")
def reply_my_ticket(ticket_id: int, payload: TicketReplyIn, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    t = SupportTicketService.get_customer_ticket(db, org_id=principal.org_id, user_id=principal.user_id, ticket_id=ticket_id)
    if t is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")
    t = SupportTicketService.customer_reply(db, ticket=t, user_id=principal.user_id, message=payload.message)
    return ticket_to_dict(db, t)


@router.post("/{ticket_id}/reply-upload")
async def reply_my_ticket_with_uploads(
    ticket_id: int,
    message: str = Form(...),
    attachments: list[UploadFile] | None = File(default=None),
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    t = SupportTicketService.get_customer_ticket(db, org_id=principal.org_id, user_id=principal.user_id, ticket_id=ticket_id)
    if t is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")
    t = SupportTicketService.customer_reply(
        db,
        ticket=t,
        user_id=principal.user_id,
        message=message,
        attachments=await _read_attachments(attachments),
    )
    return ticket_to_dict(db, t)


@router.post("/{ticket_id}/close")
def close_my_ticket(ticket_id: int, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    t = SupportTicketService.get_customer_ticket(db, org_id=principal.org_id, user_id=principal.user_id, ticket_id=ticket_id)
    if t is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")
    return ticket_to_dict(db, SupportTicketService.close_by_customer(db, ticket=t, user_id=principal.user_id))



