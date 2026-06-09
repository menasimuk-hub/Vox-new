from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from app.core.config import get_settings
from app.core.security import (
    verify_gocardless_signature_hex,
    verify_hmac_sha256_base64,
)
from app.workers.sync_tasks import handle_gocardless_webhook, handle_vapi_webhook
from app.core.database import get_db
from sqlalchemy.orm import Session
from fastapi import Depends
from app.services.provider_settings import ProviderSettingsService
from app.services.recovery_service import WebhookEventService

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

def _missing_sig() -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing signature")


def _invalid_sig() -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid signature")


@router.post("/vapi")
async def vapi_webhook(request: Request, db: Session = Depends(get_db)):
    settings = get_settings()
    body = await request.body()
    sig = request.headers.get("X-Vapi-Signature")
    if not sig:
        raise _missing_sig()
    ok = verify_hmac_sha256_base64(secret=settings.vapi_webhook_secret, body=body, signature_b64=sig)
    if not ok:
        raise _invalid_sig()
    event, created = WebhookEventService.persist_received(
        db, provider="vapi", raw_body=body, external_event_id=None, signature_valid=True
    )
    if created:
        handle_vapi_webhook.delay(event_id=event.id)
    return {"status": "ok"}


@router.post("/gocardless")
async def gocardless_webhook(request: Request, db: Session = Depends(get_db)):
    settings = get_settings()
    body = await request.body()
    sig = request.headers.get("Webhook-Signature")
    if not sig:
        raise _missing_sig()
    secret = settings.gocardless_webhook_secret
    try:
        cfg, enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="gocardless")
        if enabled and isinstance(cfg, dict) and str(cfg.get("webhook_secret") or "").strip():
            secret = str(cfg["webhook_secret"]).strip()
    except Exception:
        pass
    ok = verify_gocardless_signature_hex(secret=secret, body=body, signature_hex=sig)
    if not ok:
        raise _invalid_sig()
    external_event_id = WebhookEventService.extract_external_event_id("gocardless", body)
    event, created = WebhookEventService.persist_received(
        db, provider="gocardless", raw_body=body, external_event_id=external_event_id, signature_valid=True
    )
    if created:
        handle_gocardless_webhook.delay(event_id=event.id)
    return {"status": "ok"}


@router.post("/stripe")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    from app.services.stripe_payment_service import (
        StripeConfigError,
        StripePaymentService,
        StripeProviderError,
    )

    body = await request.body()
    sig = request.headers.get("Stripe-Signature")
    if not sig:
        raise _missing_sig()
    try:
        event = StripePaymentService.verify_webhook_signature(db, payload=body, signature_header=sig)
    except (StripeConfigError, StripeProviderError) as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e)) from e
    WebhookEventService.persist_received(
        db, provider="stripe", raw_body=body, external_event_id=str(event.get("id") or "") or None, signature_valid=True
    )
    return StripePaymentService.handle_webhook_event(db, event)


@router.post("/airwallex")
async def airwallex_webhook(request: Request, db: Session = Depends(get_db)):
    from app.services.airwallex_payment_service import (
        AirwallexConfigError,
        AirwallexPaymentService,
        AirwallexProviderError,
    )

    body = await request.body()
    timestamp = request.headers.get("x-timestamp") or ""
    sig = request.headers.get("x-signature") or ""
    if not sig or not timestamp:
        raise _missing_sig()
    try:
        event = AirwallexPaymentService.verify_webhook_signature(db, payload=body, timestamp=timestamp, signature=sig)
    except (AirwallexConfigError, AirwallexProviderError) as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e)) from e
    WebhookEventService.persist_received(
        db, provider="airwallex", raw_body=body, external_event_id=str(event.get("id") or "") or None, signature_valid=True
    )
    return AirwallexPaymentService.handle_webhook_event(db, event)
