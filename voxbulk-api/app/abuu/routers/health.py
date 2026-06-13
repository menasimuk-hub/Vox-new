from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.core.abuu_database import (
    abuu_db_ping,
    abuu_tables_present,
    get_abuu_migration_head,
)
from app.core.admin_rbac import CAP_ABUU, require_cap
from app.core.config import get_settings
from app.models.user import User

router = APIRouter(prefix="/admin/abuu", tags=["abuu-admin"])


@router.get("/health")
def abuu_health(_admin: User = Depends(require_cap(CAP_ABUU))):
    settings = get_settings()
    if not settings.abuu_enabled:
        return JSONResponse(
            status_code=503,
            content={
                "status": "disabled",
                "database": "unknown",
                "migration_head": None,
                "tables_present": False,
                "enabled": False,
            },
        )

    connected = abuu_db_ping()
    migration_head = get_abuu_migration_head() if connected else None
    tables_present = abuu_tables_present() if connected else False

    from app.abuu.services.abuu_menu_photo_storage_service import check_storage_ready

    photo_storage = check_storage_ready()

    if not connected:
        return JSONResponse(
            status_code=503,
            content={
                "status": "not_ready",
                "database": "disconnected",
                "migration_head": migration_head,
                "tables_present": tables_present,
                "enabled": True,
                "menu_photo_storage": photo_storage,
            },
        )

    body = {
        "status": "ok",
        "database": "connected",
        "migration_head": migration_head,
        "tables_present": tables_present,
        "enabled": True,
        "menu_photo_storage": photo_storage,
    }
    if settings.abuu_enabled and not photo_storage.get("writable"):
        return JSONResponse(status_code=503, content={**body, "status": "storage_not_ready"})
    return body
