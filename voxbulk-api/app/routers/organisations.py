from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
import json
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.core.dependencies import get_current_principal
from app.core.database import get_db
from app.core.encryption import get_encryptor
from app.models.provider_config import ProviderConfig
from app.models.service_api import SupportedServiceAPI
from app.schemas.onboarding import OrganisationAIConfigOut, WizardSaveStepIn
from app.schemas.organisation import OrganisationOut, OrganisationUpdate
from app.services.onboarding_service import OrganisationOnboardingService, SupportedServiceAPIService
from app.services.org_enabled_services import parse_enabled_services, serialize_enabled_services
from app.services.recovery_service import OrganisationService

router = APIRouter(prefix="/organisations", tags=["organisations"])


def _org_response(org) -> dict:
    data = OrganisationOut.model_validate(org).model_dump()
    data["enabled_services"] = parse_enabled_services(getattr(org, "enabled_services_json", None))
    return data

SERVICE_API_REQUIRED_FIELDS = {
    "dentally": [
        {"key": "base_url", "label": "Base URL", "secret": False, "placeholder": "https://api.dentally.co"},
        {"key": "api_key", "label": "API key", "secret": True, "placeholder": "Paste API key"},
    ],
    "carestack": [
        {"key": "base_url", "label": "Base URL", "secret": False, "placeholder": "CareStack API base URL"},
        {"key": "api_key", "label": "API key", "secret": True, "placeholder": "Paste API key"},
    ],
    "pabau": [
        {"key": "base_url", "label": "Base URL", "secret": False, "placeholder": "Pabau API base URL"},
        {"key": "api_key", "label": "API key", "secret": True, "placeholder": "Paste API key"},
    ],
    "cliniko": [
        {"key": "base_url", "label": "Base URL", "secret": False, "placeholder": "https://api.au1.cliniko.com/v1"},
        {"key": "api_key", "label": "API key", "secret": True, "placeholder": "Paste API key"},
    ],
    "optix": [
        {"key": "base_url", "label": "Base URL", "secret": False, "placeholder": "Optix API base URL"},
        {"key": "api_key", "label": "API key", "secret": True, "placeholder": "Paste API key"},
    ],
    "ocuco": [
        {"key": "base_url", "label": "Base URL", "secret": False, "placeholder": "Ocuco API base URL"},
        {"key": "api_key", "label": "API key", "secret": True, "placeholder": "Paste API key"},
    ],
}


def _selected_service(db: Session, org_id: str):
    SupportedServiceAPIService.ensure_defaults(db)
    status_data = OrganisationOnboardingService.status(db, org_id)
    slug = status_data.get("booking_software_slug")
    service = None
    if slug:
        service = db.execute(select(SupportedServiceAPI).where(SupportedServiceAPI.slug == slug)).scalar_one_or_none()
    return status_data, service


def _tenant_config_view(db: Session, *, org_id: str, provider: str) -> dict:
    enc = get_encryptor()
    obj = db.execute(
        select(ProviderConfig).where(
            ProviderConfig.scope == "tenant",
            ProviderConfig.org_id == org_id,
            ProviderConfig.provider == provider,
        )
    ).scalar_one_or_none()
    fields = SERVICE_API_REQUIRED_FIELDS.get(provider, [])
    if obj is None:
        return {
            "exists": False,
            "is_enabled": False,
            "configured": False,
            "config": {},
            "secret_set": {f["key"]: False for f in fields if f.get("secret")},
            "missing_fields": [f["key"] for f in fields],
        }
    try:
        cfg = json.loads(enc.decrypt_str(obj.encrypted_json))
    except Exception:
        cfg = {}
    safe_config = {k: v for k, v in cfg.items() if k not in {f["key"] for f in fields if f.get("secret")}}
    secret_set = {f["key"]: bool(cfg.get(f["key"])) for f in fields if f.get("secret")}
    missing = [f["key"] for f in fields if not str(cfg.get(f["key"]) or "").strip()]
    return {
        "exists": True,
        "is_enabled": bool(obj.is_enabled),
        "configured": bool(obj.is_enabled) and not missing,
        "config": safe_config,
        "secret_set": secret_set,
        "missing_fields": missing,
        "updated_at": obj.updated_at,
    }

@router.get("/me", response_model=OrganisationOut)
def get_my_org(
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    org = OrganisationService.get_org(db, principal.org_id)
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    return _org_response(org)


@router.patch("/me", response_model=OrganisationOut)
def update_my_org(
    payload: OrganisationUpdate,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    org = OrganisationService.update_org_profile(db, principal.org_id, **payload.model_dump(exclude_unset=True))
    return _org_response(org)


@router.patch("/me/enabled-services")
def update_enabled_services(
    payload: dict,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    from app.schemas.organisation import EnabledServicesUpdate

    body = EnabledServicesUpdate.model_validate(payload or {})
    org = OrganisationService.get_org(db, principal.org_id)
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    current = parse_enabled_services(org.enabled_services_json)
    for key in ("interview", "survey", "recovery", "follow_up"):
        val = getattr(body, key, None)
        if val is not None:
            current[key] = bool(val)
    org.enabled_services_json = serialize_enabled_services(current)
    db.add(org)
    db.commit()
    db.refresh(org)
    return {"ok": True, "enabled_services": parse_enabled_services(org.enabled_services_json)}


@router.get("/me/ai-config", response_model=OrganisationAIConfigOut)
def get_my_ai_config(
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    return OrganisationOnboardingService.ai_config(db, principal.org_id)


@router.put("/me/ai-config", response_model=OrganisationAIConfigOut)
def update_my_ai_config(
    payload: WizardSaveStepIn,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    try:
        return OrganisationOnboardingService.apply_wizard_payload(
            db,
            principal.org_id,
            payload.model_dump(exclude_unset=True),
            complete=False,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.get("/me/service-api-settings")
def get_my_service_api_settings(
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    status_data, service = _selected_service(db, principal.org_id)
    if service is None:
        return {
            "status": status_data,
            "service": None,
            "required_fields": [],
            "connection": {"exists": False, "is_enabled": False, "configured": False, "config": {}, "secret_set": {}, "missing_fields": []},
        }
    return {
        "status": status_data,
        "service": {
            "slug": service.slug,
            "display_name": service.display_name,
            "category_slug": service.category_slug,
            "short_description": service.short_description,
            "status": service.status,
            "is_active": bool(service.is_active),
            "is_recommended": bool(service.is_recommended),
            "api_difficulty": service.api_difficulty,
            "docs_text": service.docs_text,
        },
        "required_fields": SERVICE_API_REQUIRED_FIELDS.get(service.slug, []),
        "connection": _tenant_config_view(db, org_id=principal.org_id, provider=service.slug),
    }


@router.put("/me/service-api-settings")
def save_my_service_api_settings(
    payload: dict,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    _status_data, service = _selected_service(db, principal.org_id)
    if service is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Select booking software before configuring API settings")
    config = payload.get("config") or {}
    if not isinstance(config, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="config must be an object")
    is_enabled = bool(payload.get("is_enabled", True))
    provider = service.slug
    fields = SERVICE_API_REQUIRED_FIELDS.get(provider, [])
    secret_keys = {f["key"] for f in fields if f.get("secret")}
    enc = get_encryptor()
    existing = db.execute(
        select(ProviderConfig).where(
            ProviderConfig.scope == "tenant",
            ProviderConfig.org_id == principal.org_id,
            ProviderConfig.provider == provider,
        )
    ).scalar_one_or_none()
    current = {}
    if existing is not None:
        try:
            current = json.loads(enc.decrypt_str(existing.encrypted_json))
        except Exception:
            current = {}
    merged = {**current, **config}
    for key in secret_keys:
        incoming = config.get(key)
        if (incoming is None or str(incoming).strip() == "") and current.get(key):
            merged[key] = current[key]
    for field in fields:
        key = field["key"]
        if key in merged and merged[key] is not None:
            merged[key] = str(merged[key]).strip()
    encrypted_json = enc.encrypt_str(json.dumps(merged, ensure_ascii=False, separators=(",", ":")))
    if existing is None:
        existing = ProviderConfig(scope="tenant", org_id=principal.org_id, provider=provider, is_enabled=is_enabled, encrypted_json=encrypted_json)
    else:
        existing.is_enabled = is_enabled
        existing.encrypted_json = encrypted_json
    db.add(existing)
    db.commit()
    return get_my_service_api_settings(db=db, principal=principal)


@router.post("/me/service-api-settings/test")
def test_my_service_api_settings(
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    _status_data, service = _selected_service(db, principal.org_id)
    if service is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Select booking software before testing API settings")
    view = _tenant_config_view(db, org_id=principal.org_id, provider=service.slug)
    if not view["configured"]:
        return {"ok": False, "status": "incomplete", "message": "Missing required fields", "missing_fields": view["missing_fields"]}
    return {"ok": True, "status": "configured", "message": f"{service.display_name} settings are saved. Live API validation can be added next."}

