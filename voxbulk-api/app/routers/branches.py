from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_principal
from app.core.database import get_db
from app.schemas.branch import BranchCreate, BranchOut
from app.services.recovery_service import BranchService

router = APIRouter(prefix="/branches", tags=["branches"])

@router.get("", response_model=list[BranchOut])
def list_branches(
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    return BranchService.list_branches(db, principal.org_id)


@router.post("", response_model=BranchOut)
def create_branch(
    payload: BranchCreate,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    return BranchService.create_branch(
        db,
        principal.org_id,
        name=payload.name,
        address_line1=payload.address_line1,
        city=payload.city,
        postcode=payload.postcode,
    )

