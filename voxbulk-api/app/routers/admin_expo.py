"""Admin API — VoxBulk Expo service."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from sqlalchemy.orm import Session

from app.core.admin_rbac import CAP_INTEGRATION, require_cap
from app.core.database import get_db
from app.services.expo.booth_service import ExpoBoothService
from app.services.expo.results_service import ExpoResultsService
from app.services.expo.seed_service import ExpoSeedService

router = APIRouter(prefix="/admin/expo", tags=["admin-expo"])


@router.get("/packages")
def list_packages(
    market_zone: str = "gb",
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    return {"ok": True, "items": ExpoBoothService.list_packages(db, market_zone=market_zone)}


@router.get("/industries")
def list_industries(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    return {"ok": True, "items": ExpoBoothService.list_industries(db)}


@router.post("/seed")
def seed_expo(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    ExpoSeedService.ensure_seeded(db)
    return {"ok": True}


@router.get("/overview")
def overview(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    return ExpoResultsService.admin_overview(db)
