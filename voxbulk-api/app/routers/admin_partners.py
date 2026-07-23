from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.admin_rbac import CAP_INTEGRATION, require_cap
from app.core.database import get_db
from app.schemas.partner import PartnerProviderUpdateIn, PartnerScreeningCreateIn, PartnerScreeningCreateOut
from app.services.admin_org_service import AdminOrganisationService
from app.services.partner_service import PartnerService

router = APIRouter(prefix="/admin/partners", tags=["admin-partners"])


@router.get("/kpi")
def partners_kpi(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    return PartnerService.admin_kpi(db)


@router.get("/org-options")
def partner_org_options(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    org_rows = AdminOrganisationService.list_orgs(db, limit=200, offset=0, search=None, zone=None)
    return {"items": [{"id": o.id, "name": o.name or o.id} for o in org_rows]}


@router.get("/{provider_key}")
def get_partner_provider(
    provider_key: str,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    return PartnerService.admin_get_provider(db, provider_key)


@router.patch("/{provider_key}")
def update_partner_provider(
    provider_key: str,
    body: PartnerProviderUpdateIn,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    return PartnerService.admin_update_provider(db, provider_key, body.model_dump(exclude_unset=True))


@router.post("/{provider_key}/keys")
def generate_partner_key(
    provider_key: str,
    environment: str = Query(default="sandbox"),
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    return PartnerService.admin_generate_key(db, provider_key, environment=environment)


@router.post("/{provider_key}/health")
def ping_partner_health(
    provider_key: str,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    return PartnerService.admin_ping_health(db, provider_key)


@router.get("/{provider_key}/oauth/start")
def partner_oauth_start(
    provider_key: str,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    return PartnerService.admin_oauth_start(db, provider_key)


@router.post("/{provider_key}/oauth/disconnect")
def partner_oauth_disconnect(
    provider_key: str,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    return PartnerService.admin_oauth_disconnect(db, provider_key)


@router.post("/{provider_key}/test-recruit")
def partner_test_recruit(
    provider_key: str,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    return PartnerService.admin_test_recruit(db, provider_key)


@router.post("/{provider_key}/test-webhook")
def partner_test_webhook(
    provider_key: str,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    return PartnerService.admin_test_webhook(db, provider_key)


@router.post("/{provider_key}/test-screening", response_model=PartnerScreeningCreateOut)
def admin_test_partner_screening(
    provider_key: str,
    body: PartnerScreeningCreateIn,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    row = PartnerService.admin_create_test_screening(
        db,
        provider_key,
        partner_reference_id=body.partner_reference_id,
        job_title=body.job_title,
        screening_questions=body.screening_questions,
        candidate_name=body.candidate_name,
        candidate_phone=body.candidate_phone,
        preferred_language=body.preferred_language,
        callback_url=body.callback_url,
        job_description=body.job_description,
        candidate_email=body.candidate_email,
    )
    return PartnerScreeningCreateOut(
        status=row.status,
        screening_id=row.id,
        partner_reference_id=row.partner_reference_id,
        screening_link=row.screening_link,
        estimated_completion_minutes=row.estimated_completion_minutes,
    )
