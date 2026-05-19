from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_principal
from app.models.category import Category
from app.schemas.onboarding import (
    CategoryOptionOut,
    OrganisationAIConfigOut,
    OnboardingStatusOut,
    SelectCategoryIn,
    SelectSoftwareIn,
    SupportedServiceAPIOut,
    WizardCompleteIn,
    WizardSaveStepIn,
)
from app.services.onboarding_service import (
    OrganisationOnboardingService,
    SupportedServiceAPIService,
)

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


def _service_out(db: Session, row) -> dict:
    return {
        "id": row.id,
        "slug": row.slug,
        "display_name": row.display_name,
        "category_slug": row.category_slug,
        "short_description": row.short_description,
        "status": row.status,
        "is_active": bool(row.is_active),
        "is_recommended": bool(row.is_recommended),
        "api_difficulty": row.api_difficulty,
        "docs_text": row.docs_text,
        "sort_order": row.sort_order,
        "api_setup_exists": SupportedServiceAPIService.api_setup_exists(db, row.slug),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


@router.get("/categories", response_model=list[CategoryOptionOut])
def categories(db: Session = Depends(get_db), _principal=Depends(get_current_principal)):
    SupportedServiceAPIService.ensure_defaults(db)
    rows = list(db.execute(select(Category).order_by(Category.name.asc())).scalars())
    return [{"id": row.id, "slug": row.slug, "name": row.name, "description": row.description} for row in rows]


@router.get("/software-options", response_model=list[SupportedServiceAPIOut])
def software_options(category: str, db: Session = Depends(get_db), _principal=Depends(get_current_principal)):
    rows = SupportedServiceAPIService.list(db, category_slug=category)
    return [_service_out(db, row) for row in rows]


@router.get("/category-template")
def category_template(category: str, _principal=Depends(get_current_principal)):
    try:
        return OrganisationOnboardingService.category_template(category)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@router.get("/status", response_model=OnboardingStatusOut)
def status_view(db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    return OrganisationOnboardingService.status(db, principal.org_id)


@router.post("/select-category", response_model=OnboardingStatusOut)
def select_category(payload: SelectCategoryIn, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    try:
        return OrganisationOnboardingService.select_category(
            db,
            principal.org_id,
            payload.category_slug,
            confirm_change=payload.confirm_change,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/select-software", response_model=OnboardingStatusOut)
def select_software(payload: SelectSoftwareIn, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    try:
        return OrganisationOnboardingService.select_software(
            db,
            principal.org_id,
            payload.software_slug,
            confirm_change=payload.confirm_change,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.get("/wizard", response_model=OrganisationAIConfigOut)
def wizard(db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    return OrganisationOnboardingService.ai_config(db, principal.org_id)


@router.post("/wizard/save-step", response_model=OrganisationAIConfigOut)
def save_step(payload: WizardSaveStepIn, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    try:
        return OrganisationOnboardingService.apply_wizard_payload(
            db,
            principal.org_id,
            payload.model_dump(exclude_unset=True),
            complete=False,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/wizard/generate-preview", response_model=OrganisationAIConfigOut)
def generate_preview(payload: WizardSaveStepIn, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    try:
        return OrganisationOnboardingService.apply_wizard_payload(
            db,
            principal.org_id,
            payload.model_dump(exclude_unset=True),
            complete=False,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/wizard/complete", response_model=OrganisationAIConfigOut)
def complete(payload: WizardCompleteIn, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    try:
        return OrganisationOnboardingService.apply_wizard_payload(
            db,
            principal.org_id,
            payload.model_dump(exclude_unset=True),
            complete=True,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

