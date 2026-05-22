from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status

from app.core.database import get_db
from app.models.user import User
from app.core.admin_rbac import require_platform_admin
from app.services.knowledge_base_service import (
    KB_SCOPE_ORG,
    delete_kb_file,
    get_kb_file,
    list_kb_files,
    normalize_kb_scope,
    upload_kb_file,
)
from sqlalchemy.orm import Session

router = APIRouter(prefix="/admin/knowledge-base", tags=["admin-knowledge-base"])


@router.get("")
def list_knowledge_base(
    scope: str | None = Query(default=None, description="Filter: lead, sales, org"),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_platform_admin),
):
    if scope is None:
        return {"files": list_kb_files(db)}
    return {"files": list_kb_files(db, scope=normalize_kb_scope(scope))}


@router.get("/{file_id}")
def get_knowledge_base_file(
    file_id: str,
    scope: str | None = Query(default=None, description="Required scope guard: lead, sales, or org"),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_platform_admin),
):
    row = get_kb_file(db, file_id)
    if scope is not None and str(row.get("scope") or "") != normalize_kb_scope(scope):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge base file not found in this agent library",
        )
    return {"file": row}


@router.post("/upload")
async def upload_knowledge_base(
    file: UploadFile = File(...),
    scope: str = Query(default=KB_SCOPE_ORG, description="Target library: lead, sales, org"),
    db: Session = Depends(get_db),
    admin: User = Depends(require_platform_admin),
):
    row = await upload_kb_file(db, file=file, uploaded_by_user_id=admin.id, scope=scope)
    return {"file": row}


@router.delete("/{file_id}")
def remove_knowledge_base(file_id: str, db: Session = Depends(get_db), _admin: User = Depends(require_platform_admin)):
    delete_kb_file(db, file_id=file_id)
    return {"ok": True, "deleted_file_id": file_id}
