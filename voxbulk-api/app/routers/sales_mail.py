"""Sales mail router — IMAP sync, SMTP send, labels, contacts for salesmen."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import CurrentPrincipal, get_current_principal
from app.models.sales_rep import SalesRep
from app.schemas.sales_mail import SalesMailEscalateIn, SalesMailSendIn
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


def _attachments_as_dicts(attachments) -> list[dict]:
    out: list[dict] = []
    for item in attachments or []:
        if hasattr(item, "model_dump"):
            out.append(item.model_dump())
        elif isinstance(item, dict):
            out.append(item)
    return out


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
def send_email(
    payload: SalesMailSendIn,
    db: Session = Depends(get_db),
    principal: CurrentPrincipal = Depends(get_current_principal),
):
    rep = _require_salesman(db, principal)
    attachments = _attachments_as_dicts(payload.attachments)
    body_html = (payload.body_html or "").strip()
    body_text = (payload.body_text or "").strip() or None
    cc = (payload.cc or "").strip() or None
    subject = (payload.subject or "").strip()

    if payload.escalate_target:
        source_message_id = (payload.source_message_id or "").strip()
        if not source_message_id:
            raise HTTPException(status_code=400, detail="source_message_id is required for escalation")
        try:
            result = sales_mail_service.send_escalation(
                db,
                sales_rep_id=rep.id,
                org_id=principal.org_id,
                user_id=principal.user_id,
                escalate_target=payload.escalate_target,
                source_message_id=source_message_id,
                subject=subject or None,
                body_html=body_html or None,
                body_text=body_text,
                cc=cc,
                attachments=attachments,
            )
        except SalesMailServiceError as e:
            detail = str(e)
            status = 404 if "not found" in detail.lower() else 400
            raise HTTPException(status_code=status, detail=detail) from e
        return {"ok": True, **result}

    to = (payload.to or "").strip()
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
            bool(payload.insert_promo),
            cc=cc,
            attachments=attachments,
        )
    except SalesMailServiceError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True, **result}


@router.post("/escalate")
def escalate_email(
    payload: SalesMailEscalateIn,
    db: Session = Depends(get_db),
    principal: CurrentPrincipal = Depends(get_current_principal),
):
    """Forward a stored message to Support/Billing and create a support ticket."""
    rep = _require_salesman(db, principal)
    try:
        result = sales_mail_service.send_escalation(
            db,
            sales_rep_id=rep.id,
            org_id=principal.org_id,
            user_id=principal.user_id,
            escalate_target=payload.escalate_target,
            source_message_id=payload.source_message_id,
            subject=(payload.subject or "").strip() or None,
            body_html=(payload.body_html or "").strip() or None,
            body_text=(payload.body_text or "").strip() or None,
            cc=(payload.cc or "").strip() or None,
            attachments=_attachments_as_dicts(payload.attachments),
        )
    except SalesMailServiceError as e:
        detail = str(e)
        status = 404 if "not found" in detail.lower() else 400
        raise HTTPException(status_code=status, detail=detail) from e
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
