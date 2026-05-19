from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_principal
from app.schemas.user import PatientCreate, PatientOut
from app.services.recovery_service import PatientService

router = APIRouter(prefix="/patients", tags=["patients"])

@router.get("", response_model=list[PatientOut])
def list_patients(db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    return PatientService.list_patients(db, principal.org_id)


@router.post("", response_model=PatientOut)
def create_patient(payload: PatientCreate, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    try:
        return PatientService.create_patient(db, principal.org_id, **payload.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/{patient_id}", response_model=PatientOut)
def get_patient(patient_id: str, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    patient = PatientService.get_patient(db, principal.org_id, patient_id)
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")
    return patient

