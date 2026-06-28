"""Admin API — disabled WA templates (Platform Settings)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.admin_rbac import CAP_INTEGRATION, require_cap
from app.core.database import get_db
from app.services.disabled_wa_template_service import DisabledWaTemplateService

router = APIRouter(prefix="/admin/disabled-wa-templates", tags=["admin-disabled-wa-templates"])


@router.get("")
def list_disabled_templates(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    return {"ok": True, "items": DisabledWaTemplateService.list_rows(db)}


@router.post("/names")
def add_template_names(payload: dict, db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    names = payload.get("names") or []
    if isinstance(names, str):
        names = [line.strip() for line in names.splitlines() if line.strip()]
    if not isinstance(names, list):
        raise HTTPException(status_code=400, detail="names must be a list or multiline string")
    try:
        return DisabledWaTemplateService.add_names(db, names)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/upload")
async def upload_template_names(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    filename = file.filename or "upload.txt"
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")
    try:
        names = DisabledWaTemplateService.parse_upload_content(filename, content)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not parse file: {e}") from e
    if not names:
        raise HTTPException(status_code=400, detail="No template names found in file")
    return DisabledWaTemplateService.add_names(db, names)


@router.put("/{row_id}")
def toggle_disabled(row_id: str, payload: dict, db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    disabled = bool(payload.get("disabled"))
    try:
        return DisabledWaTemplateService.set_disabled(db, row_id, disabled)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/disable-all")
def disable_all(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    return DisabledWaTemplateService.disable_all(db)


@router.post("/enable-all")
def enable_all(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    return DisabledWaTemplateService.enable_all(db)


@router.delete("/{row_id}")
def remove_row(row_id: str, db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    try:
        return DisabledWaTemplateService.remove(db, row_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
