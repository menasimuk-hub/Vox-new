"""Sales mail router — IMAP sync, SMTP send, labels, contacts for salesmen."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import CurrentPrincipal, get_current_principal
from app.models.sales_rep import SalesRep
from app.services import sales_mail_service
from app.services.sales_mail_service import SalesMailServiceError
from app.services.sales_rep_service import SalesRepService

router = APIRouter(prefix="/sales/mail", tags=["sales-mail"])


def _require_salesman(db: Session, principal: CurrentPrincipal) -> SalesRep:
    rep = SalesRepService.get_rep_for_user(db, user_id=principal.user_id)
    if rep is None or not rep.is_active:
        raise HTTPException(status_code=403, detail="This account is not an active sales or partner channel user.")
    if not SalesRepService.is_salesman(rep):
        raise HTTPException(status_code=403, detail="Mail is only available to salesmen.")
    return rep


@router.get("/status")
def get_mailbox_status(db: Session = Depends(get_db), principal: CurrentPrincipal = Depends(get_current_principal)):
    rep = _require_salesman(db, principal)
    try:
        status = sales_mail_service.get_mailbox_status(db, rep.id)
    except SalesMailServiceError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True, **status}


@router.get("/labels")
def list_labels(db: Session = Depends(get_db), principal: CurrentPrincipal = Depends(get_current_principal)):
    rep = _require_salesman(db, principal)
    labels = sales_mail_service.list_labels(db, rep.id)
    return {"ok": True, "items": labels}


@router.post("/labels")
def create_label(payload: dict, db: Session = Depends(get_db), principal: CurrentPrincipal = Depends(get_current_principal)):
    rep = _require_salesman(db, principal)
    body = payload or {}
    name = str(body.get("name", "")).strip()
    if not name:
        raise HTTPException(status_code=400, detail="Label name is required")
    color = str(body.get("color", "#3b82f6")).strip()
    try:
        label = sales_mail_service.create_label(db, rep.id, name, color)
    except SalesMailServiceError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True, "label": label}


@router.delete("/labels/{label_id}")
def delete_label(label_id: str, db: Session = Depends(get_db), principal: CurrentPrincipal = Depends(get_current_principal)):
    rep = _require_salesman(db, principal)
    sales_mail_service.delete_label(db, rep.id, label_id)
    return {"ok": True}


@router.get("/contacts")
def list_contacts(db: Session = Depends(get_db), principal: CurrentPrincipal = Depends(get_current_principal)):
    rep = _require_salesman(db, principal)
    contacts = sales_mail_service.list_contacts(db, rep.id)
    return {"ok": True, "items": contacts}


@router.post("/sync")
def sync_messages(payload: dict, db: Session = Depends(get_db), principal: CurrentPrincipal = Depends(get_current_principal)):
    rep = _require_salesman(db, principal)
    body = payload or {}
    folder = str(body.get("folder", "INBOX")).strip()
    limit = int(body.get("limit", 50))
    try:
        result = sales_mail_service.sync_messages_from_imap(db, rep.id, folder, limit)
    except SalesMailServiceError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True, **result}


@router.get("/messages")
def list_messages(
    folder: str = "INBOX",
    label: str | None = None,
    limit: int = 50,
    db: Session = Depends(get_db),
    principal: CurrentPrincipal = Depends(get_current_principal),
):
    rep = _require_salesman(db, principal)
    try:
        messages = sales_mail_service.list_messages(db, rep.id, folder, label, limit)
    except SalesMailServiceError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True, "items": messages}


@router.get("/messages/{message_id}")
def get_message(message_id: str, db: Session = Depends(get_db), principal: CurrentPrincipal = Depends(get_current_principal)):
    rep = _require_salesman(db, principal)
    try:
        message = sales_mail_service.get_message(db, rep.id, message_id)
    except SalesMailServiceError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return {"ok": True, "message": message}


@router.patch("/messages/{message_id}")
def patch_message(message_id: str, payload: dict, db: Session = Depends(get_db), principal: CurrentPrincipal = Depends(get_current_principal)):
    rep = _require_salesman(db, principal)
    body = payload or {}
    try:
        message = sales_mail_service.patch_message(
            db,
            rep.id,
            message_id,
            is_starred=body["is_starred"] if "is_starred" in body else None,
            is_deleted=body["is_deleted"] if "is_deleted" in body else None,
            is_read=body["is_read"] if "is_read" in body else None,
        )
    except SalesMailServiceError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return {"ok": True, "message": message}


@router.post("/messages/delete")
def delete_messages(payload: dict, db: Session = Depends(get_db), principal: CurrentPrincipal = Depends(get_current_principal)):
    rep = _require_salesman(db, principal)
    body = payload or {}
    ids = list(body.get("ids") or [])
    permanent = bool(body.get("permanent", False))
    try:
        result = sales_mail_service.delete_messages(db, rep.id, ids, permanent=permanent)
    except SalesMailServiceError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True, **result}


@router.post("/trash/empty")
def empty_trash(db: Session = Depends(get_db), principal: CurrentPrincipal = Depends(get_current_principal)):
    rep = _require_salesman(db, principal)
    result = sales_mail_service.empty_trash(db, rep.id)
    return {"ok": True, **result}


@router.post("/send")
def send_email(payload: dict, db: Session = Depends(get_db), principal: CurrentPrincipal = Depends(get_current_principal)):
    rep = _require_salesman(db, principal)
    body = payload or {}
    to = str(body.get("to", "")).strip()
    subject = str(body.get("subject", "")).strip()
    body_html = str(body.get("body_html", "")).strip()
    body_text = str(body.get("body_text", "")).strip() if body.get("body_text") else None
    insert_promo = bool(body.get("insert_promo", False))
    cc = str(body.get("cc", "")).strip() or None
    attachments = body.get("attachments") if isinstance(body.get("attachments"), list) else []

    if not to:
        raise HTTPException(status_code=400, detail="Recipient email is required")
    if not subject:
        raise HTTPException(status_code=400, detail="Subject is required")
    if not body_html and not body_text:
        raise HTTPException(status_code=400, detail="Email body is required")

    try:
        result = sales_mail_service.send_email(
            db,
            rep.id,
            to,
            subject,
            body_html,
            body_text,
            insert_promo,
            cc=cc,
            attachments=attachments,
        )
    except SalesMailServiceError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True, **result}


@router.post("/polish")
def polish_body(payload: dict, db: Session = Depends(get_db), principal: CurrentPrincipal = Depends(get_current_principal)):
    rep = _require_salesman(db, principal)
    body = payload or {}
    original = str(body.get("body", "")).strip()
    mode = str(body.get("mode", "fix") or "fix").strip().lower()
    context = str(body.get("context_body") or body.get("context_html") or "").strip()
    try:
        polished = sales_mail_service.polish_body_with_ai(
            db,
            body=original,
            mode=mode,
            subject=str(body.get("subject") or ""),
            from_line=str(body.get("from") or body.get("from_line") or ""),
            context_body=context,
            sales_rep_id=str(rep.id),
        )
    except SalesMailServiceError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True, "polished": polished}
