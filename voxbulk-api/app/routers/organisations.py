from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
import json
from sqlalchemy.orm import Session
from sqlalchemy import select

from fastapi.responses import FileResponse

from app.core.dependencies import get_current_principal, get_current_principal_allow_pending
from app.core.database import get_db
from app.core.encryption import get_encryptor
from app.models.provider_config import ProviderConfig
from app.models.service_api import SupportedServiceAPI
from app.schemas.onboarding import OrganisationAIConfigOut, WizardSaveStepIn
from app.schemas.organisation import OrganisationOut, OrganisationUpdate
from app.services.onboarding_service import OrganisationOnboardingService, SupportedServiceAPIService
from app.services.org_rbac import OrgRbacService
from app.services.org_enabled_services import (
    AtLeastOneServiceRequiredError,
    ServiceNotAllowedError,
    clamp_enabled_to_allowed,
    merge_admin_allowed_services,
    merge_user_enabled_services,
    org_service_maps,
    parse_allowed_services,
    parse_enabled_services,
    serialize_allowed_services,
    serialize_enabled_services,
)
from app.services.recovery_service import OrganisationService

router = APIRouter(prefix="/organisations", tags=["organisations"])


def _org_response(org, db: Session) -> dict:
    from app.services.billing_currency import (
        billing_currency_is_locked,
        currency_symbol,
        resolve_org_currency,
    )
    from app.services.country_vat_service import CountryVatService

    data = OrganisationOut.model_validate(org).model_dump()
    allowed, enabled, visible = org_service_maps(org, db)
    data["allowed_services"] = allowed
    data["enabled_services"] = enabled
    data["visible_services"] = visible
    from app.services.org_enabled_services import dashboard_service_icon_urls

    data["service_icons"] = dashboard_service_icon_urls()
    currency = resolve_org_currency(db, org)
    data["country_code"] = CountryVatService.resolve_org_country_code(db, org)
    data["billing_currency"] = currency
    data["currency_symbol"] = currency_symbol(currency)
    data["billing_currency_locked"] = billing_currency_is_locked(db, org)
    if getattr(org, "logo_storage_key", None):
        data["logo_url"] = f"/organisations/me/logo/file"
    else:
        data["logo_url"] = None
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
    return _org_response(org, db)


@router.patch("/me", response_model=OrganisationOut)
def update_my_org(
    payload: OrganisationUpdate,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    try:
        OrgRbacService.assert_can_edit_org_profile(db, org_id=principal.org_id, user_id=principal.user_id)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    org = OrganisationService.update_org_profile(db, principal.org_id, **payload.model_dump(exclude_unset=True))
    return _org_response(org, db)


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
    allowed, enabled, _ = org_service_maps(org, db)
    patch = {
        k: getattr(body, k)
        for k in ("interview", "survey", "customer_feedback", "recovery", "follow_up", "campaigns", "appointments")
        if getattr(body, k, None) is not None
    }
    try:
        enabled = merge_user_enabled_services(allowed, enabled, patch)
    except AtLeastOneServiceRequiredError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except ServiceNotAllowedError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e)) from e
    org.enabled_services_json = serialize_enabled_services(enabled)
    db.add(org)
    db.commit()
    db.refresh(org)
    from app.services.org_audit_service import OrgAuditService
    from app.models.user import User

    user = db.execute(select(User).where(User.id == principal.user_id)).scalar_one_or_none()
    if user:
        OrgAuditService.record_for_user(
            db,
            org_id=principal.org_id,
            user=user,
            action="settings.services_updated",
            detail=json.dumps(patch, ensure_ascii=False),
        )
    allowed, enabled, visible = org_service_maps(org, db)
    return {"ok": True, "enabled_services": enabled, "allowed_services": allowed, "visible_services": visible}


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
    from app.services.org_audit_service import OrgAuditService
    from app.models.user import User

    user = db.execute(select(User).where(User.id == principal.user_id)).scalar_one_or_none()
    if user:
        OrgAuditService.record_for_user(
            db,
            org_id=principal.org_id,
            user=user,
            action="settings.api_connection_saved",
            detail=str(service.slug),
        )
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


# --- Team, opt-out, audit (customer dashboard) ---


def _actor_user(db: Session, principal):
    from app.models.user import User

    return db.execute(select(User).where(User.id == principal.user_id)).scalar_one_or_none()


@router.get("/me/team/members")
def list_my_team_members(db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    from app.services.org_team_service import OrgTeamService

    return OrgTeamService.list_members(db, principal.org_id)


@router.get("/me/team/invites")
def list_my_team_invites(db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    from app.services.org_team_service import OrgTeamService

    return OrgTeamService.list_invites(db, principal.org_id)


@router.post("/me/team/invites")
def create_my_team_invite(payload: dict, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    from app.services.org_audit_service import OrgAuditService
    from app.services.org_team_service import OrgTeamService

    user = _actor_user(db, principal)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication credentials")
    try:
        result = OrgTeamService.create_invite(
            db,
            org_id=principal.org_id,
            email=str(payload.get("email") or ""),
            role=payload.get("role"),
            invited_by=user,
            send_email=bool(payload.get("send_email", True)),
        )
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    OrgAuditService.record_for_user(
        db,
        org_id=principal.org_id,
        user=user,
        action="team.invite_sent",
        detail=f"Invited {result['email']} as {result['role']}",
    )
    return result


@router.delete("/me/team/invites/{invite_id}")
def revoke_my_team_invite(invite_id: str, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    from app.services.org_audit_service import OrgAuditService
    from app.services.org_team_service import OrgTeamService

    user = _actor_user(db, principal)
    try:
        ok = OrgTeamService.revoke_invite(db, org_id=principal.org_id, invite_id=invite_id, actor_user_id=principal.user_id)
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e)) from e
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invite not found")
    if user:
        OrgAuditService.record_for_user(db, org_id=principal.org_id, user=user, action="team.invite_revoked", detail=invite_id)
    return {"ok": True}


@router.delete("/me/team/members/{user_id}")
def remove_my_team_member(user_id: str, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    from app.services.org_audit_service import OrgAuditService
    from app.services.org_team_service import OrgTeamService

    user = _actor_user(db, principal)
    try:
        ok = OrgTeamService.remove_member(db, org_id=principal.org_id, user_id=user_id, actor_user_id=principal.user_id)
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")
    if user:
        OrgAuditService.record_for_user(db, org_id=principal.org_id, user=user, action="team.member_removed", detail=user_id)
    return {"ok": True}


@router.get("/me/opt-outs")
def list_my_opt_outs(db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    from app.services.org_opt_out_service import OrgOptOutService

    return OrgOptOutService.list_opt_outs(db, principal.org_id)


@router.post("/me/opt-outs")
def add_my_opt_out(payload: dict, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    from app.services.org_audit_service import OrgAuditService
    from app.services.org_opt_out_service import OrgOptOutService

    user = _actor_user(db, principal)
    try:
        row = OrgOptOutService.add_opt_out(
            db,
            org_id=principal.org_id,
            phone=str(payload.get("phone") or payload.get("phone_e164") or ""),
            contact_name=payload.get("name") or payload.get("contact_name"),
            reason=payload.get("reason"),
            created_by_user_id=principal.user_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    if user:
        OrgAuditService.record_for_user(
            db,
            org_id=principal.org_id,
            user=user,
            action="opt_out.added",
            detail=f"{row['phone_e164']} — {row.get('reason') or 'manual'}",
        )
    return row


@router.delete("/me/opt-outs/{opt_out_id}")
def remove_my_opt_out(opt_out_id: str, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    from app.services.org_audit_service import OrgAuditService
    from app.services.org_opt_out_service import OrgOptOutService

    user = _actor_user(db, principal)
    ok = OrgOptOutService.remove_opt_out(db, org_id=principal.org_id, opt_out_id=opt_out_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Opt-out not found")
    if user:
        OrgAuditService.record_for_user(db, org_id=principal.org_id, user=user, action="opt_out.removed", detail=opt_out_id)
    return {"ok": True}


@router.get("/me/audit-log")
def list_my_audit_log(
    limit: int = 100,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    from app.services.org_audit_service import OrgAuditService

    return OrgAuditService.list_events(db, principal.org_id, limit=limit)


@router.post("/me/logo")
async def upload_my_logo(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    from app.services.org_audit_service import OrgAuditService
    from app.services.org_logo_storage_service import (
        delete_logo_file,
        save_logo_bytes,
        storage_key_for,
        validate_logo_upload,
    )

    org = OrganisationService.get_org(db, principal.org_id)
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    try:
        OrgRbacService.assert_can_edit_org_profile(db, org_id=principal.org_id, user_id=principal.user_id)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    content = await file.read()
    try:
        ext = validate_logo_upload(filename=file.filename or "logo.png", content=content)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    delete_logo_file(getattr(org, "logo_storage_key", None))
    key = storage_key_for(org_id=principal.org_id, ext=ext)
    save_logo_bytes(storage_key=key, content=content)
    org.logo_storage_key = key
    db.add(org)
    db.commit()
    db.refresh(org)

    user = _actor_user(db, principal)
    if user:
        OrgAuditService.record_for_user(db, org_id=principal.org_id, user=user, action="profile.logo_updated", detail=file.filename)
    return {"ok": True, "logo_url": "/organisations/me/logo/file"}


@router.get("/me/logo/file")
def get_my_logo_file(db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    from app.services.org_logo_storage_service import media_type_for_key, resolve_logo_path

    org = OrganisationService.get_org(db, principal.org_id)
    if org is None or not getattr(org, "logo_storage_key", None):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Logo not found")
    path = resolve_logo_path(org.logo_storage_key)
    if path is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Logo file missing")
    return FileResponse(path, media_type=media_type_for_key(org.logo_storage_key))


@router.delete("/me/logo")
def delete_my_logo(db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    from app.services.org_audit_service import OrgAuditService
    from app.services.org_logo_storage_service import delete_logo_file

    org = OrganisationService.get_org(db, principal.org_id)
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    try:
        OrgRbacService.assert_can_edit_org_profile(db, org_id=principal.org_id, user_id=principal.user_id)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    if not getattr(org, "logo_storage_key", None):
        return {"ok": True}
    delete_logo_file(org.logo_storage_key)
    org.logo_storage_key = None
    db.add(org)
    db.commit()

    user = _actor_user(db, principal)
    if user:
        OrgAuditService.record_for_user(db, org_id=principal.org_id, user=user, action="profile.logo_removed", detail=None)
    return {"ok": True}


@router.get("/me/deletion-status")
def get_my_deletion_status(
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal_allow_pending),
):
    from app.models.user import User
    from app.services.account_deletion_service import AccountDeletionService

    user = db.get(User, principal.user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return AccountDeletionService.get_status(db, user=user, org_id=principal.org_id)


@router.post("/me/delete-account")
def request_delete_my_account(
    payload: dict | None = None,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    from app.models.user import User
    from app.services.account_deletion_service import AccountDeletionError, AccountDeletionService

    user = db.get(User, principal.user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    body = payload if isinstance(payload, dict) else {}
    confirm = str(body.get("confirm") or "").strip().upper()
    if confirm != "DELETE":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Type DELETE in confirm field to proceed',
        )
    try:
        return AccountDeletionService.request_user_deletion(
            db,
            user,
            org_id=principal.org_id,
            reason=str(body.get("reason") or "").strip() or None,
        )
    except AccountDeletionError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/me/cancel-delete-account")
def cancel_delete_my_account(
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal_allow_pending),
):
    from app.models.user import User
    from app.services.account_deletion_service import AccountDeletionError, AccountDeletionService

    user = db.get(User, principal.user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    try:
        return AccountDeletionService.cancel_user_deletion(db, user, org_id=principal.org_id)
    except AccountDeletionError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

