from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status

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
from app.services.meta_webhook_security import MetaWebhookVerificationError, verify_meta_webhook_signature
from app.services.meta_whatsapp_config_service import validate_meta_whatsapp_config
from app.services.meta_whatsapp_inbound_service import MetaWhatsappInboundService

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
logger = logging.getLogger(__name__)

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


def _meta_whatsapp_verify_token(db: Session) -> str:
    cfg, _enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="meta_whatsapp")
    config = validate_meta_whatsapp_config(cfg or {})
    return str(config.get("webhook_verify_token") or "").strip()


def _meta_whatsapp_app_secret(db: Session) -> str:
    cfg, _enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="meta_whatsapp")
    config = validate_meta_whatsapp_config(cfg or {})
    return str(config.get("app_secret") or "").strip()


@router.get("/meta/whatsapp")
@router.head("/meta/whatsapp")
async def meta_whatsapp_webhook_verify(
    request: Request,
    db: Session = Depends(get_db),
    hub_mode: str | None = Query(default=None, alias="hub.mode"),
    hub_verify_token: str | None = Query(default=None, alias="hub.verify_token"),
    hub_challenge: str | None = Query(default=None, alias="hub.challenge"),
):
    if request.method == "HEAD":
        return Response(status_code=status.HTTP_200_OK)
    mode = str(hub_mode or "").strip()
    token = str(hub_verify_token or "").strip()
    challenge = str(hub_challenge or "").strip()
    expected = _meta_whatsapp_verify_token(db)
    if mode == "subscribe" and expected and token == expected and challenge:
        return Response(content=challenge, media_type="text/plain", status_code=status.HTTP_200_OK)
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Webhook verification failed")


@router.post("/meta/whatsapp")
async def meta_whatsapp_webhook(
    request: Request,
    db: Session = Depends(get_db),
):
    from app.services.telnyx_webhook_security import webhook_signature_required

    raw_body = await request.body()
    app_secret = _meta_whatsapp_app_secret(db)
    signature_valid = False
    if not app_secret:
        if webhook_signature_required():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Meta WhatsApp app_secret is not configured",
            )
        logger.warning("meta_whatsapp_webhook_skipped_verify_no_app_secret")
    else:
        try:
            verify_meta_webhook_signature(
                app_secret=app_secret,
                raw_body=raw_body,
                signature_header=request.headers.get("X-Hub-Signature-256"),
            )
            signature_valid = True
        except MetaWebhookVerificationError as exc:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON payload") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid payload")
    WebhookEventService.persist_received(
        db,
        provider="meta_whatsapp",
        raw_body=raw_body,
        external_event_id=None,
        signature_valid=signature_valid,
    )
    # Dev/test may process without signature; production always requires valid signature.
    if webhook_signature_required() and not signature_valid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unsigned Meta webhook rejected")
    result = MetaWhatsappInboundService.handle_webhook(db, payload=payload)
    return result
