from __future__ import annotations

from fastapi import APIRouter, Depends, File, UploadFile

from app.core.database import get_db
from app.models.user import User
from app.core.admin_rbac import require_platform_admin
from app.services.knowledge_base_service import delete_kb_file, get_kb_file, list_kb_files, upload_kb_file
from sqlalchemy.orm import Session

router = APIRouter(prefix="/admin/knowledge-base", tags=["admin-knowledge-base"])


@router.get("")
def list_knowledge_base(db: Session = Depends(get_db), _admin: User = Depends(require_platform_admin)):
    return {"files": list_kb_files(db)}


@router.get("/{file_id}")
def get_knowledge_base_file(file_id: str, db: Session = Depends(get_db), _admin: User = Depends(require_platform_admin)):
    row = get_kb_file(db, file_id)
    return {"file": row}


@router.post("/upload")
async def upload_knowledge_base(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    admin: User = Depends(require_platform_admin),
):
    row = await upload_kb_file(db, file=file, uploaded_by_user_id=admin.id)
    return {"file": row}


@router.delete("/{file_id}")
def remove_knowledge_base(file_id: str, db: Session = Depends(get_db), _admin: User = Depends(require_platform_admin)):
    delete_kb_file(db, file_id=file_id)
    return {"ok": True, "deleted_file_id": file_id}
