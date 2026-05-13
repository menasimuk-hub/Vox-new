from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, status
from datetime import datetime, timedelta
import secrets
import uuid
import httpx

from sqlalchemy import delete, select
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db, get_engine
from app.core.admin_rbac import (
    CAP_BILLING,
    CAP_INTEGRATION,
    CAP_ORG_OPS,
    can_manage_admin_users,
    require_cap,
    require_platform_admin,
)
from app.core.security import hash_password
from app.models.branch import Branch
from app.models.membership import OrganisationMembership
from app.models.onboarding_request import OnboardingRequest
from app.models.organisation import Organisation
from app.models.organisation_invite import OrganisationInvite
from app.models.plan import Plan
from app.models.recovery_job import RecoveryJob
from app.models.subscription import Subscription
from app.models.user import User
from app.models.billing_invoice import BillingInvoice
from app.models.payment_event import PaymentEvent
from app.models.webhook_event import WebhookEvent
from app.models.appointment import Appointment
from app.models.category import Category
from app.services.admin_billing_service import AdminBillingService
from app.services.admin_ops_service import AdminOperationsService
from app.services.admin_org_service import AdminOrganisationService
from app.services.billing_event_email_service import BillingEventEmailService
from app.services.provider_settings import ProviderSettingsService, ProviderUnknown
from app.services.providers.azure_speech import AzureSpeechProviderService, VoiceAgentConfigError
from app.services.providers.cartesia_service import CartesiaProviderService
from app.services.providers.deepgram_service import DeepgramProviderService
from app.services.providers.elevenlabs_service import ElevenLabsProviderService
from app.services.providers.groq_service import GroqProviderService
from app.services.providers.openai_service import OpenAIProviderService
from app.services.dentally import DentallyAdapter, DentallyError
from app.models.admin_user import AdminUser
from app.workers.call_tasks import process_recovery_job
from app.workers.sync_tasks import handle_gocardless_webhook, handle_twilio_webhook, handle_vapi_webhook

router = APIRouter(prefix="/admin", tags=["admin"])


def require_superadmin(db: Session = Depends(get_db), admin: User = Depends(require_platform_admin)) -> User:
    if not can_manage_admin_users(db, admin):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Superadmin required")
    return admin


def _ensure_onboarding_requests_table_for_local_dev() -> None:
    settings = get_settings()
    if str(settings.env).lower() in {"dev", "development", "local"}:
        OnboardingRequest.__table__.create(bind=get_engine(), checkfirst=True)

@router.post("/bootstrap")
def bootstrap(
    organisation_name: str,
    admin_email: str,
    admin_password: str,
    db: Session = Depends(get_db),
    x_bootstrap_token: str | None = Header(default=None, alias="X-Bootstrap-Token"),
):
    settings = get_settings()
    if not settings.bootstrap_token:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Bootstrap disabled")
    if not x_bootstrap_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bootstrap token")
    if x_bootstrap_token != settings.bootstrap_token:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid bootstrap token")

    existing_org = db.execute(select(Organisation.id).limit(1)).scalar_one_or_none()
    if existing_org is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already bootstrapped")

    org = Organisation(name=organisation_name)
    db.add(org)
    db.flush()

    user = User(email=admin_email, password_hash=hash_password(admin_password), is_active=True, is_superuser=True)
    db.add(user)
    db.flush()

    db.add(OrganisationMembership(org_id=org.id, user_id=user.id))
    db.commit()

    return {"org_id": org.id, "admin_user_id": user.id}


@router.get("/webhook-events")
def list_webhook_events(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    events = list(db.execute(select(WebhookEvent).order_by(WebhookEvent.id.desc()).limit(100)).scalars())
    return [
        {
            "id": e.id,
            "provider": e.provider,
            "external_event_id": e.external_event_id,
            "signature_valid": e.signature_valid,
            "status": e.status,
            "attempts": e.attempts,
            "received_at": e.received_at,
            "processed_at": e.processed_at,
        }
        for e in events
    ]


@router.get("/webhook-events/{event_id}")
def get_webhook_event(event_id: int, db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    e = db.execute(select(WebhookEvent).where(WebhookEvent.id == event_id)).scalar_one_or_none()
    if e is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook event not found")
    return {
        "id": e.id,
        "provider": e.provider,
        "external_event_id": e.external_event_id,
        "signature_valid": e.signature_valid,
        "status": e.status,
        "attempts": e.attempts,
        "last_error": e.last_error,
        "raw_body": e.raw_body,
        "received_at": e.received_at,
        "processed_at": e.processed_at,
    }


@router.get("/integrations/{provider}")
def get_provider_settings(provider: str, db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    try:
        return ProviderSettingsService.get_platform_config_admin_view(db, provider=provider.lower())
    except ProviderUnknown:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown provider")


@router.put("/integrations/{provider}")
def upsert_provider_settings(
    provider: str,
    payload: dict,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    """
    Admin settings upsert.

    - Secrets accepted in request but never returned.
    - Returns safe summary only.
    """
    is_enabled = bool(payload.get("is_enabled", True))
    config = payload.get("config") or {}
    if not isinstance(config, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="config must be an object")
    try:
        ProviderSettingsService.upsert_platform_config(db, provider=provider.lower(), is_enabled=is_enabled, config=config)
        return ProviderSettingsService.get_platform_config_admin_view(db, provider=provider.lower())
    except ProviderUnknown:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown provider")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/integrations/azure_speech/test-tts")
def test_azure_speech_tts(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    try:
        result = AzureSpeechProviderService.test_tts(db, text=AzureSpeechProviderService.TTS_TEST_PHRASE)
    except VoiceAgentConfigError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    if not result["ok"]:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=result)
    return result


@router.post("/integrations/elevenlabs/test-tts")
def test_elevenlabs_tts(payload: dict | None = None, db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    payload = payload or {}
    try:
        result = ElevenLabsProviderService.test_tts(
            db,
            voice_id=str(payload.get("voice_id") or "").strip() or None,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"ElevenLabs TTS test failed: {e}") from e
    if not result.get("ok"):
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=result)
    return result


@router.get("/integrations/elevenlabs/voices")
def list_elevenlabs_voices(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    try:
        return ElevenLabsProviderService.voices(db)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"ElevenLabs voices failed: {e}") from e


@router.post("/integrations/openai/test")
def test_openai_completion(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    try:
        return OpenAIProviderService.test_completion_raw(db, prompt=OpenAIProviderService.TEST_PROMPT)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"OpenAI test failed: {e}") from e


@router.post("/integrations/deepseek/test")
def test_deepseek_completion(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    try:
        return OpenAIProviderService.test_completion_raw(db, prompt=OpenAIProviderService.TEST_PROMPT, provider="deepseek")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"DeepSeek test failed: {e}") from e


@router.post("/integrations/groq/test")
def test_groq_connection(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    try:
        diagnostics = GroqProviderService.diagnostics(db)
        return {"ok": True, "message": "Groq configuration is present for Whisper STT and Orpheus TTS.", **diagnostics}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Groq test failed: {e}") from e


@router.post("/integrations/deepgram/test")
def test_deepgram_connection(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    try:
        result = DeepgramProviderService.test_connection(db)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Deepgram test failed: {e}") from e
    if not result.get("ok"):
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=result)
    return result


@router.post("/integrations/cartesia/test")
def test_cartesia_connection(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    try:
        result = CartesiaProviderService.test_connection(db)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Cartesia test failed: {e}") from e
    if not result.get("ok"):
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=result)
    return result


@router.post("/integrations/vapi/test")
def test_vapi_connection(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    cfg, enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="vapi")
    config = cfg or {}
    if not enabled:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Vapi integration is disabled")
    public_key = str(config.get("public_key") or "").strip()
    assistant_id = str(config.get("assistant_id") or "").strip()
    api_key = str(config.get("api_key") or "").strip()
    base_url = str(config.get("base_url") or "https://api.vapi.ai").strip().rstrip("/")
    missing = [name for name, value in {"public_key": public_key, "assistant_id": assistant_id}.items() if not value]
    if missing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Vapi settings incomplete: missing {', '.join(missing)}")
    if not api_key:
        return {
            "ok": True,
            "verified": False,
            "message": "Vapi browser config is present. Add the optional server API key to verify the assistant from backend.",
            "assistant_id": assistant_id,
            "public_key_set": bool(public_key),
        }
    try:
        response = httpx.get(
            f"{base_url}/assistant/{assistant_id}",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=15.0,
        )
        body = response.json() if response.headers.get("content-type", "").startswith("application/json") else {"raw_text": response.text}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Vapi test failed: {e}") from e
    if not response.is_success:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail={"message": "Vapi assistant lookup failed", "status_code": response.status_code, "payload": body})
    return {
        "ok": True,
        "verified": True,
        "message": "Vapi assistant is reachable.",
        "assistant_id": assistant_id,
        "assistant_name": body.get("name") if isinstance(body, dict) else None,
    }


@router.get("/social-login/providers")
def admin_list_social_login_providers(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    """Admin-safe read of social login provider config (no secrets)."""
    return [ProviderSettingsService.get_platform_config_admin_view(db, provider=p) for p in ["google", "facebook", "linkedin"]]


@router.put("/social-login/{provider}")
def admin_upsert_social_login_provider(
    provider: str,
    payload: dict,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    """
    Admin upsert for social login providers.

    Payload fields:
    - is_enabled: bool
    - config: { client_id, client_secret, redirect_uri, ... }
    """
    provider = provider.lower().strip()
    is_enabled = bool(payload.get("is_enabled", True))
    config = payload.get("config") or {}
    if not isinstance(config, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="config must be an object")

    # Basic validation (avoid saving unusable empty strings).
    for k in ["client_id", "client_secret", "redirect_uri"]:
        if k in config and config[k] is not None and isinstance(config[k], str):
            config[k] = config[k].strip()

    try:
        ProviderSettingsService.upsert_platform_config(db, provider=provider, is_enabled=is_enabled, config=config)
        return ProviderSettingsService.get_platform_config_admin_view(db, provider=provider)
    except ProviderUnknown:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown provider")


@router.get("/organisations")
def admin_list_organisations(
    limit: int = 50,
    offset: int = 0,
    search: str | None = None,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_ORG_OPS)),
):
    items = AdminOrganisationService.list_orgs(db, limit=limit, offset=offset, search=search)
    return [
        {
            "id": o.id,
            "name": o.name,
            "created_at": o.created_at,
            "is_suspended": o.is_suspended,
            "profile_notes": o.profile_notes,
            "category_id": getattr(o, "category_id", None),
            "category_name": getattr(o, "category_name", None),
            "plan_code": o.plan_code,
            "plan_name": o.plan_name,
            "branch_count": o.branch_count,
            "user_count": o.user_count,
            "patient_count": o.patient_count,
            "appointment_count": o.appointment_count,
            "recovery_job_count": o.recovery_job_count,
            "subscription_status": o.subscription_status,
        }
        for o in items
    ]


@router.get("/organisations/{org_id}")
def admin_get_organisation(org_id: str, db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_ORG_OPS))):
    o = AdminOrganisationService.get_org_summary(db, org_id=org_id)
    if o is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    return {
        "id": o.id,
        "name": o.name,
        "created_at": o.created_at,
        "is_suspended": o.is_suspended,
        "profile_notes": o.profile_notes,
        "category_id": getattr(o, "category_id", None),
        "category_name": getattr(o, "category_name", None),
        "address_line1": getattr(o, "address_line1", None),
        "address_line2": getattr(o, "address_line2", None),
        "city": getattr(o, "city", None),
        "county_state": getattr(o, "county_state", None),
        "postcode": getattr(o, "postcode", None),
        "country": getattr(o, "country", None),
        "contact_name": getattr(o, "contact_name", None),
        "contact_email": getattr(o, "contact_email", None),
        "contact_phone": getattr(o, "contact_phone", None),
        "website": getattr(o, "website", None),
        "branch_count": o.branch_count,
        "user_count": o.user_count,
        "patient_count": o.patient_count,
        "appointment_count": o.appointment_count,
        "recovery_job_count": o.recovery_job_count,
        "subscription_status": o.subscription_status,
        "plan_code": o.plan_code,
        "plan_name": o.plan_name,
    }


@router.patch("/organisations/{org_id}")
def admin_patch_organisation(org_id: str, payload: dict, db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_ORG_OPS))):
    org = db.execute(select(Organisation).where(Organisation.id == org_id)).scalar_one_or_none()
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    if "name" in payload and payload["name"] is not None:
        name = str(payload["name"]).strip()
        if name:
            org.name = name
    if "profile_notes" in payload:
        v = payload.get("profile_notes")
        org.profile_notes = str(v).strip() if v is not None and str(v).strip() != "" else None
    if "category_id" in payload:
        v = payload.get("category_id")
        if v is None or str(v).strip() == "":
            org.category_id = None
        else:
            cid = str(v).strip()
            exists = db.execute(select(Category.id).where(Category.id == cid)).scalar_one_or_none()
            if exists is None:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid category_id")
            org.category_id = cid
    for field in [
        "address_line1",
        "address_line2",
        "city",
        "county_state",
        "postcode",
        "country",
        "contact_name",
        "contact_email",
        "contact_phone",
        "website",
    ]:
        if field in payload:
            v = payload.get(field)
            setattr(org, field, str(v).strip() if v is not None and str(v).strip() != "" else None)
    if "is_suspended" in payload:
        org.is_suspended = bool(payload.get("is_suspended"))
    db.add(org)
    db.commit()
    db.refresh(org)
    return {
        "ok": True,
        "id": org.id,
        "name": org.name,
        "is_suspended": org.is_suspended,
        "profile_notes": org.profile_notes,
        "category_id": org.category_id,
        "address_line1": org.address_line1,
        "address_line2": org.address_line2,
        "city": org.city,
        "county_state": org.county_state,
        "postcode": org.postcode,
        "country": org.country,
        "contact_name": org.contact_name,
        "contact_email": org.contact_email,
        "contact_phone": org.contact_phone,
        "website": org.website,
    }


@router.get("/organisations/{org_id}/branches")
def admin_list_org_branches(org_id: str, db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_ORG_OPS))):
    org = db.execute(select(Organisation.id).where(Organisation.id == org_id)).scalar_one_or_none()
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    rows = list(db.execute(select(Branch).where(Branch.org_id == org_id).order_by(Branch.name.asc())).scalars())
    return [
        {
            "id": b.id,
            "name": b.name,
            "city": b.city,
            "postcode": b.postcode,
            "address_line1": b.address_line1,
            "created_at": b.created_at,
        }
        for b in rows
    ]


@router.put("/organisations/{org_id}/subscription")
def admin_set_org_subscription(org_id: str, payload: dict, db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_ORG_OPS))):
    plan_code = str(payload.get("plan_code") or "").strip()
    if not plan_code:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="plan_code required")
    org = db.execute(select(Organisation).where(Organisation.id == org_id)).scalar_one_or_none()
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    plan = db.execute(select(Plan).where(Plan.code == plan_code)).scalar_one_or_none()
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown plan_code")
    sub = db.execute(
        select(Subscription).where(Subscription.org_id == org_id).order_by(Subscription.created_at.desc()).limit(1)
    ).scalar_one_or_none()
    status_str = str(payload.get("status") or "active").strip() or "active"
    if sub is None:
        sub = Subscription(id=str(uuid.uuid4()), org_id=org_id, plan_id=plan.id, status=status_str)
        db.add(sub)
    else:
        sub.plan_id = plan.id
        sub.status = status_str
    db.commit()
    return {"ok": True, "org_id": org_id, "plan_code": plan.code, "status": sub.status}


@router.get("/organisations/{org_id}/users")
def admin_list_org_users(org_id: str, db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_ORG_OPS))):
    rows = list(
        db.execute(
            select(User.id, User.email, User.is_active, User.is_superuser, OrganisationMembership.role, OrganisationMembership.created_at)
            .join(OrganisationMembership, OrganisationMembership.user_id == User.id)
            .where(OrganisationMembership.org_id == org_id)
            .order_by(OrganisationMembership.created_at.desc())
            .limit(200)
        ).all()
    )
    return [
        {
            "user_id": uid,
            "email": email,
            "is_active": is_active,
            "is_superuser": is_superuser,
            "role": role,
            "linked_at": created_at,
        }
        for uid, email, is_active, is_superuser, role, created_at in rows
    ]


@router.post("/organisations/{org_id}/users/{user_id}/block")
def admin_set_org_user_blocked(
    org_id: str,
    user_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_ORG_OPS)),
):
    mem = db.execute(
        select(OrganisationMembership).where(
            OrganisationMembership.org_id == org_id,
            OrganisationMembership.user_id == user_id,
        )
    ).scalar_one_or_none()
    if mem is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Membership not found")
    user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user.is_superuser:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot block platform superuser")
    user.is_active = not bool(payload.get("blocked", True))
    db.add(user)
    db.commit()
    return {"ok": True, "user_id": user_id, "is_active": user.is_active}


@router.delete("/organisations/{org_id}/users/{user_id}")
def admin_remove_org_user(org_id: str, user_id: str, db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_ORG_OPS))):
    mem = db.execute(
        select(OrganisationMembership).where(
            OrganisationMembership.org_id == org_id,
            OrganisationMembership.user_id == user_id,
        )
    ).scalar_one_or_none()
    if mem is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Membership not found")
    user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
    if user and user.is_superuser:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot remove platform superuser from org")
    db.delete(mem)
    db.commit()
    return {"ok": True}


def _organisation_or_404(db: Session, org_id: str) -> Organisation:
    org = db.execute(select(Organisation).where(Organisation.id == org_id)).scalar_one_or_none()
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    return org


@router.post("/organisations/{org_id}/users")
def admin_create_or_link_org_user(
    org_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_ORG_OPS)),
):
    """
    Create a clinic user in this tenant or link an existing account (no duplicate membership).

    - New email: ``password`` (min length 6) is required.
    - Existing email: ``password`` is ignored; organisation membership + role are added only.
    """
    org_ent = _organisation_or_404(db, org_id)
    if bool(org_ent.is_suspended):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Organisation suspended")

    email = str(payload.get("email") or "").strip().lower()
    if not email or "@" not in email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Valid email required")
    password_raw = payload.get("password")
    pwd = str(password_raw).strip() if password_raw is not None else ""
    role = str(payload.get("role") or "").strip() or None

    existing = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    created_new_user = False
    if existing is None:
        if len(pwd) < 6:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="password required for new users (minimum 6 characters)",
            )
        existing = User(
            email=email,
            password_hash=hash_password(pwd),
            is_active=True,
            is_superuser=False,
        )
        db.add(existing)
        db.flush()
        created_new_user = True
    elif len(pwd) > 0:
        # Explicitly ignore stray passwords for existing accounts.
        pass

    mem_chk = db.execute(
        select(OrganisationMembership.id).where(
            OrganisationMembership.org_id == org_id,
            OrganisationMembership.user_id == existing.id,
        )
    ).scalar_one_or_none()
    if mem_chk is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User already belongs to this organisation")

    db.add(OrganisationMembership(org_id=org_id, user_id=existing.id, role=role))
    db.commit()
    db.refresh(existing)
    return {
        "user_id": existing.id,
        "email": existing.email,
        "role": role,
        "created_new_user": created_new_user,
    }


@router.post("/organisations/{org_id}/invites")
def admin_create_org_invite(
    org_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_ORG_OPS)),
):
    """Create a pending invite token; user completes signup via public /signin."""
    settings = get_settings()
    org_ent = _organisation_or_404(db, org_id)
    if bool(org_ent.is_suspended):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Organisation suspended")

    email = str(payload.get("email") or "").strip().lower()
    if not email or "@" not in email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Valid email required")
    role = str(payload.get("role") or "").strip() or None

    pending_user = db.execute(select(User.id).where(User.email == email)).scalar_one_or_none()
    if pending_user is not None:
        clash = db.execute(
            select(OrganisationMembership.id).where(
                OrganisationMembership.org_id == org_id,
                OrganisationMembership.user_id == pending_user,
            )
        ).scalar_one_or_none()
        if clash is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User already belongs to this organisation")

    db.execute(
        delete(OrganisationInvite).where(
            OrganisationInvite.org_id == org_id,
            OrganisationInvite.email == email,
            OrganisationInvite.consumed_at.is_(None),
        )
    )
    token = secrets.token_urlsafe(32)
    exp = datetime.utcnow() + timedelta(days=21)
    inv = OrganisationInvite(
        org_id=org_id,
        email=email,
        role=role,
        token=token,
        expires_at=exp,
        consumed_at=None,
    )
    db.add(inv)
    db.commit()
    db.refresh(inv)

    base = settings.public_app_origin.rstrip("/")
    signup_url = f"{base}/signin?invite_token={token}"
    return {
        "invite_id": inv.id,
        "email": email,
        "role": role,
        "expires_at": inv.expires_at,
        "token": token,
        "signup_url": signup_url,
    }


@router.get("/organisations/{org_id}/invites")
def admin_list_org_invites(org_id: str, db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_ORG_OPS))):
    """Pending (not consumed) invites for tenant visibility."""
    _organisation_or_404(db, org_id)
    now = datetime.utcnow()
    rows = list(
        db.execute(
            select(OrganisationInvite)
            .where(
                OrganisationInvite.org_id == org_id,
                OrganisationInvite.consumed_at.is_(None),
            )
            .order_by(OrganisationInvite.created_at.desc())
            .limit(200)
        )
        .scalars()
        .all()
    )
    return [
        {
            "id": i.id,
            "email": i.email,
            "role": i.role,
            "created_at": i.created_at,
            "expires_at": i.expires_at,
            "is_expired": i.expires_at < now if i.expires_at else False,
        }
        for i in rows
    ]


@router.delete("/organisations/{org_id}/invites/{invite_id}")
def admin_revoke_org_invite(
    org_id: str,
    invite_id: str,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_ORG_OPS)),
):
    inv = db.execute(
        select(OrganisationInvite).where(
            OrganisationInvite.id == invite_id,
            OrganisationInvite.org_id == org_id,
            OrganisationInvite.consumed_at.is_(None),
        )
    ).scalar_one_or_none()
    if inv is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invite not found")
    db.delete(inv)
    db.commit()
    return {"ok": True}


@router.post("/organisations")
def admin_create_organisation(payload: dict, db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_ORG_OPS))):
    name = str(payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="name required")
    category_id = payload.get("category_id")
    cid = str(category_id).strip() if category_id is not None else ""
    if cid:
        exists = db.execute(select(Category.id).where(Category.id == cid)).scalar_one_or_none()
        if exists is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid category_id")
    org = Organisation(
        name=name,
        category_id=cid or None,
        address_line1=str(payload.get("address_line1") or "").strip() or None,
        address_line2=str(payload.get("address_line2") or "").strip() or None,
        city=str(payload.get("city") or "").strip() or None,
        county_state=str(payload.get("county_state") or "").strip() or None,
        postcode=str(payload.get("postcode") or "").strip() or None,
        country=str(payload.get("country") or "").strip() or None,
        contact_name=str(payload.get("contact_name") or "").strip() or None,
        contact_email=str(payload.get("contact_email") or "").strip() or None,
        contact_phone=str(payload.get("contact_phone") or "").strip() or None,
        website=str(payload.get("website") or "").strip() or None,
        profile_notes=str(payload.get("profile_notes") or "").strip() or None,
    )
    db.add(org)
    db.commit()
    db.refresh(org)
    return {"id": org.id, "name": org.name, "created_at": org.created_at}


@router.get("/categories")
def admin_list_categories(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_ORG_OPS))):
    rows = list(db.execute(select(Category).order_by(Category.name.asc())).scalars())
    return [
        {
            "id": c.id,
            "slug": c.slug,
            "name": c.name,
            "description": c.description,
            "created_at": c.created_at,
        }
        for c in rows
    ]


@router.post("/categories")
def admin_create_category(payload: dict, db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_ORG_OPS))):
    slug = str(payload.get("slug") or "").strip().lower()
    name = str(payload.get("name") or "").strip()
    desc = payload.get("description")
    if not slug:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="slug required")
    if not name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="name required")
    exists = db.execute(select(Category.id).where(Category.slug == slug)).scalar_one_or_none()
    if exists is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Category slug already exists")
    obj = Category(slug=slug, name=name, description=str(desc).strip() if desc is not None and str(desc).strip() != "" else None)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return {"id": obj.id, "slug": obj.slug, "name": obj.name, "description": obj.description, "created_at": obj.created_at}


@router.patch("/categories/{category_id}")
def admin_patch_category(category_id: str, payload: dict, db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_ORG_OPS))):
    obj = db.execute(select(Category).where(Category.id == category_id)).scalar_one_or_none()
    if obj is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
    if "slug" in payload and payload.get("slug") is not None:
        slug = str(payload.get("slug") or "").strip().lower()
        if not slug:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="slug required")
        clash = db.execute(select(Category.id).where(Category.slug == slug, Category.id != category_id)).scalar_one_or_none()
        if clash is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Category slug already exists")
        obj.slug = slug
    if "name" in payload and payload.get("name") is not None:
        name = str(payload.get("name") or "").strip()
        if not name:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="name required")
        obj.name = name
    if "description" in payload:
        v = payload.get("description")
        obj.description = str(v).strip() if v is not None and str(v).strip() != "" else None
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return {"id": obj.id, "slug": obj.slug, "name": obj.name, "description": obj.description, "created_at": obj.created_at}


@router.delete("/categories/{category_id}")
def admin_delete_category(category_id: str, db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_ORG_OPS))):
    obj = db.execute(select(Category).where(Category.id == category_id)).scalar_one_or_none()
    if obj is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
    # detach from organisations to avoid FK violations
    db.execute(
        sa.update(Organisation)
        .where(Organisation.category_id == category_id)
        .values(category_id=None)
    )
    db.delete(obj)
    db.commit()
    return {"ok": True}


@router.get("/onboarding/requests")
def admin_list_onboarding_requests(
    status_filter: str | None = None,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_ORG_OPS)),
):
    _ensure_onboarding_requests_table_for_local_dev()
    stmt = select(OnboardingRequest).order_by(OnboardingRequest.id.desc()).limit(200)
    if status_filter:
        stmt = stmt.where(OnboardingRequest.status == status_filter)
    items = list(db.execute(stmt).scalars())
    # join user/org names cheaply
    orgs = {o.id: o for o in db.execute(select(Organisation).where(Organisation.id.in_([i.org_id for i in items]))).scalars()} if items else {}
    users = {u.id: u for u in db.execute(select(User).where(User.id.in_([i.user_id for i in items]))).scalars()} if items else {}
    return [
        {
            "id": r.id,
            "status": r.status,
            "plan_code": r.plan_code,
            "payment_method": r.payment_method,
            "created_at": r.created_at,
            "decided_at": r.decided_at,
            "decision_note": r.decision_note,
            "org_id": r.org_id,
            "org_name": orgs.get(r.org_id).name if orgs.get(r.org_id) else None,
            "user_id": r.user_id,
            "user_email": users.get(r.user_id).email if users.get(r.user_id) else None,
        }
        for r in items
    ]


@router.post("/onboarding/requests/{request_id}/approve")
def admin_approve_onboarding_request(
    request_id: int,
    payload: dict | None = None,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_ORG_OPS)),
):
    _ensure_onboarding_requests_table_for_local_dev()
    r = db.execute(select(OnboardingRequest).where(OnboardingRequest.id == request_id)).scalar_one_or_none()
    if r is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")
    if r.status != "pending":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Request not pending")

    u = db.execute(select(User).where(User.id == r.user_id)).scalar_one_or_none()
    if u is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    u.is_active = True
    r.status = "approved"
    r.decided_at = datetime.utcnow()
    r.decision_note = str((payload or {}).get("note") or "") or None
    db.add_all([u, r])
    db.commit()
    return {"ok": True}


@router.post("/onboarding/requests/{request_id}/reject")
def admin_reject_onboarding_request(
    request_id: int,
    payload: dict | None = None,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_ORG_OPS)),
):
    _ensure_onboarding_requests_table_for_local_dev()
    r = db.execute(select(OnboardingRequest).where(OnboardingRequest.id == request_id)).scalar_one_or_none()
    if r is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")
    if r.status != "pending":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Request not pending")

    r.status = "rejected"
    r.decided_at = datetime.utcnow()
    r.decision_note = str((payload or {}).get("note") or "") or None
    db.add(r)
    db.commit()
    return {"ok": True}


@router.get("/operations/overview")
def admin_operations_overview(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_ORG_OPS))):
    w = AdminOperationsService.webhook_overview(db)
    j = AdminOperationsService.recovery_jobs_overview(db)
    return {
        "webhooks": {
            "total_recent": w.total_recent,
            "received": w.received,
            "processing": w.processing,
            "processed": w.processed,
            "failed": w.failed,
            "latest_received_at": w.latest_received_at,
        },
        "recovery_jobs": {
            "total_recent": j.total_recent,
            "queued": j.queued,
            "calling": j.calling,
            "messaged": j.messaged,
            "recovered": j.recovered,
            "failed": j.failed,
            "skipped": j.skipped,
            "latest_created_at": j.latest_created_at,
        },
    }


def _recovery_job_out(job: RecoveryJob) -> dict:
    return {
        "id": job.id,
        "org_id": job.org_id,
        "appointment_id": job.appointment_id,
        "state": job.state,
        "attempts": job.attempts,
        "provider": job.provider,
        "provider_ref": job.provider_ref,
        "provider_status": job.provider_status,
        "last_error": job.last_error,
        "created_at": job.created_at,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
        "updated_at": job.updated_at,
    }


@router.get("/operations/recovery-jobs")
def admin_operations_recovery_jobs(
    state_filter: str | None = None,
    limit: int = 25,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_ORG_OPS)),
):
    stmt = select(RecoveryJob).order_by(RecoveryJob.updated_at.desc(), RecoveryJob.created_at.desc()).limit(max(1, min(int(limit or 25), 100)))
    if state_filter:
        stmt = (
            select(RecoveryJob)
            .where(RecoveryJob.state == str(state_filter).strip().lower())
            .order_by(RecoveryJob.updated_at.desc(), RecoveryJob.created_at.desc())
            .limit(max(1, min(int(limit or 25), 100)))
        )
    rows = list(db.execute(stmt).scalars())
    return [_recovery_job_out(r) for r in rows]


@router.post("/operations/recovery-jobs/{job_id}/retry")
def admin_retry_recovery_job(job_id: str, db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_ORG_OPS))):
    job = db.execute(select(RecoveryJob).where(RecoveryJob.id == job_id)).scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recovery job not found")

    appt = db.execute(select(Appointment).where(Appointment.id == job.appointment_id, Appointment.org_id == job.org_id)).scalar_one_or_none()
    if appt is not None:
        appt.recovery_state = "queued"
        appt.recovery_last_error = None
        appt.recovery_updated_at = datetime.utcnow()
        db.add(appt)

    job.state = "queued"
    job.provider_ref = None
    job.provider_status = None
    job.last_error = None
    job.started_at = None
    job.finished_at = None
    job.updated_at = datetime.utcnow()
    db.add(job)
    db.commit()
    db.refresh(job)

    task_id = None
    dispatch_error = None
    try:
        task = process_recovery_job.delay(job_id=job.id)
        task_id = getattr(task, "id", None)
    except Exception as e:
        dispatch_error = str(e)[:500]
        job.last_error = f"Queued for retry, but worker dispatch failed: {dispatch_error}"
        job.updated_at = datetime.utcnow()
        db.add(job)
        db.commit()
        db.refresh(job)

    return {"ok": True, "job": _recovery_job_out(job), "task_id": task_id, "dispatch_error": dispatch_error}


def _webhook_event_out(event: WebhookEvent, *, include_raw: bool = False) -> dict:
    out = {
        "id": event.id,
        "provider": event.provider,
        "external_event_id": event.external_event_id,
        "org_id": event.org_id,
        "signature_valid": event.signature_valid,
        "status": event.status,
        "attempts": event.attempts,
        "last_error": event.last_error,
        "received_at": event.received_at,
        "processed_at": event.processed_at,
    }
    if include_raw:
        out["raw_body"] = event.raw_body
    return out


@router.get("/operations/webhooks")
def admin_operations_webhooks(
    status_filter: str | None = None,
    limit: int = 25,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_ORG_OPS)),
):
    lim = max(1, min(int(limit or 25), 100))
    stmt = select(WebhookEvent).order_by(WebhookEvent.id.desc()).limit(lim)
    if status_filter:
        stmt = select(WebhookEvent).where(WebhookEvent.status == str(status_filter).strip().lower()).order_by(WebhookEvent.id.desc()).limit(lim)
    rows = list(db.execute(stmt).scalars())
    return [_webhook_event_out(r) for r in rows]


@router.post("/operations/webhooks/{event_id}/retry")
def admin_retry_webhook_event(event_id: int, db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_ORG_OPS))):
    event = db.execute(select(WebhookEvent).where(WebhookEvent.id == event_id)).scalar_one_or_none()
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook event not found")
    if not event.signature_valid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot retry webhook with invalid signature")

    handler = {
        "twilio": handle_twilio_webhook,
        "vapi": handle_vapi_webhook,
        "gocardless": handle_gocardless_webhook,
    }.get(str(event.provider).lower())
    if handler is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No retry handler for provider")

    event.status = "received"
    event.last_error = None
    event.processed_at = None
    db.add(event)
    db.commit()
    db.refresh(event)

    task_id = None
    dispatch_error = None
    try:
        task = handler.delay(event_id=event.id)
        task_id = getattr(task, "id", None)
    except Exception as e:
        dispatch_error = str(e)[:500]
        event.status = "failed"
        event.last_error = f"Worker dispatch failed: {dispatch_error}"
        db.add(event)
        db.commit()
        db.refresh(event)

    return {"ok": True, "event": _webhook_event_out(event), "task_id": task_id, "dispatch_error": dispatch_error}


@router.get("/billing/overview")
def admin_billing_overview(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_BILLING))):
    ov = AdminBillingService.subscriptions_overview(db)
    return {
        "plans_total": ov.plans_total,
        "subscriptions_total": ov.subscriptions_total,
        "subscriptions_active": ov.subscriptions_active,
        "subscriptions_trial": ov.subscriptions_trial,
        "subscriptions_past_due": ov.subscriptions_past_due,
        "subscriptions_pending_payment": ov.subscriptions_pending_payment,
        "subscriptions_test_mode": ov.subscriptions_test_mode,
        "subscriptions_production_mode": ov.subscriptions_production_mode,
        "latest_subscription_created_at": ov.latest_subscription_created_at,
    }


@router.get("/billing/plans")
def admin_list_plans(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_BILLING))):
    from app.services.gocardless_service import BillingService

    BillingService.ensure_default_plans(db)
    plans = AdminBillingService.list_plans(db)
    return [
        {
            "id": p.id,
            "code": p.code,
            "name": p.name,
            "price_gbp_pence": p.price_gbp_pence,
            "interval": p.interval,
            "created_at": p.created_at,
            "description": getattr(p, "description", None),
            "features_json": getattr(p, "features_json", None),
        }
        for p in plans
    ]


@router.put("/billing/plans/{plan_id}")
def admin_put_plan(
    plan_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_BILLING)),
):
    """Update marketing copy and pricing for a plan (clinic dashboard reads public GET /billing/plans)."""
    from app.services.gocardless_service import BillingService

    BillingService.ensure_default_plans(db)
    p = db.execute(select(Plan).where(Plan.id == plan_id)).scalar_one_or_none()
    if p is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")

    if payload.get("name") is not None:
        p.name = str(payload.get("name") or "").strip() or p.name
    if payload.get("price_gbp_pence") is not None:
        p.price_gbp_pence = int(payload.get("price_gbp_pence") or 0)
    if payload.get("interval") is not None:
        p.interval = str(payload.get("interval") or "monthly").strip()
    if "description" in payload:
        raw = payload.get("description")
        p.description = None if raw is None else str(raw)
    if isinstance(payload.get("features"), list):
        import json

        p.features_json = json.dumps([str(x) for x in payload["features"]])
    elif payload.get("features_json") is not None:
        p.features_json = str(payload.get("features_json") or "") or None

    db.add(p)
    db.commit()
    db.refresh(p)
    return {
        "id": p.id,
        "code": p.code,
        "name": p.name,
        "price_gbp_pence": p.price_gbp_pence,
        "interval": p.interval,
        "created_at": p.created_at,
        "description": p.description,
        "features_json": p.features_json,
    }


@router.get("/admin-users")
def admin_list_admin_users(db: Session = Depends(get_db), _admin=Depends(require_superadmin)):
    rows = list(db.execute(select(AdminUser).order_by(AdminUser.created_at.desc()).limit(200)).scalars())
    return [
        {
            "id": r.id,
            "email": r.email,
            "is_active": bool(r.is_active),
            "is_superuser": bool(r.is_superuser),
            "role": r.role,
            "created_at": r.created_at,
        }
        for r in rows
    ]


_ROLES_ALLOWED = frozenset({"superadmin", "admin", "accountant", "technical", "support", "marketing"})


@router.post("/admin-users")
def admin_create_admin_user(payload: dict, db: Session = Depends(get_db), _admin=Depends(require_superadmin)):
    email = str(payload.get("email") or "").strip().lower()
    password = str(payload.get("password") or "")
    is_active = bool(payload.get("is_active", True))
    role_raw = str(payload.get("role") or "marketing").strip().lower()
    want_super_flag = bool(payload.get("is_superuser", False))
    if role_raw not in _ROLES_ALLOWED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="role must be one of: superadmin, admin, accountant, technical, support, marketing",
        )
    if want_super_flag and role_raw != "superadmin":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="is_superuser is only valid with role superadmin",
        )

    role = "superadmin" if role_raw == "admin" else role_raw
    is_super = role == "superadmin"
    user_is_super = is_super

    if not email or "@" not in email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Valid email required")
    if len(password) < 6:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="password minimum 6 characters")

    # Choose an org to satisfy the existing JWT + principal checks.
    org_id = db.execute(select(Organisation.id).order_by(Organisation.created_at.asc()).limit(1)).scalar_one_or_none()
    if org_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No organisation exists yet")

    existing = db.execute(select(AdminUser.id).where(AdminUser.email == email)).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Admin user already exists")

    # Create a backing `users` row so /auth/token + tenant membership continue to work for console users.
    u_existing = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if u_existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already used by a clinic user")

    uid = str(uuid.uuid4())
    pwd_hash = hash_password(password)

    db.add(
        AdminUser(
            id=uid,
            email=email,
            password_hash=pwd_hash,
            is_active=is_active,
            is_superuser=is_super,
            role=role,
        )
    )
    db.add(User(id=uid, email=email, password_hash=pwd_hash, is_active=is_active, is_superuser=user_is_super))
    db.add(OrganisationMembership(org_id=str(org_id), user_id=uid))
    db.commit()
    return {"ok": True, "id": uid, "email": email, "role": role}


@router.patch("/admin-users/{admin_user_id}")
def admin_patch_admin_user(
    admin_user_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    _admin=Depends(require_superadmin),
):
    au = db.execute(select(AdminUser).where(AdminUser.id == admin_user_id)).scalar_one_or_none()
    if au is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Admin user not found")

    user_row = db.execute(select(User).where(User.id == admin_user_id)).scalar_one_or_none()
    if user_row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Backing user missing")

    if "is_active" in payload:
        au.is_active = bool(payload.get("is_active"))
        user_row.is_active = au.is_active

    if "role" in payload:
        rr = str(payload.get("role") or "").strip().lower()
        if rr not in _ROLES_ALLOWED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="role must be one of: superadmin, admin, accountant, technical, support, marketing",
            )
        au.role = rr
        rr = "superadmin" if rr == "admin" else rr
        au.is_superuser = rr == "superadmin"
        user_row.is_superuser = rr == "superadmin"

    if "password" in payload and payload.get("password") is not None:
        pw = str(payload.get("password") or "")
        if len(pw) < 6:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="password minimum 6 characters")
        hashed = hash_password(pw)
        au.password_hash = hashed
        user_row.password_hash = hashed

    db.add_all([au, user_row])
    db.commit()
    db.refresh(au)
    return {
        "id": au.id,
        "email": au.email,
        "is_active": bool(au.is_active),
        "is_superuser": bool(au.is_superuser),
        "role": au.role,
    }


@router.delete("/admin-users/{admin_user_id}")
def admin_delete_admin_user(admin_user_id: str, db: Session = Depends(get_db), _admin=Depends(require_superadmin)):
    au = db.execute(select(AdminUser).where(AdminUser.id == admin_user_id)).scalar_one_or_none()
    if au is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Admin user not found")

    # Disable backing user (do not cascade delete other data).
    u = db.execute(select(User).where(User.id == admin_user_id)).scalar_one_or_none()
    if u is not None:
        u.is_active = False
        db.add(u)

    db.delete(au)
    db.commit()
    return {"ok": True}


@router.get("/billing/payment-events/recent")
def admin_list_recent_payment_events(
    limit: int = 50,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_BILLING)),
):
    """Minimal read surface for webhook-driven billing events (debug)."""
    cap = max(1, min(int(limit or 50), 200))
    rows = db.execute(select(PaymentEvent).order_by(PaymentEvent.created_at.desc()).limit(cap)).scalars().all()
    return [
        {
            "id": r.id,
            "provider": r.provider,
            "external_event_id": r.external_event_id,
            "org_id": r.org_id,
            "status": r.status,
            "client_email": r.client_email,
            "failure_reason": r.failure_reason,
            "emailed_at": r.emailed_at.isoformat() if r.emailed_at else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


@router.get("/billing/invoices/recent")
def admin_list_recent_billing_invoices(
    limit: int = 50,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_BILLING)),
):
    cap = max(1, min(int(limit or 50), 200))
    rows = db.execute(select(BillingInvoice).order_by(BillingInvoice.created_at.desc()).limit(cap)).scalars().all()
    return [
        {
            "id": r.id,
            "provider": r.provider,
            "external_invoice_id": r.external_invoice_id,
            "org_id": r.org_id,
            "status": r.status,
            "client_email": r.client_email,
            "amount_gbp_pence": r.amount_gbp_pence,
            "currency": r.currency,
            "emailed_at": r.emailed_at.isoformat() if r.emailed_at else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


@router.post("/billing/payment-events")
def admin_record_payment_event(payload: dict, db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_BILLING))):
    """
    Minimal internal event sink to wire real payment failures to email hooks.

    Expected fields:
    - provider, external_event_id, org_id, client_email, status, failure_reason?, variables?
    """
    provider = str(payload.get("provider") or "internal")
    external_event_id = str(payload.get("external_event_id") or "")
    org_id = str(payload.get("org_id") or "")
    client_email = str(payload.get("client_email") or "")
    status_str = str(payload.get("status") or "")
    failure_reason = payload.get("failure_reason")
    variables = payload.get("variables") if isinstance(payload.get("variables"), dict) else {}

    try:
        row, created, sent = BillingEventEmailService.record_payment_status(
            db,
            provider=provider,
            external_event_id=external_event_id,
            org_id=org_id,
            client_email=client_email,
            status=status_str,
            failure_reason=str(failure_reason) if failure_reason is not None else None,
            variables=variables,
        )
        return {"ok": True, "created": created, "sent": sent, "event_id": row.id}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/billing/invoices")
def admin_create_invoice(payload: dict, db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_BILLING))):
    """
    Minimal invoice creation pipeline to wire new invoice events to email hooks.

    Expected fields:
    - provider, external_invoice_id, org_id, client_email, amount_gbp_pence?, currency?, status?, variables?
    """
    provider = str(payload.get("provider") or "internal")
    external_invoice_id = str(payload.get("external_invoice_id") or "")
    org_id = str(payload.get("org_id") or "")
    client_email = str(payload.get("client_email") or "")
    amount = int(payload.get("amount_gbp_pence") or 0)
    currency = str(payload.get("currency") or "GBP")
    status_str = str(payload.get("status") or "issued")
    variables = payload.get("variables") if isinstance(payload.get("variables"), dict) else {}

    try:
        row, created, sent = BillingEventEmailService.create_invoice(
            db,
            provider=provider,
            external_invoice_id=external_invoice_id,
            org_id=org_id,
            client_email=client_email,
            amount_gbp_pence=amount,
            currency=currency,
            status=status_str,
            variables=variables,
        )
        return {"ok": True, "created": created, "sent": sent, "invoice_id": row.id}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


def _redact(obj, *, depth: int = 0):
    if depth > 6:
        return None
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            key = str(k).lower()
            # Conservative redaction: drop likely PII fields.
            if any(s in key for s in ["name", "email", "phone", "mobile", "address", "dob", "birth", "note", "notes"]):
                continue
            if key in {"first_name", "last_name"}:
                continue
            out[k] = _redact(v, depth=depth + 1)
        return out
    if isinstance(obj, list):
        return [_redact(x, depth=depth + 1) for x in obj[:10]]
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    return str(obj)


def _find_candidate_paths(obj, *, prefix: str = "") -> list[str]:
    hits: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{prefix}.{k}" if prefix else str(k)
            kl = str(k).lower()
            if any(s in kl for s in ["procedure", "treatment", "reason", "description", "appointment_type", "type"]):
                hits.append(p)
            hits.extend(_find_candidate_paths(v, prefix=p))
    elif isinstance(obj, list):
        for i, x in enumerate(obj[:5]):
            hits.extend(_find_candidate_paths(x, prefix=f"{prefix}[{i}]"))
    return hits


@router.post("/debug/dentally/appointments-sample")
def debug_capture_dentally_appointments_sample(
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
    x_debug_capture_token: str | None = Header(default=None, alias="X-Debug-Capture-Token"),
):
    """
    TEMPORARY: Fetch and return a single redacted Dentally /appointments item for payload inspection.

    - Admin-only
    - Disabled when ENV=production
    - Requires X-Debug-Capture-Token == BOOTSTRAP_TOKEN (reuses existing secret; no new env vars)
    - Redacts likely PII fields conservatively.
    """
    settings = get_settings()
    if settings.env.lower() == "production":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    if not settings.bootstrap_token:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Debug capture disabled")
    if not x_debug_capture_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing debug capture token")
    if x_debug_capture_token != settings.bootstrap_token:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid debug capture token")

    try:
        adapter = DentallyAdapter.from_settings()
        payload = adapter._get("/appointments", params={"page": 1})
    except DentallyError as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))

    items = payload.get("items") or payload.get("data") or []
    sample = items[0] if isinstance(items, list) and items else None
    redacted = _redact(sample) if isinstance(sample, dict) else None
    candidates = _find_candidate_paths(sample) if sample is not None else []
    return {"redacted_sample": redacted, "candidate_field_paths": sorted(set(candidates))}

