"""Stripe card payments for wallet top-ups (PaymentIntents via REST, no SDK dependency)."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.models.organisation import Organisation
from app.services.billing_currency import resolve_org_currency
from app.services.provider_settings import ProviderSettingsService

logger = logging.getLogger(__name__)

STRIPE_API_BASE = "https://api.stripe.com/v1"


class StripeConfigError(ValueError):
    pass


class StripeProviderError(RuntimeError):
    pass


class StripePaymentService:
    @staticmethod
    def get_config(db: Session) -> dict[str, Any]:
        cfg, enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="stripe")
        if not enabled or not cfg:
            raise StripeConfigError("Stripe is not enabled in admin settings")
        secret = str(cfg.get("secret_key") or "").strip()
        if not secret:
            raise StripeConfigError("Stripe secret key is not configured")
        return cfg

    @staticmethod
    def is_available(db: Session) -> bool:
        try:
            StripePaymentService.get_config(db)
            return True
        except StripeConfigError:
            return False

    @staticmethod
    def publishable_key(db: Session) -> str:
        cfg = StripePaymentService.get_config(db)
        return str(cfg.get("publishable_key") or "").strip()

    @staticmethod
    def _request(db: Session, method: str, path: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
        cfg = StripePaymentService.get_config(db)
        secret = str(cfg.get("secret_key") or "").strip()
        try:
            resp = httpx.request(
                method,
                f"{STRIPE_API_BASE}{path}",
                data=data,
                auth=(secret, ""),
                timeout=30.0,
            )
        except httpx.HTTPError as exc:
            raise StripeProviderError(f"Stripe request failed: {exc}") from exc
        if resp.status_code >= 400:
            try:
                err = resp.json().get("error", {})
                message = err.get("message") or resp.text[:300]
            except Exception:
                message = resp.text[:300]
            logger.warning("stripe_api_error status=%s path=%s message=%s", resp.status_code, path, message)
            raise StripeProviderError(f"Stripe error: {message}")
        return resp.json()

    @staticmethod
    def test_connection(db: Session) -> dict[str, Any]:
        """Verify the secret key by reading the account balance."""
        cfg = StripePaymentService.get_config(db)
        balance = StripePaymentService._request(db, "GET", "/balance")
        available = balance.get("available") or []
        return {
            "ok": True,
            "environment": str(cfg.get("environment") or "test"),
            "livemode": bool(balance.get("livemode")),
            "currencies": sorted({str(b.get("currency") or "").upper() for b in available if b.get("currency")}),
        }

    @staticmethod
    def create_topup_intent(db: Session, org: Organisation, *, amount_minor: int) -> dict[str, Any]:
        currency = resolve_org_currency(db, org, persist=True)
        intent = StripePaymentService._request(
            db,
            "POST",
            "/payment_intents",
            data={
                "amount": int(amount_minor),
                "currency": currency.lower(),
                "automatic_payment_methods[enabled]": "true",
                "metadata[voxbulk_org_id]": org.id,
                "metadata[voxbulk_kind]": "wallet_topup",
                "description": f"VoxBulk wallet top-up — {org.name}",
            },
        )
        return {
            "provider": "stripe",
            "payment_intent_id": str(intent.get("id") or ""),
            "client_secret": str(intent.get("client_secret") or ""),
            "publishable_key": StripePaymentService.publishable_key(db),
            "amount_minor": int(intent.get("amount") or amount_minor),
            "currency": currency,
            "status": str(intent.get("status") or ""),
        }

    @staticmethod
    def retrieve_intent(db: Session, payment_intent_id: str) -> dict[str, Any]:
        return StripePaymentService._request(db, "GET", f"/payment_intents/{payment_intent_id}")

    @staticmethod
    def confirm_topup(db: Session, org: Organisation, *, payment_intent_id: str) -> dict[str, Any]:
        """Verify the PaymentIntent succeeded server-side and credit the wallet exactly once."""
        from app.services.wallet_service import WalletService

        pid = str(payment_intent_id or "").strip()
        if not pid:
            raise StripeProviderError("payment_intent_id required")
        intent = StripePaymentService.retrieve_intent(db, pid)
        meta = intent.get("metadata") or {}
        if str(meta.get("voxbulk_org_id") or "") != org.id:
            raise StripeProviderError("Payment does not belong to this organisation")
        status = str(intent.get("status") or "")
        if status != "succeeded":
            return {"ok": False, "status": status, "credited": False}
        if WalletService.has_transaction_for_reference(db, provider="stripe", provider_reference=pid):
            return {"ok": True, "status": status, "credited": False, "duplicate": True}
        amount = int(intent.get("amount_received") or intent.get("amount") or 0)
        if amount <= 0:
            raise StripeProviderError("Stripe payment has no captured amount")
        WalletService.credit(
            db,
            org,
            amount_minor=amount,
            kind="topup",
            provider="stripe",
            provider_reference=pid,
            description="Wallet top-up via Stripe",
        )
        StripePaymentService._issue_topup_invoice(db, org, amount_minor=amount, reference=pid, provider="stripe")
        return {"ok": True, "status": status, "credited": True, "amount_minor": amount}

    @staticmethod
    def _issue_topup_invoice(db: Session, org: Organisation, *, amount_minor: int, reference: str, provider: str) -> None:
        try:
            from app.services.invoice_service import InvoiceService
            from app.services.usage_wallet_service import UsageWalletService

            email = UsageWalletService.get_org_billing_email(db, org.id)
            if not email:
                return
            InvoiceService.issue_from_payment(
                db,
                org_id=org.id,
                client_email=email,
                subtotal_pence=amount_minor,
                currency=resolve_org_currency(db, org),
                description="Wallet top-up",
                provider=provider,
                external_invoice_id=reference,
                payment_reference=reference,
                payment_method=provider,
                status="paid",
                line_items=[{"description": "Wallet top-up", "quantity": 1, "unit_pence": amount_minor, "total_pence": amount_minor}],
                kind="topup",
            )
        except Exception:
            logger.exception("stripe_topup_invoice_failed org_id=%s ref=%s", org.id, reference)

    @staticmethod
    def verify_webhook_signature(db: Session, *, payload: bytes, signature_header: str) -> dict[str, Any]:
        cfg = StripePaymentService.get_config(db)
        secret = str(cfg.get("webhook_secret") or "").strip()
        if not secret:
            raise StripeConfigError("Stripe webhook secret is not configured")
        parts = dict(p.split("=", 1) for p in str(signature_header or "").split(",") if "=" in p)
        timestamp = parts.get("t")
        sig = parts.get("v1")
        if not timestamp or not sig:
            raise StripeProviderError("Invalid Stripe signature header")
        if abs(time.time() - int(timestamp)) > 300:
            raise StripeProviderError("Stripe webhook timestamp outside tolerance")
        signed = f"{timestamp}.{payload.decode('utf-8')}"
        expected = hmac.new(secret.encode("utf-8"), signed.encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, sig):
            raise StripeProviderError("Stripe webhook signature mismatch")
        return json.loads(payload)

    @staticmethod
    def handle_webhook_event(db: Session, event: dict[str, Any]) -> dict[str, Any]:
        from app.services.wallet_service import WalletService

        kind = str(event.get("type") or "")
        if kind != "payment_intent.succeeded":
            return {"ok": True, "ignored": True, "type": kind}
        intent = (event.get("data") or {}).get("object") or {}
        pid = str(intent.get("id") or "")
        meta = intent.get("metadata") or {}
        org_id = str(meta.get("voxbulk_org_id") or "")
        if not org_id or str(meta.get("voxbulk_kind") or "") != "wallet_topup":
            return {"ok": True, "ignored": True, "reason": "not_a_wallet_topup"}
        org = db.get(Organisation, org_id)
        if org is None:
            logger.warning("stripe_webhook_unknown_org org_id=%s intent=%s", org_id, pid)
            return {"ok": True, "ignored": True, "reason": "org_not_found"}
        if WalletService.has_transaction_for_reference(db, provider="stripe", provider_reference=pid):
            return {"ok": True, "credited": False, "duplicate": True}
        amount = int(intent.get("amount_received") or intent.get("amount") or 0)
        if amount <= 0:
            return {"ok": True, "ignored": True, "reason": "zero_amount"}
        WalletService.credit(
            db,
            org,
            amount_minor=amount,
            kind="topup",
            provider="stripe",
            provider_reference=pid,
            description="Wallet top-up via Stripe",
        )
        StripePaymentService._issue_topup_invoice(db, org, amount_minor=amount, reference=pid, provider="stripe")
        return {"ok": True, "credited": True, "amount_minor": amount}
