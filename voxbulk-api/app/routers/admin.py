from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import HTMLResponse, Response
from datetime import datetime, timedelta
import json
import secrets
import uuid
import httpx

from sqlalchemy import delete, select
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db, get_engine
from app.core.http_ssl import httpx_ssl_verify
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
from app.models.dentally_appointment import DentallyAppointment
from app.models.category import Category
from app.services.admin_billing_service import AdminBillingService
from app.services.admin_ops_service import AdminOperationsService
from app.services.admin_org_service import AdminOrganisationService
from app.services.billing_event_email_service import BillingEventEmailService
from app.services.gocardless_service import BillingService, GoCardlessConfigError, GoCardlessProviderError
from app.services.provider_settings import ProviderSettingsService, ProviderUnknown
from app.services.providers.azure_speech import AzureSpeechProviderService, VoiceAgentConfigError
from app.services.providers.cartesia_service import CartesiaProviderService
from app.services.providers.deepgram_service import DeepgramProviderService
from app.services.providers.elevenlabs_service import ElevenLabsProviderService
from app.services.providers.groq_service import GroqProviderService
from app.services.providers.openai_service import OpenAIProviderService
from app.services.telnyx_external_connection_service import TelnyxExternalConnectionService
from app.services.telnyx_api_key import (
    normalize_telnyx_api_key,
    normalize_telnyx_e164,
    require_telnyx_api_key,
    resolve_telnyx_api_key,
    telnyx_auth_hint,
    telnyx_caller_hint,
    telnyx_key_fingerprint,
    telnyx_outbound_caller_id,
)
from app.services.telnyx_messaging_service import TelnyxMessagingService
from app.services.messaging_log_service import LogService
from app.services.telnyx_voice_service import TelnyxVoiceAdapter
from app.services.dentally import DentallyAdapter, DentallyError
from app.models.admin_user import AdminUser
from app.workers.call_tasks import process_recovery_job
from app.workers.sync_tasks import handle_gocardless_webhook, handle_vapi_webhook

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
    visible_to_orgs = payload.get("visible_to_orgs")
    if visible_to_orgs is not None:
        visible_to_orgs = bool(visible_to_orgs)
    config = payload.get("config") or {}
    if not isinstance(config, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="config must be an object")
    try:
        ProviderSettingsService.upsert_platform_config(
            db,
            provider=provider.lower(),
            is_enabled=is_enabled,
            config=config,
            visible_to_orgs=visible_to_orgs,
        )
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


def _persist_telnyx_connection_metadata(db: Session, patch: dict[str, Any]) -> None:
    cfg, enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="telnyx")
    telnyx_obj = ProviderSettingsService.get_platform_config(db, provider="telnyx")
    telnyx_is_enabled = bool(telnyx_obj.is_enabled) if telnyx_obj is not None else bool(enabled)
    ProviderSettingsService.upsert_platform_config(
        db,
        provider="telnyx",
        is_enabled=telnyx_is_enabled,
        config=patch,
    )


@router.post("/integrations/telnyx/microsoft-teams/create-connection")
def create_telnyx_microsoft_teams_connection(
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    try:
        refresh = TelnyxExternalConnectionService.refresh_operator_connect(db)
        snapshot = TelnyxExternalConnectionService.test_operator_connect(db, refresh_first=False)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Telnyx Microsoft Teams create failed: {e}") from e
    first_id = ""
    if isinstance(snapshot, dict):
        rows = snapshot.get("connections")
        if isinstance(rows, list) and rows and isinstance(rows[0], dict):
            first_id = str(rows[0].get("id") or "").strip()
    _persist_telnyx_connection_metadata(
        db,
        {
            "teams_external_connection_id": first_id,
            "teams_operator_connect_last_refresh_at": datetime.utcnow().isoformat(),
        },
    )
    return {
        "ok": bool(refresh.get("ok") or snapshot.get("ok")),
        "message": str(refresh.get("message") or "Operator Connect refresh sent."),
        "refresh": refresh,
        "snapshot": snapshot,
    }


@router.post("/integrations/telnyx/microsoft-teams/test-connection")
def test_telnyx_microsoft_teams_connection(
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    try:
        result = TelnyxExternalConnectionService.test_operator_connect(db, refresh_first=True)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Telnyx Microsoft Teams test failed: {e}") from e
    rows = result.get("connections")
    if isinstance(rows, list) and rows and isinstance(rows[0], dict):
        cid = str(rows[0].get("id") or "").strip()
        _persist_telnyx_connection_metadata(
            db,
            {
                "teams_external_connection_id": cid,
                "teams_operator_connect_last_refresh_at": datetime.utcnow().isoformat(),
            },
        )
    return result


@router.post("/integrations/calendly/test")
def test_calendly_integration(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    from app.services.scheduling_connection_service import test_calendly_platform_config

    return test_calendly_platform_config(db)


@router.post("/integrations/cal-com/test")
def test_cal_com_integration(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    from app.services.cal_com_connection_service import test_cal_com_platform_config

    return test_cal_com_platform_config(db)


@router.post("/integrations/google-calendar/test")
def test_google_calendar_integration(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    from app.services.google_calendar_booking_service import test_google_calendar_platform_config

    return test_google_calendar_platform_config(db)


@router.post("/integrations/microsoft-calendar/test")
def test_microsoft_calendar_integration(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    from app.services.microsoft_calendar_service import test_microsoft_calendar_platform_config

    return test_microsoft_calendar_platform_config(db)


@router.post("/integrations/cronofy/test")
def test_cronofy_integration_deprecated(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    return {"ok": False, "detail": "Cronofy is no longer supported for new connections."}


@router.post("/integrations/hubspot/test")
def test_hubspot_integration(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    from app.services.hubspot_connection_service import verify_hubspot_platform_config

    return verify_hubspot_platform_config(db)


@router.post("/integrations/pipedrive/test")
def test_pipedrive_integration(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    from app.services.pipedrive_connection_service import test_pipedrive_platform_config

    return test_pipedrive_platform_config(db)


@router.post("/integrations/zoho_crm/test")
def test_zoho_crm_integration(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    from app.services.zoho_crm_connection_service import test_zoho_crm_platform_config

    return test_zoho_crm_platform_config(db)


@router.post("/integrations/zoho_bookings/test")
def test_zoho_bookings_integration(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    from app.services.zoho_crm_connection_service import test_zoho_crm_platform_config

    result = test_zoho_crm_platform_config(db)
    result["detail"] = (
        "Zoho Bookings uses the same Zoho OAuth app as Zoho CRM. "
        + str(result.get("detail") or "")
    )
    return result


@router.post("/integrations/groq/test")
def test_groq_connection(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    try:
        diagnostics = GroqProviderService.diagnostics(db)
        return {"ok": True, "message": "Groq configuration is present for Whisper STT and Orpheus TTS.", **diagnostics}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Groq test failed: {e}") from e


@router.post("/integrations/deepinfra/test")
def test_deepinfra_connection(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    from app.services.providers.deepinfra_service import DeepInfraProviderService

    try:
        result = DeepInfraProviderService.test_connection(db)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"DeepInfra test failed: {e}") from e
    if not result.get("ok"):
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=result)
    try:
        from app.services.provider_settings import ProviderSettingsService

        ProviderSettingsService.upsert_platform_config(
            db,
            provider="deepinfra",
            is_enabled=True,
            config={
                "last_tested_at": result.get("last_tested_at"),
                "last_test_status": result.get("last_test_status"),
                "last_test_response_time_ms": result.get("response_time_ms"),
            },
        )
    except Exception:
        pass
    return result


@router.get("/integrations/deepinfra/moderation-models")
def list_deepinfra_moderation_models(_admin=Depends(require_cap(CAP_INTEGRATION))):
    from app.services.moderation import DEEPINFRA_MODERATION_MODELS

    return {"models": DEEPINFRA_MODERATION_MODELS}


@router.post("/integrations/deepinfra/test-moderation")
def test_deepinfra_moderation(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    from app.services.moderation import moderate_content

    sample = "Hello {first_name}, thank you for taking our short survey today. How was your recent visit?"
    try:
        result = moderate_content(sample, db=db)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Moderation test failed: {e}") from e
    return {"ok": bool(result.get("safe")), "sample": sample, "result": result}


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


@router.post("/integrations/gocardless/test")
def test_gocardless_connection(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    try:
        result = BillingService.test_gocardless_connection(db)
    except GoCardlessConfigError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except GoCardlessProviderError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"GoCardless test failed: {e}") from e
    if not result.get("ok"):
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=result)
    return result


@router.post("/integrations/stripe/test")
def test_stripe_connection(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    from app.services.stripe_payment_service import StripeConfigError, StripePaymentService, StripeProviderError

    try:
        return StripePaymentService.test_connection(db)
    except StripeConfigError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except StripeProviderError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Stripe test failed: {e}") from e


@router.post("/integrations/airwallex/test")
def test_airwallex_connection(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    from app.services.airwallex_payment_service import (
        AirwallexConfigError,
        AirwallexPaymentService,
        AirwallexProviderError,
    )

    try:
        return AirwallexPaymentService.test_connection(db)
    except AirwallexConfigError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except AirwallexProviderError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Airwallex test failed: {e}") from e


@router.get("/billing/subscriptions")
def admin_list_subscriptions(
    limit: int = 200,
    status: str | None = None,
    provider: str | None = None,
    search: str | None = None,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_BILLING)),
):
    rows = AdminBillingService.list_subscriptions(
        db,
        limit=limit,
        status=status,
        provider=provider,
        search=search,
    )
    return [
        {
            **row,
            "current_period_end": row["current_period_end"].isoformat() if row["current_period_end"] else None,
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
        }
        for row in rows
    ]


@router.get("/billing/subscriptions/pending-cash")
def admin_list_pending_cash_subscriptions(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_BILLING))):
    return BillingService.list_pending_cash_subscriptions(db)


@router.post("/billing/subscriptions/{org_id}/approve-cash")
def admin_approve_cash_subscription(
    org_id: str,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_BILLING)),
):
    from app.services.usage_wallet_service import UsageWalletService

    try:
        sub, plan = BillingService.approve_cash_subscription(db, org_id=org_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    UsageWalletService.sync_plan_limits(db, org_id=org_id, plan=plan, subscription=sub)
    return {
        "ok": True,
        "subscription": {
            "id": sub.id,
            "org_id": sub.org_id,
            "plan_id": sub.plan_id,
            "status": sub.status,
            "payment_provider": sub.payment_provider,
        },
        "plan": {"id": plan.id, "code": plan.code, "name": plan.name},
    }


@router.post("/billing/subscriptions/{org_id}/reject-cash")
def admin_reject_cash_subscription(
    org_id: str,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_BILLING)),
):
    try:
        sub = BillingService.reject_cash_subscription(db, org_id=org_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return {
        "ok": True,
        "subscription": {
            "id": sub.id,
            "org_id": sub.org_id,
            "plan_id": sub.plan_id,
            "status": sub.status,
        },
    }


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
    key_swap_hint = (
        "In the Vapi dashboard (API Keys): paste Public Key into Public key above, and Private API Key into "
        "Server API key (optional). Do not swap them — the wrong key type returns 401."
    )

    def _response_body(response: httpx.Response) -> dict:
        if response.headers.get("content-type", "").startswith("application/json"):
            body = response.json()
            return body if isinstance(body, dict) else {"raw": body}
        return {"raw_text": response.text}

    def _raise_vapi_failure(*, label: str, response: httpx.Response) -> None:
        body = _response_body(response)
        if response.status_code == 401:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "message": f"Vapi {label} rejected the key (401 Unauthorized)",
                    "hint": key_swap_hint,
                    "status_code": 401,
                    "payload": body,
                },
            )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"message": f"Vapi {label} check failed", "status_code": response.status_code, "payload": body},
        )

    def _verify_public_key_web() -> dict:
        """Public keys only work on POST /call/web (same as the browser SDK), not GET /assistant."""
        try:
            response = httpx.post(
                f"{base_url}/call/web",
                headers={"Authorization": f"Bearer {public_key}", "Content-Type": "application/json"},
                json={"assistantId": assistant_id},
                timeout=15.0,
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Vapi public key test failed (browser / Talk to us): {e}",
            ) from e
        if not response.is_success:
            _raise_vapi_failure(label="public key (browser / Talk to us)", response=response)
        return _response_body(response)

    def _verify_private_key_assistant() -> dict:
        try:
            response = httpx.get(
                f"{base_url}/assistant/{assistant_id}",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=15.0,
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Vapi private API key test failed (server): {e}",
            ) from e
        if not response.is_success:
            _raise_vapi_failure(label="private API key (server)", response=response)
        return _response_body(response)

    public_body = _verify_public_key_web()
    assistant_name = ""
    if isinstance(public_body.get("assistant"), dict):
        assistant_name = str(public_body["assistant"].get("name") or "").strip()

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Private API key is required. Paste it in Server API key (from Vapi dashboard → API Keys → Private).",
        )

    server_body = _verify_private_key_assistant()
    if not assistant_name:
        assistant_name = str(server_body.get("name") or "").strip()
    return {
        "ok": True,
        "verified": True,
        "message": "Public key (browser) and private API key (server) both verified.",
        "assistant_id": assistant_id,
        "assistant_name": assistant_name,
        "public_key_verified": True,
        "server_key_verified": True,
    }


@router.post("/integrations/telnyx/verify-key")
def verify_telnyx_api_key(payload: dict | None = None, _admin=Depends(require_cap(CAP_INTEGRATION))):
    """Test a pasted API key against Telnyx without saving (checks length + live auth)."""
    payload = payload or {}
    api_key = normalize_telnyx_api_key(str(payload.get("api_key") or ""))
    fp = telnyx_key_fingerprint(api_key)
    if not api_key:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="api_key is required")
    if fp.get("too_short") or not fp["looks_valid"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=telnyx_auth_hint(api_key))
    try:
        response = httpx.get(
            "https://api.telnyx.com/v2/phone_numbers",
            headers={"Authorization": f"Bearer {api_key}"},
            params={"page[size]": 1},
            timeout=15.0,
            verify=httpx_ssl_verify(),
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Telnyx API request failed: {e}") from e
    if response.status_code == 401:
        detail = "Telnyx rejected this API key (401)."
        try:
            body = response.json()
            errors = (body or {}).get("errors") if isinstance(body, dict) else None
            if isinstance(errors, list) and errors:
                detail = str(errors[0].get("detail") or detail)
        except Exception:
            pass
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail={"message": detail, **fp})
    if response.status_code >= 400:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Telnyx returned HTTP {response.status_code}")
    return {"ok": True, "message": f"API key verified ({fp['length']} characters). Click Save Telnyx to store it.", **fp}


@router.post("/integrations/telnyx/test")
def test_telnyx_connection(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    cfg, enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="telnyx")
    if not enabled:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Telnyx integration is disabled")
    config = ProviderSettingsService._validate_telnyx_config(cfg or {})
    try:
        api_key, key_source = require_telnyx_api_key(db, config)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    config["api_key"] = api_key
    missing = ProviderSettingsService._missing_fields("telnyx", config)
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Telnyx settings incomplete: missing {', '.join(missing)}",
        )

    warnings: list[str] = []
    voice_url = str(config.get("voice_webhook_url") or "").strip()
    webhook_base = str(config.get("webhook_base_url") or "").strip()
    if "localhost" in webhook_base.lower() or "127.0.0.1" in webhook_base:
        warnings.append(
            "Webhook base uses localhost — Telnyx cannot reach your machine. "
            "Run `ngrok http 8000`, paste the https URL in Webhook base URL, save, then paste the voice webhook in Telnyx."
        )

    telnyx_numbers: list[str] = []
    if voice_url:
        try:
            probe = httpx.get(voice_url, timeout=12.0, follow_redirects=True)
            if probe.status_code >= 400:
                local_hint = ""
                if "/telnyx/webhooks/voice" in voice_url:
                    try:
                        local = httpx.get("http://127.0.0.1:8000/telnyx/webhooks/voice", timeout=5.0)
                        if local.status_code == 200:
                            local_hint = " Local API is OK — fix your public URL (ngrok path must end with /telnyx/webhooks/voice)."
                    except Exception:
                        pass
                warnings.append(
                    f"Voice webhook probe returned HTTP {probe.status_code} (expected 200).{local_hint} "
                    f"URL tested: {voice_url}"
                )
        except Exception as e:
            warnings.append(f"Could not reach voice webhook ({voice_url}): {e}")

    messaging_url = str(config.get("messaging_webhook_url") or "").strip()
    if messaging_url:
        try:
            probe = httpx.get(messaging_url, timeout=12.0, follow_redirects=True)
            if probe.status_code >= 400:
                local_hint = ""
                if "/telnyx/webhooks/messages" in messaging_url:
                    try:
                        local = httpx.get("http://127.0.0.1:8000/telnyx/webhooks/messages", timeout=5.0)
                        if local.status_code == 200:
                            local_hint = " Local API is OK — fix your public URL (ngrok path must end with /telnyx/webhooks/messages)."
                    except Exception:
                        pass
                warnings.append(
                    f"Messaging webhook probe returned HTTP {probe.status_code} (expected 200).{local_hint} "
                    f"URL tested: {messaging_url}"
                )
        except Exception as e:
            warnings.append(f"Could not reach messaging webhook ({messaging_url}): {e}")

    try:
        telnyx_numbers = TelnyxVoiceAdapter.list_account_phone_numbers(api_key=api_key)
    except Exception:
        telnyx_numbers = []

    try:
        response = httpx.get(
            "https://api.telnyx.com/v2/phone_numbers",
            headers={"Authorization": f"Bearer {api_key}"},
            params={"page[size]": 1},
            timeout=15.0,
            verify=httpx_ssl_verify(),
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Telnyx API request failed: {e}") from e
    if response.status_code == 401:
        telnyx_detail = ""
        try:
            body = response.json()
            if isinstance(body, dict):
                errors = body.get("errors")
                if isinstance(errors, list) and errors and isinstance(errors[0], dict):
                    telnyx_detail = str(errors[0].get("detail") or errors[0].get("title") or "").strip()
        except Exception:
            pass
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "message": f"Telnyx API key rejected (401){f': {telnyx_detail}' if telnyx_detail else ''}",
                "hint": telnyx_auth_hint(api_key),
                "key_source": key_source,
                **telnyx_key_fingerprint(api_key),
            },
        )
    if response.status_code >= 400:
        body = response.json() if response.headers.get("content-type", "").startswith("application/json") else {"raw": response.text}
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"message": "Telnyx API check failed", "status_code": response.status_code, "payload": body},
        )

    message = "Telnyx API key OK. Voice and messaging webhook URLs are set."
    if warnings:
        message = f"{message} Warnings: {' | '.join(warnings)}"

    from app.services.telnyx_number_inventory_service import build_number_inventory

    inventory = build_number_inventory(api_key=api_key, config=config)
    telnyx_numbers = inventory.get("telnyx_phone_numbers") or telnyx_numbers
    inv_warnings = list(inventory.get("inventory_warnings") or [])
    configured_checks = inventory.get("configured_checks") or []
    for check in configured_checks:
        if check.get("status") != "ok" and check.get("issues"):
            inv_warnings.append(f"{check.get('number')} ({check.get('role')}): {', '.join(check.get('issues') or [])}")
    if inv_warnings:
        warnings = warnings + inv_warnings
        if inventory.get("ok") is False:
            message = f"{message} Number issues: {' | '.join(inv_warnings[:5])}"

    return {
        "ok": bool(inventory.get("ok", True)) and not any(w for w in warnings if "not on Telnyx account" in w),
        "message": message,
        "voice_webhook_url": voice_url,
        "messaging_webhook_url": messaging_url,
        "media_stream_url": str(config.get("media_stream_url") or ""),
        "warnings": warnings,
        "key_source": key_source,
        "telnyx_phone_numbers": telnyx_numbers,
        "account_inventory": inventory.get("account_inventory") or [],
        "configured_checks": configured_checks,
        "inventory_warnings": inv_warnings,
        **telnyx_key_fingerprint(api_key),
    }


@router.post("/integrations/telnyx/test-call")
def test_telnyx_call(payload: dict | None = None, db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    payload = payload or {}
    to_number = str(payload.get("to_number") or "").strip()
    if not to_number:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="to_number is required")

    cfg, enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="telnyx")
    if not enabled:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Telnyx integration is disabled")
    config = ProviderSettingsService._validate_telnyx_config(cfg or {})
    try:
        api_key, key_source = require_telnyx_api_key(db, config)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    config["api_key"] = api_key
    missing = ProviderSettingsService._missing_fields("telnyx", config)
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Telnyx settings incomplete: missing {', '.join(missing)}",
        )

    from_number = str(payload.get("from_number") or "").strip() or telnyx_outbound_caller_id(config)
    account_numbers: list[str] = []
    try:
        account_numbers = TelnyxVoiceAdapter.list_account_phone_numbers(api_key=api_key)
    except Exception:
        pass
    if account_numbers and from_number:
        try:
            from_norm = normalize_telnyx_e164(from_number)
            if from_norm not in account_numbers:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "message": f"From number {from_norm} is not on your Telnyx account.",
                        "hint": telnyx_caller_hint(from_norm, account_numbers),
                        "from_number": from_norm,
                        "telnyx_phone_numbers": account_numbers,
                    },
                )
            from_number = from_norm
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    result = TelnyxVoiceAdapter.start_outbound_call(
        to_number=to_number,
        from_number=from_number,
        config=config,
        client_state={"source": "admin_test_call"},
    )
    if not result.ok:
        message = result.detail or result.status or "Telnyx test call failed"
        hint = None
        if result.status == "invalid_caller_id" or (message and "origination" in message.lower()):
            hint = telnyx_caller_hint(from_number, account_numbers)
        elif "401" in message:
            hint = telnyx_auth_hint(api_key)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "message": message,
                "hint": hint,
                "from_number": from_number,
                "telnyx_phone_numbers": account_numbers,
                "key_source": key_source,
                **telnyx_key_fingerprint(api_key),
            },
        )
    return {
        "ok": True,
        "message": f"Test call queued ({result.status})",
        "external_id": result.external_id,
        "call_control_id": result.external_id,
        "from_number": from_number,
    }


@router.post("/integrations/telnyx/test-all-senders")
def test_telnyx_all_senders(payload: dict | None = None, db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    import time

    from app.services.telnyx_number_inventory_service import _collect_configured_senders

    payload = payload or {}
    to_number = str(payload.get("to_number") or "").strip()
    if not to_number:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="to_number is required")
    channels_raw = payload.get("channels")
    channels = [str(c).strip().lower() for c in channels_raw] if isinstance(channels_raw, list) else ["voice", "sms", "whatsapp"]
    channels = [c for c in channels if c in ("voice", "sms", "whatsapp")]

    cfg, enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="telnyx")
    if not enabled:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Telnyx integration is disabled")
    config = ProviderSettingsService._validate_telnyx_config(cfg or {})
    try:
        api_key, _key_source = require_telnyx_api_key(db, config)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    config["api_key"] = api_key

    senders = _collect_configured_senders(config)
    by_role: dict[str, list[dict[str, Any]]] = {"voice": [], "sms": [], "whatsapp": []}
    seen_role: dict[str, set[str]] = {"voice": set(), "sms": set(), "whatsapp": set()}
    for s in senders:
        role = s["role"]
        if role not in by_role or s["number"] in seen_role[role]:
            continue
        seen_role[role].add(s["number"])
        by_role[role].append(s)

    results: list[dict[str, Any]] = []

    if "voice" in channels:
        for sender in by_role["voice"]:
            from_num = sender["number"]
            result = TelnyxVoiceAdapter.start_outbound_call(
                to_number=to_number,
                from_number=from_num,
                config=config,
                client_state={"source": "admin_test_all_senders", "from": from_num},
            )
            results.append(
                {
                    "number": from_num,
                    "role": "voice",
                    "label": sender.get("label") or "",
                    "ok": result.ok,
                    "message": result.detail or result.status or ("queued" if result.ok else "failed"),
                    "external_id": result.external_id,
                    "call_control_id": result.external_id,
                }
            )
            time.sleep(1.0)

    if "sms" in channels:
        for sender in by_role["sms"]:
            from_num = sender["number"]
            result = TelnyxMessagingService.send_sms(
                db,
                to_number=to_number,
                body="VOXBULK Telnyx SMS test (all senders)",
                from_number=from_num,
            )
            results.append(
                {
                    "number": from_num,
                    "role": "sms",
                    "label": sender.get("label") or "",
                    "ok": result.ok,
                    "message": result.detail or result.status or ("queued" if result.ok else "failed"),
                    "external_id": result.external_id,
                }
            )
            time.sleep(0.5)

    if "whatsapp" in channels:
        from app.services.telnyx_whatsapp_template_sync_service import TelnyxWhatsappTemplateSyncService, send_template_id_for_row

        approved = TelnyxWhatsappTemplateSyncService.list_stored(db, approved_only=True)
        template_id = None
        template_name = None
        template_language = None
        if approved:
            first = approved[0]
            template_id = str(first.get("template_id") or "").strip() or None
            template_name = str(first.get("name") or "").strip() or None
            template_language = str(first.get("language") or "").strip() or None

        for sender in by_role["whatsapp"]:
            from_num = sender["number"]
            if not template_id and not template_name:
                results.append(
                    {
                        "number": from_num,
                        "role": "whatsapp",
                        "label": sender.get("label") or "",
                        "ok": False,
                        "message": "No approved WhatsApp template — sync templates first",
                        "external_id": None,
                    }
                )
                continue
            kwargs: dict[str, Any] = {
                "to_number": to_number,
                "body": "VOXBULK Telnyx WhatsApp test (all senders)",
                "from_number": from_num,
            }
            if template_id:
                kwargs["template_id"] = template_id
            if template_name:
                kwargs["template_name"] = template_name
            if template_language:
                kwargs["template_language"] = template_language
            result = TelnyxMessagingService.send_whatsapp(db, **kwargs)
            results.append(
                {
                    "number": from_num,
                    "role": "whatsapp",
                    "label": sender.get("label") or "",
                    "ok": result.ok,
                    "message": result.detail or result.status or ("queued" if result.ok else "failed"),
                    "external_id": result.external_id,
                }
            )
            time.sleep(0.5)

    ok_count = sum(1 for r in results if r.get("ok"))
    return {
        "ok": ok_count == len(results) if results else True,
        "message": f"Tested {len(results)} sender(s): {ok_count} OK, {len(results) - ok_count} failed",
        "results": results,
    }


@router.post("/integrations/telnyx/hangup")
def test_telnyx_hangup(payload: dict | None = None, db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    payload = payload or {}
    call_control_id = str(payload.get("call_control_id") or payload.get("external_id") or "").strip()
    if not call_control_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="call_control_id is required")

    cfg, enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="telnyx")
    if not enabled:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Telnyx integration is disabled")
    config = ProviderSettingsService._validate_telnyx_config(cfg or {})
    api_key, _key_source = resolve_telnyx_api_key(db, config)
    config["api_key"] = api_key
    missing = ProviderSettingsService._missing_fields("telnyx", config)
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Telnyx settings incomplete: missing {', '.join(missing)}",
        )

    result = TelnyxVoiceAdapter.hangup_call(call_control_id=call_control_id, config=config)
    if not result.ok:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=result.detail or result.status or "Telnyx hangup failed",
        )
    return {
        "ok": True,
        "message": "Call hangup sent",
        "call_control_id": call_control_id,
    }


@router.post("/integrations/telnyx/test-sms")
def test_telnyx_sms(payload: dict | None = None, db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    payload = payload or {}
    to_number = str(payload.get("to_number") or "").strip()
    body = str(payload.get("body") or "VOXBULK Telnyx SMS test").strip()
    if not to_number:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="to_number is required")

    cfg, _enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="telnyx")
    config = ProviderSettingsService._validate_telnyx_config(cfg or {})

    from_number = str(payload.get("from_number") or "").strip() or None
    messaging_profile_id = str(payload.get("messaging_profile_id") or "").strip() or None

    result = TelnyxMessagingService.send_sms(
        db,
        to_number=to_number,
        body=body,
        from_number=from_number,
        messaging_profile_id=messaging_profile_id,
    )
    if not result.ok:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=result.detail or result.status)
    return {
        "ok": True,
        "message": "SMS queued",
        "external_id": result.external_id,
        "status": result.status,
        "from_number": from_number,
    }


@router.get("/integrations/telnyx/whatsapp-templates")
def list_telnyx_whatsapp_templates(
    approved_only: bool = False,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    from app.services.telnyx_whatsapp_template_sync_service import TelnyxWhatsappTemplateSyncService

    return {
        "ok": True,
        "templates": TelnyxWhatsappTemplateSyncService.list_stored(db, approved_only=approved_only),
    }


@router.get("/integrations/telnyx/whatsapp-templates/health")
def telnyx_whatsapp_templates_health(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    """Check all four voxbulk_sales_* templates are synced and APPROVED."""
    import json

    from app.services.sales_whatsapp_telnyx_service import TELNYX_SALES_TEMPLATE_NAMES
    from app.services.sales_whatsapp_telnyx_service import url_button_index_from_components
    from app.services.telnyx_whatsapp_template_sync_service import (
        TelnyxWhatsappTemplateSyncService,
        send_template_id_for_row,
    )

    checks: list[dict] = []
    all_ok = True
    for sales_key, telnyx_name in TELNYX_SALES_TEMPLATE_NAMES.items():
        row = TelnyxWhatsappTemplateSyncService.get_for_sales_key(db, sales_key)
        approved = row is not None and str(row.status or "").upper() == "APPROVED"
        if not approved:
            all_ok = False
        components = None
        if row and row.components_json:
            try:
                components = json.loads(row.components_json)
            except json.JSONDecodeError:
                components = None
        checks.append(
            {
                "sales_key": sales_key,
                "telnyx_name": telnyx_name,
                "synced": row is not None,
                "approved": approved,
                "language": row.language if row else None,
                "send_template_id": send_template_id_for_row(row) if row else None,
                "has_url_button": url_button_index_from_components(components) is not None,
                "status": row.status if row else None,
                "rejection_reason": row.rejection_reason if row else None,
            }
        )
    return {
        "ok": all_ok,
        "ready": all_ok,
        "message": "All sales templates approved" if all_ok else "Sync Telnyx templates — one or more voxbulk_sales_* templates missing or not APPROVED",
        "templates": checks,
    }


@router.post("/integrations/telnyx/whatsapp-templates/sync")
def sync_telnyx_whatsapp_templates(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    from app.services.telnyx_whatsapp_template_sync_service import (
        TelnyxWhatsappTemplateSyncError,
        TelnyxWhatsappTemplateSyncService,
    )

    try:
        return TelnyxWhatsappTemplateSyncService.sync(db)
    except TelnyxWhatsappTemplateSyncError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.post("/integrations/telnyx/test-whatsapp")
def test_telnyx_whatsapp(payload: dict | None = None, db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    from app.services.telnyx_whatsapp_template_sync_service import (
        TelnyxWhatsappTemplateSyncService,
        send_template_id_for_row,
    )

    payload = payload or {}
    to_number = str(payload.get("to_number") or "").strip()
    body = str(payload.get("body") or "VOXBULK Telnyx WhatsApp test").strip()
    template_name = str(payload.get("template_name") or "").strip() or None
    template_id = str(payload.get("template_id") or "").strip() or None
    template_language = str(payload.get("template_language") or "").strip() or None
    if not to_number:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="to_number is required")

    cfg, _enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="telnyx")
    config = ProviderSettingsService._validate_telnyx_config(cfg or {})
    wa_from_override: str | None = str(payload.get("from_number") or "").strip() or None
    wa_profile_override: str | None = str(payload.get("messaging_profile_id") or "").strip() or None

    template_error = TelnyxMessagingService.validate_whatsapp_template_ref(template_name, template_id)
    if template_error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=template_error)

    used_default_template = False
    if not template_id and not template_name:
        approved = TelnyxWhatsappTemplateSyncService.list_stored(db, approved_only=True)
        if approved:
            first = approved[0]
            template_id = str(first.get("template_id") or "").strip() or None
            template_name = str(first.get("name") or "").strip() or None
            template_language = str(first.get("language") or "").strip() or template_language
            used_default_template = bool(template_id or template_name)

    synced = TelnyxWhatsappTemplateSyncService.resolve_for_send(
        db,
        template_name=template_name,
        template_id=template_id,
    )
    if synced is not None:
        if not template_id:
            template_id = send_template_id_for_row(synced)
        if not template_language:
            template_language = synced.language
        if not template_name:
            template_name = synced.name

    template_components = payload.get("template_components")
    if not template_components:
        if synced is not None:
            template_components = TelnyxWhatsappTemplateSyncService.build_components_for_row(synced)
        elif template_name and not template_id:
            from app.services.sales_whatsapp_telnyx_service import build_test_components_for_template_name

            template_components = build_test_components_for_template_name(template_name)

    components = template_components if isinstance(template_components, list) else None
    from app.services.sales_whatsapp_telnyx_service import resolve_whatsapp_template_languages

    langs: list[str] = []
    for candidate in (
        template_language,
        synced.language if synced else None,
        *resolve_whatsapp_template_languages(db),
    ):
        code = str(candidate or "").strip()
        if code and code not in langs:
            langs.append(code)
    if not langs:
        langs = ["en_US"]

    send_name = str(template_name or (synced.name if synced else "") or "").strip() or None
    send_tid = None
    if synced:
        send_tid = send_template_id_for_row(synced)
    elif template_id:
        send_tid = template_id

    def _send(**kwargs):
        if wa_from_override:
            kwargs["from_number"] = wa_from_override
        if wa_profile_override:
            kwargs["messaging_profile_id"] = wa_profile_override
        return TelnyxMessagingService.send_whatsapp(db, **kwargs)

    result = None
    if send_name:
        for lang in langs:
            attempt = _send(
                to_number=to_number,
                body=body,
                template_name=send_name,
                template_language=lang,
                template_components=components,
            )
            result = attempt
            if attempt.ok:
                break
    if (result is None or not result.ok) and send_tid:
        for lang in langs:
            attempt = _send(
                to_number=to_number,
                body=body,
                template_id=send_tid,
                template_language=lang,
                template_components=components,
            )
            result = attempt
            if attempt.ok:
                break
    if result is None:
        result = _send(to_number=to_number, body=body)
    if not result.ok:
        detail = result.detail or result.status
        if not (template_name or template_id):
            detail = (
                f"{detail} "
                "Free-form WhatsApp text only works within 24 hours after the recipient messages your business number. "
                "For a first contact, send a Meta-approved template instead (set template_name in the test request)."
            )
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=detail)

    log_id = None
    log_warning = None
    try:
        from sqlalchemy import select

        from app.models.organisation import Organisation

        cfg, _enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="telnyx")
        config = cfg if isinstance(cfg, dict) else {}
        org_id = str(config.get("messaging_org_id") or config.get("default_messaging_org_id") or "").strip()
        if not org_id:
            fallback = db.execute(select(Organisation.id).order_by(Organisation.created_at.asc()).limit(1)).scalar_one_or_none()
            org_id = str(fallback or "")
        wa_from = str(wa_from_override or config.get("whatsapp_from") or "").strip() or None
        if not org_id:
            log_warning = "Message sent but not saved to Messages — no organisation in database."
        else:
            log_body = body if not (template_name or template_id) else f"[template:{template_name or template_id}] {body}".strip()
            row = TelnyxMessagingService.log_outbound(
                db,
                org_id=org_id,
                to_number=to_number,
                from_number=wa_from,
                body=log_body,
                result=result,
            )
            log_id = row.id
    except Exception as exc:
        log_warning = f"Message sent but could not save to Messages log: {exc}"

    message = "WhatsApp message queued — see Messages below (delivery status updates via Telnyx webhook)."
    if used_default_template and template_name:
        message = f"WhatsApp queued using template “{template_name}”. {message}"
    elif not (template_name or template_id):
        message = (
            "WhatsApp queued as free-form text (24h window only). "
            "Sync templates and pick one for first contact. "
            + message
        )

    delivery_status = None
    delivery_error = None
    if result.external_id:
        try:
            live = TelnyxMessagingService.retrieve_message(db, result.external_id)
            if live.get("ok"):
                delivery_status = live.get("status")
                delivery_error = live.get("error_summary")
        except Exception:
            pass

    failed_delivery = str(delivery_status or "").lower() in {
        "delivery_failed",
        "failed",
        "undelivered",
        "rejected",
    }
    if failed_delivery:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=delivery_error or f"WhatsApp template delivery failed (status={delivery_status})",
        )

    return {
        "ok": True,
        "message": message,
        "external_id": result.external_id,
        "status": result.status,
        "delivery_status": delivery_status,
        "delivery_error": delivery_error,
        "template_id": send_tid or template_id,
        "template_name": send_name or template_name,
        "template_language": template_language or (synced.language if synced else None),
        "log_id": log_id,
        "warning": log_warning,
    }


@router.post("/integrations/meta_whatsapp/test")
def test_meta_whatsapp_connection(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    from app.services.meta_whatsapp_service import MetaWhatsappService

    result = MetaWhatsappService.test_connection(db)
    if not result.get("ok"):
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=result)
    return result


@router.get("/integrations/meta_whatsapp/templates")
def list_meta_whatsapp_templates(
    limit: int = 5,
    status: str = "APPROVED",
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    from app.services.meta_whatsapp_config_service import MetaWhatsappConfigError
    from app.services.meta_whatsapp_service import MetaWhatsappService

    try:
        return MetaWhatsappService.list_templates(db, limit=limit, status=status)
    except MetaWhatsappConfigError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/integrations/meta_whatsapp/test-send")
def test_meta_whatsapp_send(payload: dict | None = None, db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    from app.services.meta_whatsapp_config_service import MetaWhatsappConfigError
    from app.services.meta_whatsapp_service import MetaWhatsappService, MetaWhatsappServiceError

    payload = payload or {}
    to_number = str(payload.get("to_number") or "").strip()
    template_name = str(payload.get("template_name") or "").strip()
    template_language = str(payload.get("template_language") or "").strip()
    if not to_number:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="to_number is required")
    if not template_name:
        try:
            listed = MetaWhatsappService.list_templates(db, limit=1, status="APPROVED")
            rows = listed.get("templates") if isinstance(listed.get("templates"), list) else []
            if rows:
                template_name = str(rows[0].get("name") or "").strip()
                template_language = str(rows[0].get("language") or template_language or "en").strip()
        except (MetaWhatsappConfigError, MetaWhatsappServiceError):
            pass
    if not template_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="template_name is required")
    try:
        result = MetaWhatsappService.send_template(
            db,
            to_number=to_number,
            template_name=template_name,
            template_language=template_language or "en",
        )
    except (MetaWhatsappConfigError, MetaWhatsappServiceError) as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return result


@router.post("/integrations/meta_whatsapp/whatsapp-templates/sync")
def sync_meta_whatsapp_templates(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    from app.services.survey_whatsapp_template_service import SurveyWhatsappTemplateService
    from app.services.telnyx_whatsapp_template_sync_service import TelnyxWhatsappTemplateSyncError
    from app.services.whatsapp_provider_service import is_meta_whatsapp_primary

    if not is_meta_whatsapp_primary(db):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Meta WhatsApp is not enabled or fully configured — save credentials first",
        )
    try:
        return SurveyWhatsappTemplateService.sync_hub_from_meta(db)
    except TelnyxWhatsappTemplateSyncError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.post("/integrations/meta_whatsapp/whatsapp-templates/sync-step/{step}")
def sync_meta_whatsapp_templates_step(
    step: str,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    """Chunked sync so the admin UI can show 1/4, 2/4, … without browser timeout."""
    from app.services.survey_whatsapp_template_service import SurveyWhatsappTemplateService
    from app.services.telnyx_whatsapp_template_sync_service import (
        TelnyxWhatsappTemplateSyncError,
        TelnyxWhatsappTemplateSyncService,
    )
    from app.services.wa_template_closeout_service import WaTemplateCloseoutService
    from app.services.whatsapp_provider_service import is_meta_whatsapp_primary

    if not is_meta_whatsapp_primary(db):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Meta WhatsApp is not enabled or fully configured — save credentials first",
        )
    steps = ["catalog", "link_repair", "push", "cleanup"]
    key = str(step or "").strip().lower()
    if key not in steps:
        raise HTTPException(status_code=400, detail=f"Unknown step. Use one of: {', '.join(steps)}")
    idx = steps.index(key) + 1
    total = len(steps)
    try:
        if key == "catalog":
            catalog = TelnyxWhatsappTemplateSyncService.sync(db)
            result = {
                "ok": True,
                "step": key,
                "step_index": idx,
                "step_total": total,
                "message": f"Step {idx}/{total}: catalog synced ({catalog.get('synced') or 0} templates)",
                "catalog": {k: v for k, v in (catalog or {}).items() if k != "templates"},
            }
        elif key == "link_repair":
            link_s = WaTemplateCloseoutService.link_missing_survey_types(db)
            link_f = WaTemplateCloseoutService.link_missing_feedback_types(db)
            repair_s = WaTemplateCloseoutService.repair_all_survey_content(db, force_rejected=True)
            repair_f = WaTemplateCloseoutService.regenerate_all_feedback_templates(db)
            rename = WaTemplateCloseoutService.rename_promo_meta_names(db)
            relink = SurveyWhatsappTemplateService.relink_survey_templates(db)
            result = {
                "ok": True,
                "step": key,
                "step_index": idx,
                "step_total": total,
                "message": (
                    f"Step {idx}/{total}: linked {link_s.get('created', 0) + link_f.get('created', 0)} types, "
                    f"repaired {repair_s.get('repaired', 0)} survey / {repair_f.get('regenerated', 0)} feedback"
                ),
                "link_survey": link_s,
                "link_feedback": link_f,
                "survey_repair": repair_s,
                "feedback_repair": repair_f,
                "rename_promo": rename,
                "relink": relink,
            }
        elif key == "push":
            survey_push = WaTemplateCloseoutService.push_local_and_needs_resubmit(db)
            interview = WaTemplateCloseoutService.push_all_interview(db)
            feedback_push = WaTemplateCloseoutService.push_all_feedback(db)
            result = {
                "ok": True,
                "step": key,
                "step_index": idx,
                "step_total": total,
                "message": (
                    f"Step {idx}/{total}: pushed survey {survey_push.get('pushed', 0)}, "
                    f"interview {interview.get('pushed', 0)}, feedback {feedback_push.get('pushed', 0)}"
                ),
                "survey_push": survey_push,
                "interview": interview,
                "feedback_push": feedback_push,
            }
        else:
            meta_del = WaTemplateCloseoutService.delete_meta_rejected_ours(db)
            clean = WaTemplateCloseoutService.clean_dead_orphan_rejected(db, dry_run=False)
            catalog = TelnyxWhatsappTemplateSyncService.sync(db)
            result = {
                "ok": True,
                "step": key,
                "step_index": idx,
                "step_total": total,
                "message": (
                    f"Step {idx}/{total}: deleted {meta_del.get('deleted', 0)} Meta rejected, "
                    f"cleaned {clean.get('deleted', 0)} local orphans"
                ),
                "meta_rejected_deleted": meta_del,
                "clean": clean,
                "synced": catalog.get("synced"),
                "approved": sum(
                    1
                    for t in (catalog.get("templates") or [])
                    if str(t.get("status") or "").upper() == "APPROVED"
                ),
                "pending": sum(
                    1
                    for t in (catalog.get("templates") or [])
                    if str(t.get("status") or "").upper() == "PENDING"
                ),
                "rejected": sum(
                    1
                    for t in (catalog.get("templates") or [])
                    if str(t.get("status") or "").upper() == "REJECTED"
                ),
                "local_only": 0,
            }
        return result
    except TelnyxWhatsappTemplateSyncError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except Exception as exc:
        try:
            db.rollback()
        except Exception:
            pass
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.get("/integrations/meta_whatsapp/inbound-messages")
def list_meta_whatsapp_inbound_messages(
    limit: int = 50,
    date_from: str | None = None,
    date_to: str | None = None,
    from_number: str | None = None,
    to_number: str | None = None,
    q: str | None = None,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    rows = LogService.list_platform_message_logs(
        db,
        limit=max(limit, 200),
        date_from=date_from,
        date_to=date_to,
        from_number=from_number,
        to_number=to_number,
        q=q,
        provider="meta_whatsapp",
    )
    inbound = [r for r in rows if str(r.get("direction") or "").lower() in {"inbound", "in", "incoming"}]
    return {"ok": True, "messages": inbound[: max(1, min(limit, 200))]}


@router.get("/wa-messages/inbound")
def list_all_wa_inbound_messages(
    limit: int = 100,
    date_from: str | None = None,
    date_to: str | None = None,
    from_number: str | None = None,
    to_number: str | None = None,
    q: str | None = None,
    provider: str | None = None,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    """All inbound WhatsApp messages (Meta primary; includes legacy providers)."""
    rows = LogService.list_platform_message_logs(
        db,
        limit=500,
        date_from=date_from,
        date_to=date_to,
        from_number=from_number,
        to_number=to_number,
        q=q,
        provider=provider,
    )
    inbound = [r for r in rows if str(r.get("direction") or "").lower() in {"inbound", "in", "incoming"}]
    if not inbound:
        # Legacy rows may omit direction — include recent non-outbound logs.
        inbound = [r for r in rows if str(r.get("direction") or "").lower() not in {"outbound", "out"}]
    return {"ok": True, "messages": inbound[: max(1, min(limit, 200))]}


@router.get("/integrations/meta_whatsapp/webhook-probe")
def probe_meta_whatsapp_webhook(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    import httpx

    from app.services.meta_whatsapp_config_service import validate_meta_whatsapp_config

    cfg, enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="meta_whatsapp")
    config = validate_meta_whatsapp_config(cfg or {})
    webhook_url = str(config.get("webhook_url") or "").strip()
    verify_token = str(config.get("webhook_verify_token") or "").strip()
    if not webhook_url:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="webhook_url is not configured — save webhook base URL first")
    if not verify_token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="webhook_verify_token is not configured")
    params = {
        "hub.mode": "subscribe",
        "hub.verify_token": verify_token,
        "hub.challenge": "voxbulk_probe_ok",
    }
    try:
        with httpx.Client(timeout=10.0, follow_redirects=True) as client:
            response = client.get(webhook_url, params=params)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Webhook probe failed: {exc}") from exc
    body = (response.text or "").strip()
    ok = response.status_code == 200 and body == "voxbulk_probe_ok"
    return {
        "ok": ok,
        "status_code": response.status_code,
        "body": body[:200],
        "webhook_url": webhook_url,
        "enabled": enabled,
    }


@router.get("/integrations/telnyx/inbound-messages")
def list_telnyx_inbound_messages(
    limit: int = 50,
    date_from: str | None = None,
    date_to: str | None = None,
    from_number: str | None = None,
    to_number: str | None = None,
    q: str | None = None,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    rows = LogService.list_platform_message_logs(
        db,
        limit=limit,
        date_from=date_from,
        date_to=date_to,
        from_number=from_number,
        to_number=to_number,
        q=q,
    )
    return {"ok": True, "messages": rows[: max(1, min(limit, 200))]}


@router.get("/integrations/telnyx/phone-allowlist/defaults")
def telnyx_phone_allowlist_defaults(_admin=Depends(require_cap(CAP_INTEGRATION))):
    from app.services.telnyx_phone_allowlist_service import TelnyxPhoneAllowlistService

    return {"ok": True, **TelnyxPhoneAllowlistService.admin_view({})}


@router.get("/integrations/telnyx/messaging-destinations/defaults")
def telnyx_messaging_destinations_defaults(_admin=Depends(require_cap(CAP_INTEGRATION))):
    from app.services.telnyx_messaging_destinations_service import TelnyxMessagingDestinationsService

    return {"ok": True, **TelnyxMessagingDestinationsService.admin_view({})}


@router.post("/integrations/telnyx/messaging-destinations/sync-to-telnyx")
def sync_telnyx_messaging_destinations(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    from app.services.telnyx_messaging_destinations_service import TelnyxMessagingDestinationsService

    result = TelnyxMessagingDestinationsService.sync_to_telnyx_profiles(db)
    if not result.get("ok"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result.get("error") or result.get("message") or "Sync failed")
    return result


@router.get("/integrations/telnyx/messages/{message_id}")
def get_telnyx_message_detail(message_id: str, db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    """Fetch live delivery status + Meta/Telnyx errors from GET /v2/messages/{id}."""
    detail = TelnyxMessagingService.retrieve_message(db, message_id)
    if not detail.get("ok"):
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=detail.get("error") or "Telnyx message lookup failed")

    try:
        from sqlalchemy import select
        from app.models.whatsapp_log import WhatsAppLog

        row = db.execute(
            select(WhatsAppLog).where(WhatsAppLog.external_message_id == message_id).limit(1)
        ).scalar_one_or_none()
        if row is not None:
            status = str(detail.get("status") or row.status or "").strip()
            if status:
                row.status = status
            err_summary = str(detail.get("error_summary") or "").strip()
            if err_summary and "Delivery error:" not in str(row.body or ""):
                row.body = f"{row.body or ''}\nDelivery error: {err_summary}".strip()
            elif err_summary:
                row.body = str(row.body or "")
                if err_summary not in row.body:
                    row.body = f"{row.body}\nDelivery error: {err_summary}".strip()
            row.raw_payload = json.dumps(detail.get("raw") or detail, ensure_ascii=False)[:8000]
            db.add(row)
            db.commit()
    except Exception:
        pass

    return detail


@router.get("/social-login/providers")
def admin_list_social_login_providers(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    """Admin-safe read of social login provider config (no secrets)."""
    return [ProviderSettingsService.get_platform_config_admin_view(db, provider=p) for p in ["google", "apple", "linkedin"]]


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
    for k in ["client_id", "client_secret", "redirect_uri", "team_id", "key_id"]:
        if k in config and config[k] is not None and isinstance(config[k], str):
            config[k] = config[k].strip()
    if "private_key" in config and config["private_key"] is not None and isinstance(config["private_key"], str):
        config["private_key"] = config["private_key"].strip()

    try:
        ProviderSettingsService.upsert_platform_config(db, provider=provider, is_enabled=is_enabled, config=config)
        return ProviderSettingsService.get_platform_config_admin_view(db, provider=provider)
    except ProviderUnknown:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown provider")


@router.get("/organisations/summary")
def admin_organisations_summary(
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_ORG_OPS)),
):
    total = int(db.scalar(select(sa.func.count()).select_from(Organisation)) or 0)
    active = int(
        db.scalar(
            select(sa.func.count()).select_from(Organisation).where(Organisation.is_suspended.is_(False))
        )
        or 0
    )
    return {"total": total, "active": active}


@router.get("/organisations")
def admin_list_organisations(
    limit: int = 50,
    offset: int = 0,
    search: str | None = None,
    zone: str | None = None,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_ORG_OPS)),
):
    from app.services.market_zone import country_to_zone, format_wallet_pence, zone_label

    items = AdminOrganisationService.list_orgs(db, limit=limit, offset=offset, search=search, zone=zone)
    return [
        {
            "id": o.id,
            "name": o.name,
            "created_at": o.created_at,
            "is_suspended": o.is_suspended,
            "profile_notes": o.profile_notes,
            "category_id": getattr(o, "category_id", None),
            "category_name": getattr(o, "category_name", None),
            "city": getattr(o, "city", None),
            "country": getattr(o, "country", None),
            "contact_email": getattr(o, "contact_email", None),
            "contact_name": getattr(o, "contact_name", None),
            **AdminOrganisationService.summary_plan_dict(o),
            "branch_count": o.branch_count,
            "user_count": o.user_count,
            "patient_count": o.patient_count,
            "appointment_count": o.appointment_count,
            "recovery_job_count": o.recovery_job_count,
            "subscription_status": o.subscription_status,
            "wallet_balance_pence": int(o.wallet_balance_pence or 0),
            "market_zone": country_to_zone(getattr(o, "country", None)),
            "market_label": zone_label(country_to_zone(getattr(o, "country", None))),
            "wallet_balance_display": format_wallet_pence(int(o.wallet_balance_pence or 0), country_to_zone(getattr(o, "country", None))),
        }
        for o in items
    ]


@router.get("/organisations/control-center")
def admin_org_control_center_list(
    limit: int = 200,
    offset: int = 0,
    search: str | None = None,
    country: str | None = None,
    status: str | None = None,
    plan_code: str | None = None,
    payment_status: str | None = None,
    campaign_status: str | None = None,
    channel: str | None = None,
    overage_only: bool = False,
    invoices_due_only: bool = False,
    running_campaigns_only: bool = False,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_ORG_OPS)),
):
    from app.services.org_control_center_service import OrgControlCenterService

    return OrgControlCenterService.list_rows(
        db,
        limit=limit,
        offset=offset,
        search=search,
        country=country,
        status=status,
        plan_code=plan_code,
        payment_status=payment_status,
        campaign_status=campaign_status,
        channel=channel,
        overage_only=overage_only,
        invoices_due_only=invoices_due_only,
        running_campaigns_only=running_campaigns_only,
    )


@router.get("/organisations/{org_id}/control-center")
def admin_org_control_center_detail(
    org_id: str,
    invoice_search: str | None = None,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_ORG_OPS)),
):
    from app.services.org_control_center_service import OrgControlCenterService

    detail = OrgControlCenterService.get_detail(db, org_id, invoice_search=invoice_search)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    return detail


def _control_center_actor(principal) -> tuple[str | None, str | None]:
    return (
        getattr(principal, "user_id", None),
        getattr(principal, "email", None),
    )


@router.post("/organisations/{org_id}/control-center/wallet/credit")
def admin_occ_wallet_credit(
    org_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    principal=Depends(require_cap(CAP_ORG_OPS)),
):
    from app.services.org_control_center_actions_service import OrgControlCenterActionsService

    amount = int(payload.get("amount_minor") or payload.get("amount_pence") or 0)
    reason = str(payload.get("reason") or payload.get("note") or "Admin wallet credit").strip()
    actor_id, actor_email = _control_center_actor(principal)
    try:
        return OrgControlCenterActionsService.credit_wallet(
            db, org_id, amount_minor=amount, reason=reason, actor_user_id=actor_id, actor_email=actor_email
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/organisations/{org_id}/control-center/wallet/debit")
def admin_occ_wallet_debit(
    org_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    principal=Depends(require_cap(CAP_ORG_OPS)),
):
    from app.services.org_control_center_actions_service import OrgControlCenterActionsService

    amount = int(payload.get("amount_minor") or payload.get("amount_pence") or 0)
    reason = str(payload.get("reason") or payload.get("note") or "Admin wallet debit").strip()
    actor_id, actor_email = _control_center_actor(principal)
    try:
        return OrgControlCenterActionsService.debit_wallet(
            db, org_id, amount_minor=amount, reason=reason, actor_user_id=actor_id, actor_email=actor_email
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/organisations/{org_id}/control-center/wallet/refund")
def admin_occ_wallet_refund(
    org_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    principal=Depends(require_cap(CAP_ORG_OPS)),
):
    from app.services.org_control_center_actions_service import OrgControlCenterActionsService

    amount = int(payload.get("amount_minor") or payload.get("amount_pence") or 0)
    reason = str(payload.get("reason") or payload.get("note") or "Admin wallet refund").strip()
    actor_id, actor_email = _control_center_actor(principal)
    try:
        return OrgControlCenterActionsService.refund_wallet(
            db,
            org_id,
            amount_minor=amount,
            reason=reason,
            invoice_id=str(payload.get("invoice_id") or "").strip() or None,
            order_id=str(payload.get("order_id") or "").strip() or None,
            actor_user_id=actor_id,
            actor_email=actor_email,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/organisations/{org_id}/control-center/wallet/transactions/{transaction_id}/reverse")
def admin_occ_reverse_wallet_transaction(
    org_id: str,
    transaction_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    principal=Depends(require_cap(CAP_ORG_OPS)),
):
    from app.services.org_control_center_actions_service import OrgControlCenterActionsService

    reason = str(payload.get("reason") or payload.get("note") or "Admin wallet reversal").strip()
    actor_id, actor_email = _control_center_actor(principal)
    try:
        return OrgControlCenterActionsService.reverse_wallet_transaction(
            db,
            org_id,
            transaction_id,
            reason=reason,
            actor_user_id=actor_id,
            actor_email=actor_email,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/organisations/{org_id}/control-center/invoices/{invoice_id}/collect")
def admin_occ_collect_invoice(
    org_id: str,
    invoice_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    principal=Depends(require_cap(CAP_ORG_OPS)),
):
    from app.services.org_control_center_actions_service import OrgControlCenterActionsService

    method = str(payload.get("method") or "wallet").strip().lower()
    actor_id, actor_email = _control_center_actor(principal)
    try:
        return OrgControlCenterActionsService.collect_invoice_payment(
            db,
            org_id,
            invoice_id,
            method=method,
            actor_user_id=actor_id,
            actor_email=actor_email,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/organisations/{org_id}/control-center/credits/adjust")
def admin_occ_adjust_credits(
    org_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    principal=Depends(require_cap(CAP_ORG_OPS)),
):
    from app.services.org_control_center_actions_service import OrgControlCenterActionsService

    actor_id, actor_email = _control_center_actor(principal)
    try:
        return OrgControlCenterActionsService.adjust_credits(
            db,
            org_id,
            service_code=str(payload.get("service_code") or "survey"),
            delta=int(payload.get("delta") or 0),
            reason=str(payload.get("reason") or "").strip(),
            actor_user_id=actor_id,
            actor_email=actor_email,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/organisations/{org_id}/control-center/promo/apply")
def admin_occ_apply_promo(
    org_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    principal=Depends(require_cap(CAP_ORG_OPS)),
):
    from app.services.org_control_center_actions_service import OrgControlCenterActionsService

    actor_id, actor_email = _control_center_actor(principal)
    try:
        return OrgControlCenterActionsService.apply_promo(
            db,
            org_id,
            promo_code=str(payload.get("promo_code") or "").strip(),
            actor_user_id=actor_id,
            actor_email=actor_email,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.patch("/organisations/{org_id}/control-center/overage")
def admin_occ_set_overage(
    org_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    principal=Depends(require_cap(CAP_ORG_OPS)),
):
    from app.services.org_control_center_actions_service import OrgControlCenterActionsService

    actor_id, actor_email = _control_center_actor(principal)
    try:
        return OrgControlCenterActionsService.set_allow_overage(
            db,
            org_id,
            allow_overage=bool(payload.get("allow_overage")),
            reason=str(payload.get("reason") or "").strip() or None,
            actor_user_id=actor_id,
            actor_email=actor_email,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.patch("/organisations/{org_id}/control-center/billing-payment-provider")
def admin_occ_set_billing_payment_provider(
    org_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    principal=Depends(require_cap(CAP_ORG_OPS)),
):
    from app.services.org_control_center_actions_service import OrgControlCenterActionsService

    actor_id, actor_email = _control_center_actor(principal)
    try:
        return OrgControlCenterActionsService.set_billing_payment_provider(
            db,
            org_id,
            billing_payment_provider=payload.get("billing_payment_provider"),
            reason=str(payload.get("reason") or "").strip() or None,
            actor_user_id=actor_id,
            actor_email=actor_email,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.get("/billing/subscription-routing")
def admin_subscription_routing_policy(
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_BILLING)),
    org_id: str | None = None,
):
    from app.models.organisation import Organisation
    from app.services.payment_provider_router import (
        GOCARDLESS_COUNTRY_CODES,
        PaymentProviderRouter,
    )

    org = db.get(Organisation, org_id) if org_id else None
    return {
        "policy": "GoCardless Direct Debit when the organisation country supports it and GoCardless is enabled; otherwise Airwallex card checkout (Stripe as secondary fallback).",
        "platform": PaymentProviderRouter.subscription_options(db, None),
        "sample_routing": PaymentProviderRouter.routing_explain(db, org),
        "gocardless_country_count": len(GOCARDLESS_COUNTRY_CODES),
    }


@router.post("/organisations/{org_id}/control-center/invoices")
def admin_occ_create_invoice(
    org_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    principal=Depends(require_cap(CAP_ORG_OPS)),
):
    from app.services.org_control_center_actions_service import OrgControlCenterActionsService

    actor_id, actor_email = _control_center_actor(principal)
    try:
        return OrgControlCenterActionsService.create_invoice(
            db,
            org_id,
            amount_minor=int(payload.get("amount_minor") or payload.get("amount_pence") or 0),
            invoice_type=str(payload.get("invoice_type") or payload.get("kind") or "manual"),
            due_date=str(payload.get("due_date") or "") or None,
            note=str(payload.get("note") or payload.get("description") or "").strip() or None,
            actor_user_id=actor_id,
            actor_email=actor_email,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/organisations/{org_id}/control-center/invoices/{invoice_id}/mark-paid")
def admin_occ_mark_invoice_paid(
    org_id: str,
    invoice_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    principal=Depends(require_cap(CAP_ORG_OPS)),
):
    from app.services.org_control_center_actions_service import OrgControlCenterActionsService

    actor_id, actor_email = _control_center_actor(principal)
    try:
        return OrgControlCenterActionsService.mark_invoice_paid(
            db,
            org_id,
            invoice_id,
            note=str(payload.get("note") or "").strip() or None,
            actor_user_id=actor_id,
            actor_email=actor_email,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.patch("/organisations/{org_id}/control-center/invoices/{invoice_id}")
def admin_occ_edit_invoice(
    org_id: str,
    invoice_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    principal=Depends(require_cap(CAP_ORG_OPS)),
):
    from app.services.org_control_center_actions_service import OrgControlCenterActionsService

    actor_id, actor_email = _control_center_actor(principal)
    body = dict(payload or {})
    if body.get("amount_minor") is None and body.get("amount_pence") is not None:
        body["amount_minor"] = body.get("amount_pence")
    try:
        return OrgControlCenterActionsService.edit_invoice(
            db,
            org_id,
            invoice_id,
            payload=body,
            actor_user_id=actor_id,
            actor_email=actor_email,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/organisations/{org_id}/control-center/invoices/{invoice_id}/void")
def admin_occ_void_invoice(
    org_id: str,
    invoice_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    principal=Depends(require_cap(CAP_ORG_OPS)),
):
    from app.services.org_control_center_actions_service import OrgControlCenterActionsService

    actor_id, actor_email = _control_center_actor(principal)
    try:
        return OrgControlCenterActionsService.void_invoice(
            db,
            org_id,
            invoice_id,
            reason=str(payload.get("reason") or payload.get("note") or "").strip() or None,
            actor_user_id=actor_id,
            actor_email=actor_email,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/organisations/{org_id}/control-center/invoices/{invoice_id}/resend")
def admin_occ_resend_invoice(
    org_id: str,
    invoice_id: str,
    db: Session = Depends(get_db),
    principal=Depends(require_cap(CAP_ORG_OPS)),
):
    from app.services.org_control_center_actions_service import OrgControlCenterActionsService

    actor_id, actor_email = _control_center_actor(principal)
    try:
        return OrgControlCenterActionsService.resend_invoice_email(
            db, org_id, invoice_id, actor_user_id=actor_id, actor_email=actor_email
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/organisations/{org_id}/control-center/invoices/{invoice_id}/reissue")
def admin_occ_reissue_invoice(
    org_id: str,
    invoice_id: str,
    db: Session = Depends(get_db),
    principal=Depends(require_cap(CAP_ORG_OPS)),
):
    from app.services.org_control_center_actions_service import OrgControlCenterActionsService

    actor_id, actor_email = _control_center_actor(principal)
    try:
        return OrgControlCenterActionsService.reissue_invoice(
            db, org_id, invoice_id, actor_user_id=actor_id, actor_email=actor_email
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.get("/organisations/{org_id}/control-center/invoices/{invoice_id}/pdf")
def admin_occ_invoice_pdf(
    org_id: str,
    invoice_id: str,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_ORG_OPS)),
):
    from fastapi.responses import Response

    from app.models.billing_invoice import BillingInvoice
    from app.models.organisation import Organisation
    from app.services.invoice_service import InvoiceDocumentService

    invoice = db.get(BillingInvoice, invoice_id)
    if invoice is None or invoice.org_id != org_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
    org = db.get(Organisation, org_id)
    pdf_bytes = InvoiceDocumentService.render_pdf(db, invoice=invoice, org=org)
    number = invoice.invoice_number or invoice.id
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="invoice-{number}.pdf"'},
    )


@router.get("/billing/cancellation-requests")
def admin_list_cancellation_requests(
    limit: int = 100,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_ORG_OPS)),
):
    from app.services.subscription_cancellation_service import SubscriptionCancellationService

    return {"items": SubscriptionCancellationService.list_scheduled_cancellations(db, limit=limit)}


@router.get("/billing/refund-reviews")
def admin_list_refund_reviews(
    status: str | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_ORG_OPS)),
):
    from app.services.subscription_cancellation_service import SubscriptionCancellationService

    return {"items": SubscriptionCancellationService.list_refund_reviews(db, status=status, limit=limit)}


@router.get("/billing/requests")
def admin_list_billing_requests(
    status: str | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_ORG_OPS)),
):
    from app.services.subscription_cancellation_service import SubscriptionCancellationService

    return {"items": SubscriptionCancellationService.list_billing_requests(db, status=status, limit=limit)}


@router.get("/notifications/summary")
def admin_notifications_summary(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_ORG_OPS))):
    from app.services.notification_service import NotificationService

    return NotificationService.admin_pending_count(db)


@router.post("/organisations/{org_id}/control-center/cancellation/reverse")
def admin_occ_reverse_cancellation(
    org_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    principal=Depends(require_cap(CAP_ORG_OPS)),
):
    from app.services.subscription_cancellation_service import (
        SubscriptionCancellationError,
        SubscriptionCancellationService,
    )

    actor_id, _ = _control_center_actor(principal)
    try:
        return SubscriptionCancellationService.reverse_cancellation(
            db,
            org_id=org_id,
            admin_user_id=actor_id,
            note=str(payload.get("note") or payload.get("reason") or "").strip() or None,
        )
    except SubscriptionCancellationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/organisations/{org_id}/control-center/cancellation/immediate")
def admin_occ_immediate_cancellation(
    org_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    principal=Depends(require_cap(CAP_ORG_OPS)),
):
    from app.services.subscription_cancellation_service import (
        SubscriptionCancellationError,
        SubscriptionCancellationService,
    )

    actor_id, _ = _control_center_actor(principal)
    try:
        return SubscriptionCancellationService.admin_approve_immediate_cancel(
            db,
            org_id=org_id,
            admin_user_id=actor_id,
            issue_wallet_credit=bool(payload.get("issue_wallet_credit")),
            wallet_credit_pence=payload.get("wallet_credit_pence"),
            note=str(payload.get("note") or payload.get("reason") or "").strip() or None,
        )
    except SubscriptionCancellationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/organisations/{org_id}/control-center/refund-reviews/{review_id}/resolve")
def admin_occ_resolve_refund_review(
    org_id: str,
    review_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    principal=Depends(require_cap(CAP_ORG_OPS)),
):
    from app.models.billing_refund_review import BillingRefundReview
    from app.services.subscription_cancellation_service import (
        SubscriptionCancellationError,
        SubscriptionCancellationService,
    )

    review = db.get(BillingRefundReview, review_id)
    if review is None or review.org_id != org_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Refund review not found")
    actor_id, _ = _control_center_actor(principal)
    try:
        return SubscriptionCancellationService.resolve_refund_review(
            db,
            review_id=review_id,
            admin_user_id=actor_id,
            review_status=str(payload.get("review_status") or "completed"),
            admin_notes=str(payload.get("admin_notes") or payload.get("note") or "").strip() or None,
            approved_external_refund_pence=payload.get("approved_external_refund_pence"),
            issue_wallet_credit=bool(payload.get("issue_wallet_credit")),
            wallet_credit_pence=payload.get("wallet_credit_pence"),
        )
    except SubscriptionCancellationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/organisations/{org_id}/control-center/refund-reviews/{review_id}/reverse-wallet")
def admin_occ_reverse_cancellation_wallet_credit(
    org_id: str,
    review_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    principal=Depends(require_cap(CAP_ORG_OPS)),
):
    from app.models.billing_refund_review import BillingRefundReview
    from app.services.subscription_cancellation_service import (
        SubscriptionCancellationError,
        SubscriptionCancellationService,
    )

    review = db.get(BillingRefundReview, review_id)
    if review is None or review.org_id != org_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Refund review not found")
    actor_id, _ = _control_center_actor(principal)
    try:
        return SubscriptionCancellationService.reverse_wallet_credit(
            db,
            review_id=review_id,
            admin_user_id=actor_id,
            reason=str(payload.get("reason") or payload.get("note") or "").strip() or None,
        )
    except SubscriptionCancellationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/organisations/{org_id}/control-center/campaigns/{order_id}/{action}")
def admin_occ_campaign_action(
    org_id: str,
    order_id: str,
    action: str,
    db: Session = Depends(get_db),
    principal=Depends(require_cap(CAP_ORG_OPS)),
):
    from app.services.org_control_center_actions_service import OrgControlCenterActionsService

    actor_id, actor_email = _control_center_actor(principal)
    try:
        return OrgControlCenterActionsService.campaign_action(
            db, org_id, order_id, action, actor_user_id=actor_id, actor_email=actor_email
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/organisations/{org_id}/control-center/campaigns/stop-all")
def admin_occ_stop_all_campaigns(
    org_id: str,
    db: Session = Depends(get_db),
    principal=Depends(require_cap(CAP_ORG_OPS)),
):
    from app.services.org_control_center_actions_service import OrgControlCenterActionsService

    actor_id, actor_email = _control_center_actor(principal)
    return OrgControlCenterActionsService.stop_all_campaigns(
        db, org_id, actor_user_id=actor_id, actor_email=actor_email
    )


@router.post("/organisations/{org_id}/control-center/campaigns/{order_id}/retry-failed")
def admin_occ_retry_failed(
    org_id: str,
    order_id: str,
    db: Session = Depends(get_db),
    principal=Depends(require_cap(CAP_ORG_OPS)),
):
    from app.services.org_control_center_actions_service import OrgControlCenterActionsService

    actor_id, actor_email = _control_center_actor(principal)
    try:
        return OrgControlCenterActionsService.retry_failed_recipients(
            db, org_id, order_id, actor_user_id=actor_id, actor_email=actor_email
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/organisations/{org_id}/control-center/campaigns/purge-queue")
def admin_occ_purge_queue(
    org_id: str,
    db: Session = Depends(get_db),
    principal=Depends(require_cap(CAP_ORG_OPS)),
):
    from app.services.org_control_center_actions_service import OrgControlCenterActionsService

    actor_id, actor_email = _control_center_actor(principal)
    return OrgControlCenterActionsService.purge_queued_campaigns(
        db, org_id, actor_user_id=actor_id, actor_email=actor_email
    )


@router.patch("/organisations/{org_id}/control-center/notes")
def admin_occ_save_notes(
    org_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    principal=Depends(require_cap(CAP_ORG_OPS)),
):
    from app.services.org_control_center_actions_service import OrgControlCenterActionsService

    actor_id, actor_email = _control_center_actor(principal)
    return OrgControlCenterActionsService.save_profile_notes(
        db,
        org_id,
        profile_notes=payload.get("profile_notes"),
        actor_user_id=actor_id,
        actor_email=actor_email,
    )


@router.patch("/organisations/{org_id}/control-center/suspend")
def admin_occ_suspend(
    org_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    principal=Depends(require_cap(CAP_ORG_OPS)),
):
    from app.services.org_control_center_actions_service import OrgControlCenterActionsService

    actor_id, actor_email = _control_center_actor(principal)
    try:
        return OrgControlCenterActionsService.set_suspended(
            db,
            org_id,
            suspended=bool(payload.get("is_suspended")),
            reason=str(payload.get("reason") or "").strip() or None,
            actor_user_id=actor_id,
            actor_email=actor_email,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/organisations/{org_id}/control-center/delete-account")
def admin_occ_delete_account(
    org_id: str,
    payload: dict | None = None,
    db: Session = Depends(get_db),
    principal=Depends(require_cap(CAP_ORG_OPS)),
):
    from app.services.account_deletion_service import AccountDeletionError, AccountDeletionService

    actor_id, actor_email = _control_center_actor(principal)
    body = payload if isinstance(payload, dict) else {}
    confirm = str(body.get("confirm") or "").strip().upper()
    if confirm != "DELETE":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Type DELETE in confirm field')
    try:
        return AccountDeletionService.approve_and_complete(
            db,
            org_id,
            actor_user_id=actor_id,
            actor_email=actor_email,
            reason=str(body.get("reason") or "").strip() or None,
            admin_notes=str(body.get("admin_notes") or body.get("note") or "").strip() or None,
        )
    except AccountDeletionError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.get("/account-deletions")
def admin_list_account_deletions(
    status_filter: str = "pending",
    limit: int = 100,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_ORG_OPS)),
):
    from app.services.account_deletion_service import AccountDeletionService

    return {
        "items": AccountDeletionService.list_admin_queue(db, status_filter=status_filter, limit=limit),
        "pending_count": AccountDeletionService.pending_count(db),
    }


@router.get("/account-deletions/{request_id}")
def admin_get_account_deletion(
    request_id: str,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_ORG_OPS)),
):
    from app.services.account_deletion_service import AccountDeletionService

    data = AccountDeletionService.get_admin_request(db, request_id)
    if data is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deletion request not found")
    return data


@router.post("/account-deletions/{request_id}/complete")
def admin_complete_account_deletion(
    request_id: str,
    payload: dict | None = None,
    db: Session = Depends(get_db),
    principal=Depends(require_cap(CAP_ORG_OPS)),
):
    from app.services.account_deletion_service import AccountDeletionError, AccountDeletionService

    actor_id, actor_email = _control_center_actor(principal)
    body = payload if isinstance(payload, dict) else {}
    confirm = str(body.get("confirm") or "").strip().upper()
    if confirm != "DELETE":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Type DELETE in confirm field')
    data = AccountDeletionService.get_admin_request(db, request_id)
    if data is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deletion request not found")
    org_id = str(data.get("org_id") or "")
    try:
        return AccountDeletionService.approve_and_complete(
            db,
            org_id,
            actor_user_id=actor_id,
            actor_email=actor_email,
            reason=str(body.get("reason") or "").strip() or None,
            admin_notes=str(body.get("admin_notes") or body.get("note") or "").strip() or None,
            request_id=request_id,
        )
    except AccountDeletionError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.get("/organisations/{org_id}")
def admin_get_organisation(org_id: str, db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_ORG_OPS))):
    from app.services.market_zone import country_to_zone, format_wallet_pence, zone_label

    o = AdminOrganisationService.get_org_summary(db, org_id=org_id)
    if o is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    market_zone = country_to_zone(getattr(o, "country", None))
    wallet_pence = int(o.wallet_balance_pence or 0)
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
        **AdminOrganisationService.summary_plan_dict(o),
        "wallet_balance_pence": wallet_pence,
        "wallet_balance_gbp": f"£{(wallet_pence / 100):.2f}",
        "market_zone": market_zone,
        "market_label": zone_label(market_zone),
        "wallet_balance_display": format_wallet_pence(wallet_pence, market_zone),
        "deletion_status": str(getattr(o, "deletion_status", "active") or "active"),
        "deletion_requested_at": getattr(o, "deletion_requested_at", None),
    }


@router.get("/organisations/{org_id}/enabled-services")
def admin_get_org_enabled_services(
    org_id: str,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_ORG_OPS)),
):
    return admin_get_org_allowed_services(org_id, db, _admin)


@router.get("/organisations/{org_id}/allowed-services")
def admin_get_org_allowed_services(
    org_id: str,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_ORG_OPS)),
):
    from app.services.org_enabled_services import build_service_breakdown, org_service_maps, org_uses_platform_default_allowed
    from app.services.platform_services_settings_service import get_platform_default_allowed

    org = db.execute(select(Organisation).where(Organisation.id == org_id)).scalar_one_or_none()
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    allowed, enabled, visible = org_service_maps(org, db)

    return {
        "org_id": org.id,
        "org_name": org.name,
        "allowed_services": allowed,
        "enabled_services": enabled,
        "visible_services": visible,
        "uses_platform_default_allowed": org_uses_platform_default_allowed(org),
        "platform_default_allowed": get_platform_default_allowed(db),
        "service_breakdown": build_service_breakdown(allowed, enabled, visible),
    }


@router.patch("/organisations/{org_id}/enabled-services")
def admin_patch_org_enabled_services(
    org_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_ORG_OPS)),
):
    return admin_patch_org_allowed_services(org_id, payload, db, _admin)


@router.patch("/organisations/{org_id}/allowed-services")
def admin_patch_org_allowed_services(
    org_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_ORG_OPS)),
):
    from app.services.org_enabled_services import (
        AtLeastOneServiceRequiredError,
        build_service_breakdown,
        merge_admin_allowed_services,
        org_service_maps,
        org_uses_platform_default_allowed,
        serialize_allowed_services,
        serialize_enabled_services,
    )
    from app.services.platform_services_settings_service import get_platform_default_allowed

    org = db.execute(select(Organisation).where(Organisation.id == org_id)).scalar_one_or_none()
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    allowed, enabled, _ = org_service_maps(org, db)
    try:
        allowed, enabled = merge_admin_allowed_services(allowed, enabled, payload or {})
    except AtLeastOneServiceRequiredError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    org.allowed_services_json = serialize_allowed_services(allowed)
    org.enabled_services_json = serialize_enabled_services(enabled)
    db.add(org)
    db.commit()
    db.refresh(org)
    allowed, enabled, visible = org_service_maps(org, db)
    return {
        "ok": True,
        "allowed_services": allowed,
        "enabled_services": enabled,
        "visible_services": visible,
        "uses_platform_default_allowed": org_uses_platform_default_allowed(org),
        "platform_default_allowed": get_platform_default_allowed(db),
        "service_breakdown": build_service_breakdown(allowed, enabled, visible),
    }


@router.get("/platform/default-allowed-services")
def admin_get_platform_default_allowed_services(
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_ORG_OPS)),
):
    from app.services.platform_services_settings_service import ensure_row, get_platform_default_allowed

    ensure_row(db)
    return {"ok": True, "default_allowed_services": get_platform_default_allowed(db)}


@router.patch("/platform/default-allowed-services")
def admin_patch_platform_default_allowed_services(
    payload: dict,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_ORG_OPS)),
):
    from app.services.org_enabled_services import AtLeastOneServiceRequiredError
    from app.services.platform_services_settings_service import (
        get_platform_default_allowed,
        push_platform_default_to_orgs,
        update_platform_default_allowed,
    )

    services = payload.get("services") if isinstance(payload.get("services"), dict) else payload
    try:
        default_allowed = update_platform_default_allowed(db, services or {})
    except AtLeastOneServiceRequiredError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    reset_all = bool(payload.get("reset_all_orgs_to_platform_default"))
    pushed = 0
    if reset_all:
        pushed = push_platform_default_to_orgs(db, org_ids=None, clear_overrides_only=True)
    return {
        "ok": True,
        "default_allowed_services": default_allowed,
        "orgs_reset_to_platform_default": pushed,
    }


@router.patch("/organisations/bulk-allowed-services")
def admin_bulk_patch_org_allowed_services(
    payload: dict,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_ORG_OPS)),
):
    from app.services.org_enabled_services import AtLeastOneServiceRequiredError
    from app.services.platform_services_settings_service import bulk_patch_org_allowed_services

    apply_to_all = bool(payload.get("apply_to_all"))
    org_ids = None if apply_to_all else payload.get("org_ids")
    if org_ids is not None and not isinstance(org_ids, list):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="org_ids must be a list")
    if org_ids is not None:
        org_ids = [str(x).strip() for x in org_ids if str(x).strip()]
        if not org_ids and not apply_to_all:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Select at least one organisation")
    services = payload.get("services") if isinstance(payload.get("services"), dict) else payload
    reset_to_platform = bool(payload.get("reset_to_platform_default"))
    if not reset_to_platform and not isinstance(services, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="services patch required")
    try:
        updated = bulk_patch_org_allowed_services(
            db,
            org_ids=org_ids,
            services_patch=None if reset_to_platform else services,
            reset_to_platform_default=reset_to_platform,
        )
    except AtLeastOneServiceRequiredError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return {"ok": True, "updated_count": updated}


@router.patch("/organisations/{org_id}")
def admin_patch_organisation(
    org_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    principal=Depends(require_cap(CAP_ORG_OPS)),
):
    from app.services.org_audit_service import OrgAuditService

    org = db.execute(select(Organisation).where(Organisation.id == org_id)).scalar_one_or_none()
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    actor_id, actor_email = _control_center_actor(principal)
    if "name" in payload and payload["name"] is not None:
        name = str(payload["name"]).strip()
        if name:
            org.name = name
    if "finance_notes" in payload:
        v = payload.get("finance_notes")
        before = org.profile_notes
        after = str(v).strip() if v is not None and str(v).strip() != "" else None
        org.profile_notes = after
        OrgAuditService.record_admin(
            db,
            org_id=org_id,
            event_type="finance.notes_updated",
            action="Finance notes updated",
            entity_type="organisation",
            entity_id=org_id,
            actor_user_id=actor_id,
            actor_email=actor_email,
            metadata={"before": before, "after": after},
            commit=False,
        )
    elif "profile_notes" in payload:
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
    if "country" in payload:
        from app.services.org_billing_profile_service import sync_org_country_code

        sync_org_country_code(db, org, commit=False)
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
    from app.services.billing_lifecycle_service import BillingLifecycleService
    from app.services.usage_wallet_service import UsageWalletService

    plan_code = str(payload.get("plan_code") or "").strip()
    if not plan_code:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="plan_code required")
    org = db.execute(select(Organisation).where(Organisation.id == org_id)).scalar_one_or_none()
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    from app.services.billing_access_service import BillingAccessService

    plan_check = db.execute(select(Plan).where(Plan.code == plan_code)).scalar_one_or_none()
    if plan_check is not None and not BillingAccessService.is_valid_core_plan(db, plan_check):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Plan is not a Core Platform (C.P) plan. Use feedback-subscription for F.B plans.",
        )
    status_str = str(payload.get("status") or "").strip().lower()
    force_raw = bool(payload.get("force_raw"))
    if force_raw:
        plan = plan_check or db.execute(select(Plan).where(Plan.code == plan_code)).scalar_one_or_none()
        if plan is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown plan_code")
        if not BillingAccessService.is_valid_core_plan(db, plan):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Plan is not a Core Platform (C.P) plan",
            )
        sub = db.execute(
            select(Subscription)
            .where(Subscription.org_id == org_id, Subscription.service_code == "voxbulk")
            .order_by(Subscription.updated_at.desc(), Subscription.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        status_val = status_str or "active"
        if sub is None:
            sub = Subscription(
                id=str(uuid.uuid4()),
                org_id=org_id,
                plan_id=plan.id,
                service_code="voxbulk",
                status=status_val,
            )
            db.add(sub)
        else:
            sub.plan_id = plan.id
            sub.pending_plan_id = None
            sub.status = status_val
        db.commit()
        db.refresh(sub)
        UsageWalletService.sync_plan_limits(db, org_id=org_id, plan=plan, subscription=sub)
        return {"ok": True, "org_id": org_id, "plan_code": plan.code, "status": sub.status, "mode": "raw"}
    try:
        sub, plan, direction, extra = BillingLifecycleService.change_subscription_plan(
            db, org_id=org_id, plan_code=plan_code
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if status_str and status_str not in {"", "active"}:
        sub.status = status_str
        db.add(sub)
        db.commit()
        db.refresh(sub)
    UsageWalletService.sync_plan_limits(db, org_id=org_id, plan=plan, subscription=sub)
    return {
        "ok": True,
        "org_id": org_id,
        "plan_code": plan.code,
        "status": sub.status,
        "direction": direction,
        "billing_extra": extra,
        "mode": "lifecycle",
    }


@router.put("/organisations/{org_id}/feedback-subscription")
def admin_set_org_feedback_subscription(
    org_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_ORG_OPS)),
):
    from app.services.customer_feedback.billing_service import FeedbackBillingError, FeedbackBillingService

    plan_code = str(payload.get("plan_code") or "").strip()
    plan_id = str(payload.get("plan_id") or "").strip() or None
    if not plan_code and not plan_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="plan_code or plan_id required")
    org = db.execute(select(Organisation).where(Organisation.id == org_id)).scalar_one_or_none()
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    status_str = str(payload.get("status") or "active").strip().lower() or "active"
    try:
        sub, plan, mode = FeedbackBillingService.admin_assign_plan(
            db,
            org_id=org_id,
            plan_id=plan_id,
            plan_code=plan_code or None,
            status=status_str,
        )
    except FeedbackBillingError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {
        "ok": True,
        "org_id": org_id,
        "plan_code": plan.code,
        "plan_name": plan.name,
        "status": sub.status,
        "service_code": sub.service_code,
        "mode": mode,
    }


@router.post("/organisations/{org_id}/wallet/credit")
def admin_credit_org_wallet(
    org_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    principal=Depends(require_cap(CAP_ORG_OPS)),
):
    from app.models.organisation import Organisation
    from app.services.billing_lifecycle_service import BillingLifecycleService
    from app.services.market_zone import country_to_zone, format_wallet_pence
    from app.services.org_audit_service import OrgAuditService
    from app.services.payment_event_service import PaymentEventService
    from app.services.wallet_service import WalletService

    org = db.get(Organisation, org_id)
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    amount = int(payload.get("amount_pence") or payload.get("amount_minor") or 0)
    if amount <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="amount_pence must be positive")
    note = str(payload.get("note") or payload.get("reason") or "Admin wallet credit").strip()
    actor_id, actor_email = _control_center_actor(principal)
    try:
        result = BillingLifecycleService.admin_wallet_credit(
            db,
            org_id=org_id,
            amount_minor=amount,
            reason=note,
            created_by_user_id=actor_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    OrgAuditService.record_admin(
        db,
        org_id=org_id,
        event_type="wallet.credit",
        action="Admin wallet credit",
        entity_type="organisation",
        entity_id=org_id,
        actor_user_id=actor_id,
        actor_email=actor_email,
        detail=note,
        metadata={"amount_minor": amount, **(result or {})},
    )
    PaymentEventService.record_finance(
        db,
        org_id=org_id,
        client_email=org.contact_email or actor_email or "admin@voxbulk.com",
        event_kind="wallet.credit",
        actor_user_id=actor_id,
        metadata={"amount_minor": amount, "note": note},
    )
    db.refresh(org)
    market_zone = country_to_zone(getattr(org, "country", None))
    wallet_pence = WalletService.balance_minor(org)
    return {
        "ok": True,
        "org_id": org_id,
        "credited_pence": amount,
        "note": note or None,
        "wallet_balance_pence": wallet_pence,
        "wallet_balance_gbp": f"£{(wallet_pence / 100):.2f}",
        "wallet_balance_display": format_wallet_pence(wallet_pence, market_zone),
        **(result or {}),
    }


@router.get("/organisations/{org_id}/operations")
def admin_get_organisation_operations(
    org_id: str,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_ORG_OPS)),
):
    from app.models.plan import Plan
    from app.models.service_order import ServiceOrder
    from app.models.subscription import Subscription
    from app.services.billing_access_service import BillingAccessService
    from app.services.invoice_service import InvoiceService
    from app.services.market_zone import country_to_zone, format_wallet_pence, zone_currency_symbol, zone_label
    from app.services.platform_catalog_service import ServiceOrderService
    from app.services.subscription_summary_service import SubscriptionSummaryService
    from app.services.usage_wallet_service import UsageWalletService

    o = AdminOrganisationService.get_org_summary(db, org_id=org_id)
    if o is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")

    market_zone = country_to_zone(getattr(o, "country", None))
    usage_row = UsageWalletService.get_current(db, org_id)
    core_sub = BillingAccessService.get_valid_core_subscription(db, org_id)
    if usage_row is None and core_sub is not None:
        usage_row = UsageWalletService.bootstrap_from_plan(db, org_id=org_id, subscription=core_sub)

    running_orders = list(
        db.execute(
            select(ServiceOrder)
            .where(
                ServiceOrder.org_id == org_id,
                ServiceOrder.status.in_(("running", "paused", "draft")),
            )
            .order_by(ServiceOrder.updated_at.desc())
            .limit(50)
        ).scalars()
    )
    recent_orders = ServiceOrderService.list_orders(db, org_id=org_id, limit=30)
    invoices = InvoiceService.list_for_org(db, org_id=org_id, limit=30)

    users = list(
        db.execute(
            select(User.id, User.email, User.is_active, User.is_superuser, OrganisationMembership.role, OrganisationMembership.created_at)
            .join(OrganisationMembership, OrganisationMembership.user_id == User.id)
            .where(OrganisationMembership.org_id == org_id)
            .order_by(OrganisationMembership.created_at.desc())
            .limit(200)
        ).all()
    )

    wallet_pence = int(o.wallet_balance_pence or 0)
    subscription_finance = None
    feedback_subscription_finance = None
    cancellation_preview = None
    org_row = db.get(Organisation, org_id)
    if org_row is not None:
        from app.services.billing_finance_service import BillingFinanceService

        sub_summary = SubscriptionSummaryService.build_org_summary(db, org_id)
        subscription_finance = sub_summary.get("core")
        feedback_subscription_finance = sub_summary.get("feedback")
        if core_sub is not None:
            try:
                cancellation_preview = BillingFinanceService.cancellation_preview(db, org_id)
            except ValueError:
                cancellation_preview = None

    return {
        "organisation": {
            "id": o.id,
            "name": o.name,
            "created_at": o.created_at,
            "is_suspended": o.is_suspended,
            "country": getattr(o, "country", None),
            "city": getattr(o, "city", None),
            "contact_name": getattr(o, "contact_name", None),
            "contact_email": getattr(o, "contact_email", None),
            "contact_phone": getattr(o, "contact_phone", None),
            **AdminOrganisationService.summary_plan_dict(o),
            "user_count": o.user_count,
            "branch_count": o.branch_count,
            "wallet_balance_pence": wallet_pence,
            "wallet_balance_display": format_wallet_pence(wallet_pence, market_zone),
            "market_zone": market_zone,
            "market_label": zone_label(market_zone),
            "currency_symbol": zone_currency_symbol(market_zone),
        },
        "usage": UsageWalletService.summary_dict(usage_row) if usage_row else None,
        "running_orders": [ServiceOrderService.order_to_admin_dict(db, r) for r in running_orders],
        "recent_orders": [ServiceOrderService.order_to_admin_dict(db, r) for r in recent_orders],
        "invoices": [InvoiceService.invoice_to_dict(db, inv) for inv in invoices],
        "users": [
            {
                "user_id": uid,
                "email": email,
                "is_active": is_active,
                "is_superuser": is_superuser,
                "role": role,
                "linked_at": created_at,
            }
            for uid, email, is_active, is_superuser, role, created_at in users
        ],
        "subscription_finance": subscription_finance,
        "feedback_subscription_finance": feedback_subscription_finance,
        "cancellation_preview": cancellation_preview,
    }


@router.get("/organisations/{org_id}/invoices")
def admin_list_org_invoices(
    org_id: str,
    limit: int = 50,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_ORG_OPS)),
):
    from app.services.invoice_service import InvoiceService

    org = db.get(Organisation, org_id)
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    rows = InvoiceService.list_for_org(db, org_id=org_id, limit=limit)
    return [InvoiceService.invoice_to_dict(db, r) for r in rows]


@router.get("/organisations/{org_id}/users")
def admin_list_org_users(org_id: str, db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_ORG_OPS))):
    rows = list(
        db.execute(
            select(
                User.id,
                User.email,
                User.is_active,
                User.is_superuser,
                User.deletion_status,
                User.deletion_requested_at,
                OrganisationMembership.role,
                OrganisationMembership.created_at,
            )
            .join(OrganisationMembership, OrganisationMembership.user_id == User.id)
            .where(OrganisationMembership.org_id == org_id)
            .order_by(OrganisationMembership.created_at.desc())
            .limit(200)
        ).all()
    )
    from app.services.account_deletion_service import AccountDeletionService

    return [
        {
            "user_id": uid,
            "email": email,
            "is_active": is_active,
            "is_superuser": is_superuser,
            "deletion_status": del_status,
            "deletion_label": AccountDeletionService._status_label(del_status),
            "deletion_requested_at": del_req_at,
            "role": role,
            "linked_at": created_at,
        }
        for uid, email, is_active, is_superuser, del_status, del_req_at, role, created_at in rows
    ]


@router.get("/organisations/{org_id}/users/{user_id}/activity")
def admin_org_user_activity(
    org_id: str,
    user_id: str,
    limit: int = 100,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_ORG_OPS)),
):
    from app.models.service_order import ServiceOrder
    from app.models.support_ticket import SupportTicket
    from app.services.org_audit_service import OrgAuditService
    from app.services.platform_catalog_service import ServiceOrderService

    mem = db.execute(
        select(OrganisationMembership).where(
            OrganisationMembership.org_id == org_id,
            OrganisationMembership.user_id == user_id,
        )
    ).scalar_one_or_none()
    if mem is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not in this organisation")
    user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    audit_events = OrgAuditService.list_events_for_user(db, org_id, user_id, limit=limit)
    orders = list(
        db.execute(
            select(ServiceOrder)
            .where(ServiceOrder.org_id == org_id, ServiceOrder.user_id == user_id)
            .order_by(ServiceOrder.updated_at.desc())
            .limit(max(1, min(int(limit or 100), 100)))
        ).scalars()
    )
    tickets = list(
        db.execute(
            select(SupportTicket)
            .where(SupportTicket.organisation_id == org_id, SupportTicket.created_by_user_id == user_id)
            .order_by(SupportTicket.updated_at.desc())
            .limit(max(1, min(int(limit or 100), 50)))
        ).scalars()
    )
    return {
        "user": {
            "user_id": user.id,
            "email": user.email,
            "is_active": user.is_active,
            "role": mem.role,
            "linked_at": mem.created_at,
            "account_created_at": user.created_at,
        },
        "audit_events": audit_events,
        "service_orders": [ServiceOrderService.order_to_admin_dict(db, o) for o in orders],
        "support_tickets": [
            {
                "id": t.id,
                "subject": t.subject,
                "status": t.status,
                "category": t.category,
                "created_at": t.created_at,
                "updated_at": t.updated_at,
            }
            for t in tickets
        ],
        "counts": {
            "audit_events": len(audit_events),
            "service_orders": len(orders),
            "support_tickets": len(tickets),
        },
    }


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


@router.post("/organisations/{org_id}/users/{user_id}/hard-delete-test")
def admin_hard_delete_org_user_test(
    org_id: str,
    user_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_ORG_OPS)),
):
    """DEV/OPS TEST — wipe billing, detach FK refs, hard-delete user; delete solo org if applicable."""
    from sqlalchemy.exc import IntegrityError

    from app.services.user_hard_delete_service import HARD_DELETE_CONFIRM, UserHardDeleteError, hard_delete_user

    body = payload if isinstance(payload, dict) else {}
    if str(body.get("confirm") or "").strip() != HARD_DELETE_CONFIRM:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f'Type {HARD_DELETE_CONFIRM} in confirm field',
        )
    try:
        report = hard_delete_user(
            db,
            user_id,
            org_id=org_id,
            delete_solo_orgs=bool(body.get("delete_solo_org", True)),
            delete_service_orders=bool(body.get("delete_service_orders", True)),
        )
        db.commit()
        return {"ok": True, "report": report}
    except UserHardDeleteError as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Database blocked delete: {getattr(e.orig, 'args', (str(e),))[0]}",
        ) from e
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


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
    if created_new_user:
        from app.core.database import get_sessionmaker
        from app.services.product_email_triggers import ProductEmailTriggers

        with get_sessionmaker()() as s2:
            ProductEmailTriggers.send_new_user_welcome_safe(
                s2,
                to_email=str(existing.email),
                organisation_name=str(org_ent.name or ""),
            )
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
    from app.models.agent import AgentAssignment, AgentDefinition
    from app.models.organisation_ai_config import OrganisationServiceCatalogItem
    from app.models.service_api import SupportedServiceAPI

    obj = db.execute(select(Category).where(Category.id == category_id)).scalar_one_or_none()
    if obj is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
    slug = str(obj.slug or "").strip()
    # Detach orgs and dependent rows so FK delete succeeds.
    db.execute(
        sa.update(Organisation)
        .where(Organisation.category_id == category_id)
        .values(category_id=None)
    )
    db.execute(
        sa.update(AgentDefinition)
        .where(AgentDefinition.category_id == category_id)
        .values(category_id=None)
    )
    db.execute(
        sa.update(AgentAssignment)
        .where(AgentAssignment.category_id == category_id)
        .values(category_id=None)
    )
    if slug:
        db.execute(delete(OrganisationServiceCatalogItem).where(OrganisationServiceCatalogItem.category_slug == slug))
        db.execute(delete(SupportedServiceAPI).where(SupportedServiceAPI.category_slug == slug))
    db.delete(obj)
    db.commit()
    return {"ok": True}


@router.get("/onboarding/settings")
def admin_get_onboarding_settings(
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_ORG_OPS)),
):
    from app.services.onboarding_settings_service import OnboardingSettingsService

    row = OnboardingSettingsService.get_settings(db)
    return {"settings": OnboardingSettingsService.settings_out(row)}


@router.put("/onboarding/settings")
def admin_update_onboarding_settings(
    payload: dict,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_ORG_OPS)),
):
    from datetime import datetime

    from app.services.onboarding_settings_service import OnboardingSettingsService

    row = OnboardingSettingsService.get_settings(db)
    if "auto_approve_promo_signups" in payload:
        row.auto_approve_promo_signups = bool(payload.get("auto_approve_promo_signups"))
    row.updated_at = datetime.utcnow()
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"settings": OnboardingSettingsService.settings_out(row)}


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
            "promo_code": r.promo_code,
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

    from app.services.onboarding_settings_service import OnboardingSettingsService

    try:
        OnboardingSettingsService.approve_request(
            db,
            r,
            user=u,
            note=str((payload or {}).get("note") or "") or None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

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


@router.get("/dashboard/provider-balances")
def admin_dashboard_provider_balances(
    db: Session = Depends(get_db),
    _admin=Depends(require_platform_admin),
):
    from app.services.provider_balance_service import get_provider_balances

    return get_provider_balances(db)


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
        "appointment_id": job.dentally_appointment_id,
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

    appt = db.execute(select(DentallyAppointment).where(DentallyAppointment.id == job.dentally_appointment_id, DentallyAppointment.org_id == job.org_id)).scalar_one_or_none()
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
    from app.services.billing_access_service import BillingAccessService
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
        if BillingAccessService.is_valid_core_plan(db, p)
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


@router.get("/billing/calls-cost")
def admin_billing_calls_cost(
    date_range: str = "last_30_days",
    page: int = 1,
    page_size: int = 25,
    transport: str | None = None,
    search: str | None = None,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_BILLING)),
):
    from app.services.telnyx_call_cost_service import list_call_costs

    try:
        return list_call_costs(
            db,
            date_range=date_range,
            page=page,
            page_size=page_size,
            transport=transport,
            search=search,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@router.get("/billing/calls-cost/{session_id}")
def admin_billing_call_cost_detail(
    session_id: str,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_BILLING)),
):
    from app.services.telnyx_call_cost_service import get_call_cost_detail

    try:
        return get_call_cost_detail(db, session_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/billing/conversations/{conversation_id}/insights")
def admin_billing_conversation_insights(
    conversation_id: str,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_BILLING)),
):
    from app.services.telnyx_call_cost_service import get_call_insights_by_conversation

    try:
        return get_call_insights_by_conversation(db, conversation_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/billing/calls-cost/{session_id}/insights")
def admin_billing_call_insights(
    session_id: str,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_BILLING)),
):
    from app.services.telnyx_call_cost_service import get_call_insights_by_session

    try:
        return get_call_insights_by_session(db, session_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/telnyx/conversations/{conversation_id}/insights")
def admin_telnyx_conversation_insights(
    conversation_id: str,
    db: Session = Depends(get_db),
    _admin=Depends(require_platform_admin),
):
    from app.services.telnyx_conversation_service import fetch_conversation_insights

    payload = fetch_conversation_insights(db, conversation_id)
    if payload.get("status") == "invalid":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(payload.get("error") or "Invalid id"))
    return payload


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
    from app.services.billing_finance_service import BillingFinanceService

    return BillingFinanceService.list_payment_events(db, limit=limit)


@router.get("/billing/payment-events")
def admin_list_payment_events(
    limit: int = 200,
    provider: str | None = None,
    status: str | None = None,
    org_id: str | None = None,
    event_kind: str | None = None,
    duplicates_only: bool = False,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_BILLING)),
):
    from app.services.billing_finance_service import BillingFinanceService

    return {"items": BillingFinanceService.list_payment_events(
        db,
        limit=limit,
        provider=provider,
        status=status,
        org_id=org_id,
        event_kind=event_kind,
        duplicates_only=duplicates_only,
    )}


@router.get("/billing/refunds")
def admin_list_billing_refunds(
    limit: int = 200,
    status: str | None = None,
    org_id: str | None = None,
    provider: str | None = None,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_BILLING)),
):
    from app.services.billing_finance_service import BillingFinanceService

    return {"items": BillingFinanceService.list_refunds(
        db, limit=limit, status=status, org_id=org_id, provider=provider
    )}


@router.get("/billing/wallet-ledger")
def admin_list_wallet_ledger(
    limit: int = 200,
    org_id: str | None = None,
    kind: str | None = None,
    direction: str | None = None,
    search: str | None = None,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_BILLING)),
):
    from app.services.billing_finance_service import BillingFinanceService

    return {"items": BillingFinanceService.list_wallet_ledger(
        db, limit=limit, org_id=org_id, kind=kind, direction=direction, search=search
    )}


@router.get("/billing/exceptions")
def admin_list_billing_exceptions(
    limit: int = 200,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_BILLING)),
):
    from app.services.billing_exceptions_service import BillingExceptionsService

    items = BillingExceptionsService.list_exceptions(db, limit=limit)
    return {"items": items, "summary": BillingExceptionsService.summary(db)}


@router.get("/organisations/{org_id}/billing/cancellation-preview")
def admin_org_cancellation_preview(
    org_id: str,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_ORG_OPS)),
):
    from app.services.billing_finance_service import BillingFinanceService

    try:
        return BillingFinanceService.cancellation_preview(db, org_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@router.get("/organisations/{org_id}/billing/upgrade-preview")
def admin_org_upgrade_preview(
    org_id: str,
    plan_code: str,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_ORG_OPS)),
):
    from app.services.billing_finance_service import BillingFinanceService

    try:
        return BillingFinanceService.upgrade_preview(db, org_id, new_plan_code=plan_code)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.get("/billing/ops-summary")
def admin_billing_ops_summary(
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_BILLING)),
):
    from app.services.billing_exceptions_service import BillingExceptionsService
    from app.services.billing_finance_service import BillingFinanceService

    from app.models.organisation import Organisation
    from sqlalchemy import func, select

    exceptions = BillingExceptionsService.summary(db)
    refunds = BillingFinanceService.list_refunds(db, limit=500, status="under_review")
    failed_events = BillingFinanceService.list_payment_events(db, limit=200, status="failed")
    wallet_liability_minor = int(
        db.execute(select(func.coalesce(func.sum(Organisation.wallet_balance_pence), 0))).scalar_one() or 0
    )
    return {
        "pending_refund_queue": len(refunds),
        "failed_payments": len(failed_events),
        "billing_exceptions": exceptions,
        "wallet_liability_minor": wallet_liability_minor,
    }


@router.get("/billing/invoices/recent")
def admin_list_recent_billing_invoices(
    limit: int = 100,
    status: str | None = None,
    provider: str | None = None,
    search: str | None = None,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_BILLING)),
):
    from app.services.invoice_service import InvoiceService

    rows = InvoiceService.list_admin(db, limit=limit, status=status, provider=provider, search=search)
    return [InvoiceService.invoice_to_dict(db, r) for r in rows]


@router.get("/billing/invoices/{invoice_id}")
def admin_get_billing_invoice(
    invoice_id: str,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_BILLING)),
):
    from app.models.billing_invoice import BillingInvoice
    from app.services.invoice_service import InvoiceService

    row = db.get(BillingInvoice, invoice_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
    return InvoiceService.invoice_to_dict(db, row)


@router.get("/billing/invoices/{invoice_id}/html", response_class=HTMLResponse)
def admin_get_billing_invoice_html(
    invoice_id: str,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_BILLING)),
):
    from app.models.billing_invoice import BillingInvoice
    from app.services.invoice_service import InvoiceDocumentService

    row = db.get(BillingInvoice, invoice_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
    return InvoiceDocumentService.render_html(db, invoice=row)


@router.get("/billing/invoices/{invoice_id}/pdf")
def admin_get_billing_invoice_pdf(
    invoice_id: str,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_BILLING)),
):
    from app.models.billing_invoice import BillingInvoice
    from app.services.invoice_service import InvoiceDocumentService

    row = db.get(BillingInvoice, invoice_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
    try:
        pdf_bytes = InvoiceDocumentService.render_pdf(db, invoice=row)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)) from e
    number = row.invoice_number or row.id
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="invoice-{number}.pdf"'},
    )


@router.post("/billing/invoices/{invoice_id}/dispute")
def admin_dispute_billing_invoice(
    invoice_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_BILLING)),
):
    from app.services.billing_lifecycle_service import BillingLifecycleService
    from app.services.invoice_service import InvoiceService

    try:
        row = BillingLifecycleService.set_invoice_disputed(
            db, invoice_id=invoice_id, note=str(payload.get("note") or "").strip() or None
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return InvoiceService.invoice_to_dict(db, row)


@router.post("/billing/invoices/{invoice_id}/resolve-dispute")
def admin_resolve_billing_invoice_dispute(
    invoice_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_BILLING)),
):
    from app.services.billing_lifecycle_service import BillingLifecycleService
    from app.services.invoice_service import InvoiceService

    try:
        row = BillingLifecycleService.clear_invoice_dispute(
            db, invoice_id=invoice_id, note=str(payload.get("note") or "").strip() or None
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return InvoiceService.invoice_to_dict(db, row)


@router.post("/billing/invoices/{invoice_id}/bank-refund")
def admin_bank_refund_billing_invoice(
    invoice_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    principal=Depends(require_cap(CAP_BILLING)),
):
    from app.services.billing_lifecycle_service import BillingLifecycleService

    try:
        credit_note = BillingLifecycleService.record_bank_refund(
            db,
            invoice_id=invoice_id,
            note=str(payload.get("note") or "").strip() or None,
            created_by_user_id=getattr(principal, "user_id", None),
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return {
        "ok": True,
        "credit_note_id": credit_note.id,
        "credit_note_number": credit_note.credit_note_number,
        "refund_method": credit_note.refund_method,
        "amount_minor": credit_note.amount_minor,
    }


def _admin_billing_invoice_row(db: Session, invoice_id: str):
    from app.services.invoice_service import InvoiceService

    row = InvoiceService.resolve_for_admin(db, invoice_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
    return row


# BILLING_INVOICE_VOID_ROUTE_V1 — deploy marker: POST /admin/billing/invoices/{id}/void
@router.patch("/billing/invoices/{invoice_id}")
def admin_edit_billing_invoice(
    invoice_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    principal=Depends(require_cap(CAP_BILLING)),
):
    from app.services.org_control_center_actions_service import OrgControlCenterActionsService

    row = _admin_billing_invoice_row(db, invoice_id)
    actor_id, actor_email = _control_center_actor(principal)
    body = dict(payload or {})
    if body.get("amount_minor") is None and body.get("amount_pence") is not None:
        body["amount_minor"] = body.get("amount_pence")
    try:
        return OrgControlCenterActionsService.edit_invoice(
            db,
            row.org_id,
            row.id,
            payload=body,
            actor_user_id=actor_id,
            actor_email=actor_email,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/billing/invoices/{invoice_id}/void")
def admin_void_billing_invoice(
    invoice_id: str,
    payload: dict | None = None,
    db: Session = Depends(get_db),
    principal=Depends(require_cap(CAP_BILLING)),
):
    from app.services.org_control_center_actions_service import OrgControlCenterActionsService

    row = _admin_billing_invoice_row(db, invoice_id)
    actor_id, actor_email = _control_center_actor(principal)
    body = dict(payload or {})
    try:
        return OrgControlCenterActionsService.void_invoice(
            db,
            row.org_id,
            row.id,
            reason=str(body.get("reason") or body.get("note") or "").strip() or None,
            actor_user_id=actor_id,
            actor_email=actor_email,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/billing/invoices/{invoice_id}/mark-paid")
def admin_mark_billing_invoice_paid(
    invoice_id: str,
    payload: dict | None = None,
    db: Session = Depends(get_db),
    principal=Depends(require_cap(CAP_BILLING)),
):
    from app.services.org_control_center_actions_service import OrgControlCenterActionsService

    row = _admin_billing_invoice_row(db, invoice_id)
    actor_id, actor_email = _control_center_actor(principal)
    note = str((payload or {}).get("note") or "").strip() or None
    try:
        return OrgControlCenterActionsService.mark_invoice_paid(
            db,
            row.org_id,
            row.id,
            note=note,
            actor_user_id=actor_id,
            actor_email=actor_email,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/billing/invoices/{invoice_id}/stop-dd-collection")
def admin_stop_dd_collection(
    invoice_id: str,
    payload: dict | None = None,
    db: Session = Depends(get_db),
    principal=Depends(require_cap(CAP_BILLING)),
):
    from app.services.invoice_lifecycle_service import InvoiceLifecycleError, InvoiceLifecycleService

    row = _admin_billing_invoice_row(db, invoice_id)
    actor_id, actor_email = _control_center_actor(principal)
    note = str((payload or {}).get("reason") or (payload or {}).get("note") or "").strip() or None
    try:
        invoice = InvoiceLifecycleService.stop_dd_collection(
            db,
            row,
            reason=note,
            actor_user_id=actor_id,
            actor_email=actor_email,
        )
        return {"ok": True, "invoice_id": invoice.id, "status": invoice.status}
    except InvoiceLifecycleError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.get("/billing/invoices/failed")
def admin_list_failed_invoices(
    db: Session = Depends(get_db),
    limit: int = 100,
    _admin=Depends(require_cap(CAP_BILLING)),
):
    from app.models.billing_invoice import BillingInvoice
    from app.services.invoice_service import InvoiceService

    cap = max(1, min(int(limit or 100), 300))
    rows = list(
        db.execute(
            select(BillingInvoice)
            .where(BillingInvoice.status.in_(("failed", "past_due", "collecting")))
            .order_by(BillingInvoice.created_at.desc())
            .limit(cap)
        )
        .scalars()
        .all()
    )
    return {"items": [InvoiceService.invoice_to_dict(db, inv) for inv in rows]}


@router.post("/billing/invoices/{invoice_id}/collect")
def admin_collect_billing_invoice(
    invoice_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    principal=Depends(require_cap(CAP_BILLING)),
):
    from app.services.org_control_center_actions_service import OrgControlCenterActionsService

    row = _admin_billing_invoice_row(db, invoice_id)
    method = str(payload.get("method") or "wallet").strip().lower()
    actor_id, actor_email = _control_center_actor(principal)
    try:
        return OrgControlCenterActionsService.collect_invoice_payment(
            db,
            row.org_id,
            row.id,
            method=method,
            actor_user_id=actor_id,
            actor_email=actor_email,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/billing/organisations/{org_id}/wallet-credit")
def admin_wallet_credit_org(
    org_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    principal=Depends(require_cap(CAP_BILLING)),
):
    from app.models.organisation import Organisation
    from app.services.billing_lifecycle_service import BillingLifecycleService
    from app.services.org_audit_service import OrgAuditService
    from app.services.payment_event_service import PaymentEventService

    org = db.get(Organisation, org_id)
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    amount = int(payload.get("amount_minor") or payload.get("amount_pence") or 0)
    reason = str(payload.get("reason") or "Admin wallet credit").strip()
    actor_id, actor_email = _control_center_actor(principal)
    try:
        result = BillingLifecycleService.admin_wallet_credit(
            db,
            org_id=org_id,
            amount_minor=amount,
            reason=reason,
            created_by_user_id=actor_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    OrgAuditService.record_admin(
        db,
        org_id=org_id,
        event_type="wallet.credit",
        action="Admin wallet credit",
        entity_type="organisation",
        entity_id=org_id,
        actor_user_id=actor_id,
        actor_email=actor_email,
        detail=reason,
        metadata={"amount_minor": amount, **(result or {})},
    )
    PaymentEventService.record_finance(
        db,
        org_id=org_id,
        client_email=org.contact_email or actor_email or "admin@voxbulk.com",
        event_kind="wallet.credit",
        actor_user_id=actor_id,
        metadata={"amount_minor": amount, "note": reason},
    )
    return {"ok": True, **result}


@router.post("/billing/invoices/{invoice_id}/resend-email")
def admin_resend_billing_invoice_email(
    invoice_id: str,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_BILLING)),
):
    from app.models.billing_invoice import BillingInvoice
    from app.services.billing_event_email_service import BillingEventEmailService

    row = db.get(BillingInvoice, invoice_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
    ok, err = BillingEventEmailService.send_invoice_email(db, invoice=row)
    if ok:
        row.emailed_at = datetime.utcnow()
        db.add(row)
        db.commit()
        db.refresh(row)
    return {"ok": ok, "sent": ok, "error": err}


@router.get("/billing/vat-rates")
def admin_list_vat_rates(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_BILLING))):
    from app.services.country_vat_service import CountryVatService

    return [CountryVatService.to_dict(r) for r in CountryVatService.list_all(db)]


@router.put("/billing/vat-rates/{country_code}")
def admin_upsert_vat_rate(
    country_code: str,
    payload: dict,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_BILLING)),
):
    from app.services.country_vat_service import CountryVatService

    try:
        row = CountryVatService.upsert(
            db,
            country_code=country_code,
            country_name=str(payload.get("country_name") or country_code),
            vat_rate_percent=float(payload.get("vat_rate_percent") or 0),
            is_enabled=bool(payload.get("is_enabled", True)),
            notes=str(payload.get("notes") or "") or None,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return CountryVatService.to_dict(row)


@router.delete("/billing/vat-rates/{country_code}")
def admin_delete_vat_rate(
    country_code: str,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_BILLING)),
):
    from app.services.country_vat_service import CountryVatService

    if not CountryVatService.delete(db, country_code):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="VAT rate not found")
    return {"ok": True}


@router.get("/billing/invoices/recent-legacy")
def admin_list_recent_billing_invoices_legacy(
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

