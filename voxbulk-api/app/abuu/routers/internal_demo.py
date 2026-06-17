"""Internal demo-only endpoints (guarded by ABUU_DEMO_SHOWALL_ENABLED)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.abuu.services.demo_showall_service import DemoShowallService, demo_showall_enabled
from app.core.abuu_database import get_abuu_db

router = APIRouter(prefix="/abuu/internal/demo", tags=["abuu-internal-demo"])


def _require_demo_showall() -> None:
    if not demo_showall_enabled():
        raise HTTPException(status_code=404, detail="Not found")


@router.get("/restaurants")
def demo_restaurants(db: Session = Depends(get_abuu_db), _: None = Depends(_require_demo_showall)):
    return DemoShowallService.list_restaurants(db)


@router.get("/drivers")
def demo_drivers(db: Session = Depends(get_abuu_db), _: None = Depends(_require_demo_showall)):
    return DemoShowallService.list_drivers(db)
