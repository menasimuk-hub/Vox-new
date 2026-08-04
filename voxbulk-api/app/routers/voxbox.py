"""Voxbox unified inbox API — multi IMAP/SMTP + DeepSeek drafts."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.voxbox import (
    VoxboxAccountIn,
    VoxboxAccountUpdate,
    VoxboxAiReplyIn,
    VoxboxCredentialsUpdate,
    VoxboxLoginIn,
    VoxboxMessagePatch,
    VoxboxReorderIn,
    VoxboxSendIn,
)
from app.services.voxbox_auth_service import VoxboxAuthError, VoxboxAuthService, get_voxbox_principal
from app.services.voxbox_mail_service import VoxboxMailService, VoxboxServiceError

router = APIRouter(prefix="/voxbox", tags=["voxbox"])


@router.post("/auth/login")
def voxbox_login(payload: VoxboxLoginIn, db: Session = Depends(get_db)):
    try:
        return VoxboxAuthService.login(db, username=payload.username, password=payload.password)
    except VoxboxAuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc


@router.get("/auth/me")
def voxbox_me(principal: dict = Depends(get_voxbox_principal)):
    return principal


@router.put("/auth/credentials")
def voxbox_update_credentials(
    payload: VoxboxCredentialsUpdate,
    principal: dict = Depends(get_voxbox_principal),
    db: Session = Depends(get_db),
):
    try:
        return VoxboxAuthService.update_credentials(
            db,
            username=principal["username"],
            current_password=payload.current_password,
            new_username=payload.username,
            new_password=payload.password,
            display_name=payload.display_name,
        )
    except VoxboxAuthError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/accounts")
def list_accounts(_principal: dict = Depends(get_voxbox_principal), db: Session = Depends(get_db)):
    return VoxboxMailService.list_accounts(db)


@router.post("/accounts")
def create_account(
    payload: VoxboxAccountIn,
    _principal: dict = Depends(get_voxbox_principal),
    db: Session = Depends(get_db),
):
    try:
        return VoxboxMailService.create_account(db, payload)
    except VoxboxServiceError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.put("/accounts/reorder")
def reorder_accounts(
    payload: VoxboxReorderIn,
    _principal: dict = Depends(get_voxbox_principal),
    db: Session = Depends(get_db),
):
    return VoxboxMailService.reorder_accounts(db, payload.ordered_ids)


@router.put("/accounts/{account_id}")
def update_account(
    account_id: str,
    payload: VoxboxAccountUpdate,
    _principal: dict = Depends(get_voxbox_principal),
    db: Session = Depends(get_db),
):
    try:
        return VoxboxMailService.update_account(db, account_id, payload)
    except VoxboxServiceError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.delete("/accounts/{account_id}")
def delete_account(
    account_id: str,
    _principal: dict = Depends(get_voxbox_principal),
    db: Session = Depends(get_db),
):
    try:
        return VoxboxMailService.delete_account(db, account_id)
    except VoxboxServiceError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/accounts/{account_id}/test")
def test_account(
    account_id: str,
    _principal: dict = Depends(get_voxbox_principal),
    db: Session = Depends(get_db),
):
    try:
        return VoxboxMailService.test_account(db, account_id)
    except VoxboxServiceError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/messages")
def list_messages(
    account_id: str | None = Query(default=None),
    folder: str | None = Query(default=None),
    tab: str | None = Query(default=None),
    q: str | None = Query(default=None),
    _principal: dict = Depends(get_voxbox_principal),
    db: Session = Depends(get_db),
):
    return VoxboxMailService.list_messages(db, account_id=account_id, folder=folder, tab=tab, q=q)


@router.get("/messages/{message_id}")
def get_message(
    message_id: str,
    _principal: dict = Depends(get_voxbox_principal),
    db: Session = Depends(get_db),
):
    try:
        return VoxboxMailService.get_message(db, message_id)
    except VoxboxServiceError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.patch("/messages/{message_id}")
def patch_message(
    message_id: str,
    payload: VoxboxMessagePatch,
    _principal: dict = Depends(get_voxbox_principal),
    db: Session = Depends(get_db),
):
    try:
        return VoxboxMailService.patch_message(db, message_id, payload)
    except VoxboxServiceError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/messages/{message_id}/send")
def send_message(
    message_id: str,
    payload: VoxboxSendIn,
    _principal: dict = Depends(get_voxbox_principal),
    db: Session = Depends(get_db),
):
    try:
        return VoxboxMailService.send_message(db, message_id, payload)
    except VoxboxServiceError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/ai/reply")
def ai_reply(
    payload: VoxboxAiReplyIn,
    _principal: dict = Depends(get_voxbox_principal),
    db: Session = Depends(get_db),
):
    return VoxboxMailService.ai_reply(db, payload)


@router.post("/sync")
def sync_mail(_principal: dict = Depends(get_voxbox_principal), db: Session = Depends(get_db)):
    return VoxboxMailService.sync_all(db)


@router.get("/kpi")
def kpi(
    account_id: str | None = Query(default=None),
    _principal: dict = Depends(get_voxbox_principal),
    db: Session = Depends(get_db),
):
    return VoxboxMailService.kpi(db, account_id=account_id)
