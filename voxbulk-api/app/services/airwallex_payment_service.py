"""Airwallex card payments for wallet top-ups and invoice settlement (PaymentIntents via REST)."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
import uuid
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.models.organisation import Organisation
from app.models.subscription import Subscription
from app.services.billing_currency import resolve_org_currency
from app.services.provider_settings import ProviderSettingsService

logger = logging.getLogger(__name__)

AIRWALLEX_BASES = {
    "demo": "https://api-demo.airwallex.com",
    "prod": "https://api.airwallex.com",
}

# Short-lived bearer token cache: {cache_key: (expiry_epoch, token)}
_TOKEN_CACHE: dict[str, tuple[float, str]] = {}


class AirwallexConfigError(ValueError):
    pass


class AirwallexProviderError(RuntimeError):
    pass


class AirwallexPaymentService:
    @staticmethod
    def get_config(db: Session) -> dict[str, Any]:
        cfg, enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="airwallex")
        if not enabled or not cfg:
            raise AirwallexConfigError("Airwallex is not enabled in admin settings")
        if not str(cfg.get("client_id") or "").strip() or not str(cfg.get("api_key") or "").strip():
            raise AirwallexConfigError("Airwallex client ID / API key are not configured")
        return cfg

    @staticmethod
    def is_available(db: Session) -> bool:
        try:
            AirwallexPaymentService.get_config(db)
            return True
        except AirwallexConfigError:
            return False

    @staticmethod
    def _base_url(cfg: dict[str, Any]) -> str:
        env = str(cfg.get("environment") or "demo").strip().lower()
        return AIRWALLEX_BASES.get(env, AIRWALLEX_BASES["demo"])

    @staticmethod
    def _bearer_token(db: Session) -> tuple[str, str]:
        cfg = AirwallexPaymentService.get_config(db)
        base = AirwallexPaymentService._base_url(cfg)
        client_id = str(cfg.get("client_id") or "").strip()
        cache_key = f"{base}:{client_id}"
        cached = _TOKEN_CACHE.get(cache_key)
        now = time.time()
        if cached and cached[0] > now + 60:
            return cached[1], base
        try:
            resp = httpx.post(
                f"{base}/api/v1/authentication/login",
                headers={"x-client-id": client_id, "x-api-key": str(cfg.get("api_key") or "").strip()},
                timeout=30.0,
            )
        except httpx.HTTPError as exc:
            raise AirwallexProviderError(f"Airwallex auth failed: {exc}") from exc
        if resp.status_code >= 400:
            raise AirwallexProviderError(f"Airwallex auth error: {resp.text[:300]}")
        token = str(resp.json().get("token") or "")
        if not token:
            raise AirwallexProviderError("Airwallex auth returned no token")
        _TOKEN_CACHE[cache_key] = (now + 25 * 60, token)
        return token, base

    @staticmethod
    def _request(db: Session, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        token, base = AirwallexPaymentService._bearer_token(db)
        try:
            resp = httpx.request(
                method,
                f"{base}{path}",
                json=payload,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                timeout=30.0,
            )
        except httpx.HTTPError as exc:
            raise AirwallexProviderError(f"Airwallex request failed: {exc}") from exc
        if resp.status_code >= 400:
            logger.warning("airwallex_api_error status=%s path=%s body=%s", resp.status_code, path, resp.text[:300])
            try:
                message = resp.json().get("message") or resp.text[:300]
            except Exception:
                message = resp.text[:300]
            raise AirwallexProviderError(f"Airwallex error: {message}")
        return resp.json()

    @staticmethod
    def test_connection(db: Session) -> dict[str, Any]:
        """Verify the client ID / API key by authenticating against Airwallex."""
        cfg = AirwallexPaymentService.get_config(db)
        token, base = AirwallexPaymentService._bearer_token(db)
        return {
            "ok": bool(token),
            "environment": str(cfg.get("environment") or "demo"),
            "api_base": base,
        }

    @staticmethod
    def create_invoice_payment_intent(
        db: Session,
        org: Organisation,
        *,
        invoice_id: str,
        amount_minor: int,
        invoice_number: str | None = None,
    ) -> dict[str, Any]:
        currency = resolve_org_currency(db, org, persist=True)
        label = invoice_number or invoice_id[:8]
        request_id = str(uuid.uuid4())
        intent = AirwallexPaymentService._request(
            db,
            "POST",
            "/api/v1/pa/payment_intents/create",
            payload={
                "request_id": request_id,
                "amount": round(int(amount_minor) / 100.0, 2),
                "currency": currency,
                "merchant_order_id": f"voxbulk-invoice-{invoice_id[:8]}-{int(time.time())}",
                "metadata": {
                    "voxbulk_org_id": org.id,
                    "voxbulk_kind": "invoice_payment",
                    "voxbulk_invoice_id": invoice_id,
                },
                "descriptor": f"Invoice {label}"[:22],
            },
        )
        return {
            "provider": "airwallex",
            "payment_intent_id": str(intent.get("id") or ""),
            "client_secret": str(intent.get("client_secret") or ""),
            "amount_minor": int(amount_minor),
            "currency": currency,
            "status": str(intent.get("status") or ""),
            "environment": str(AirwallexPaymentService.get_config(db).get("environment") or "demo"),
        }

    @staticmethod
    def confirm_invoice_payment(
        db: Session,
        org: Organisation,
        *,
        invoice_id: str,
        payment_intent_id: str,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        from app.models.billing_invoice import BillingInvoice
        from app.services.invoice_payment_service import InvoicePaymentService

        pid = str(payment_intent_id or "").strip()
        if not pid:
            raise AirwallexProviderError("payment_intent_id required")
        intent = AirwallexPaymentService.retrieve_intent(db, pid)
        meta = intent.get("metadata") or {}
        if str(meta.get("voxbulk_org_id") or "") != org.id:
            raise AirwallexProviderError("Payment does not belong to this organisation")
        if str(meta.get("voxbulk_kind") or "") != "invoice_payment":
            raise AirwallexProviderError("Payment is not for invoice settlement")
        if str(meta.get("voxbulk_invoice_id") or "") != str(invoice_id):
            raise AirwallexProviderError("Payment does not match this invoice")
        status = str(intent.get("status") or "").upper()
        if status != "SUCCEEDED":
            return {"ok": False, "status": status, "paid": False}
        invoice = db.get(BillingInvoice, invoice_id)
        if invoice is None or invoice.org_id != org.id:
            raise AirwallexProviderError("Invoice not found")
        if not InvoicePaymentService.is_payable(invoice):
            raise AirwallexProviderError("This invoice is no longer payable")
        amount = int(round(float(intent.get("captured_amount") or intent.get("amount") or 0) * 100))
        due = InvoicePaymentService.amount_due_minor(invoice)
        if amount < due:
            raise AirwallexProviderError("Card payment amount is less than invoice due")
        if str(invoice.payment_reference or "") == pid and str(invoice.status or "").lower() == "paid":
            return {"ok": True, "status": status, "paid": True, "duplicate": True, "invoice_id": invoice.id}
        return InvoicePaymentService.mark_paid_from_card(
            db,
            org,
            invoice,
            provider="airwallex",
            provider_reference=pid,
            amount_minor=amount,
            user_id=user_id,
        )

    @staticmethod
    def create_subscription_checkout_intent(
        db: Session,
        org: Organisation,
        *,
        amount_minor: int,
        plan_id: str,
        billing_interval: str,
        service_code: str = "voxbulk",
        customer_email: str = "",
    ) -> dict[str, Any]:
        from app.services.airwallex_billing_service import AirwallexBillingService

        payload = AirwallexBillingService.subscription_checkout_payload(
            db,
            org,
            amount_minor=amount_minor,
            plan_id=plan_id,
            billing_interval=billing_interval,
            service_code=service_code,
            customer_email=customer_email,
        )
        intent = AirwallexPaymentService._request(
            db,
            "POST",
            "/api/v1/pa/payment_intents/create",
            payload=payload,
        )
        currency = str(payload.get("currency") or "GBP")
        return {
            "provider": "airwallex",
            "payment_intent_id": str(intent.get("id") or ""),
            "client_secret": str(intent.get("client_secret") or ""),
            "amount_minor": int(amount_minor),
            "currency": currency,
            "status": str(intent.get("status") or ""),
            "environment": str(AirwallexPaymentService.get_config(db).get("environment") or "demo"),
            "customer_id": payload.get("customer_id"),
        }

    @staticmethod
    def create_topup_intent(db: Session, org: Organisation, *, amount_minor: int) -> dict[str, Any]:
        currency = resolve_org_currency(db, org, persist=True)
        request_id = str(uuid.uuid4())
        intent = AirwallexPaymentService._request(
            db,
            "POST",
            "/api/v1/pa/payment_intents/create",
            payload={
                "request_id": request_id,
                "amount": round(int(amount_minor) / 100.0, 2),
                "currency": currency,
                "merchant_order_id": f"voxbulk-topup-{org.id[:8]}-{int(time.time())}",
                "metadata": {"voxbulk_org_id": org.id, "voxbulk_kind": "wallet_topup"},
                "descriptor": "VoxBulk wallet top-up",
            },
        )
        return {
            "provider": "airwallex",
            "payment_intent_id": str(intent.get("id") or ""),
            "client_secret": str(intent.get("client_secret") or ""),
            "amount_minor": int(amount_minor),
            "currency": currency,
            "status": str(intent.get("status") or ""),
            "environment": str(AirwallexPaymentService.get_config(db).get("environment") or "demo"),
        }

    @staticmethod
    def retrieve_intent(db: Session, payment_intent_id: str) -> dict[str, Any]:
        return AirwallexPaymentService._request(db, "GET", f"/api/v1/pa/payment_intents/{payment_intent_id}")

    @staticmethod
    def confirm_topup(db: Session, org: Organisation, *, payment_intent_id: str) -> dict[str, Any]:
        from app.services.wallet_service import WalletService

        pid = str(payment_intent_id or "").strip()
        if not pid:
            raise AirwallexProviderError("payment_intent_id required")
        intent = AirwallexPaymentService.retrieve_intent(db, pid)
        meta = intent.get("metadata") or {}
        if str(meta.get("voxbulk_org_id") or "") != org.id:
            raise AirwallexProviderError("Payment does not belong to this organisation")
        status = str(intent.get("status") or "").upper()
        if status != "SUCCEEDED":
            return {"ok": False, "status": status, "credited": False}
        if WalletService.has_transaction_for_reference(db, provider="airwallex", provider_reference=pid):
            return {"ok": True, "status": status, "credited": False, "duplicate": True}
        amount = int(round(float(intent.get("captured_amount") or intent.get("amount") or 0) * 100))
        if amount <= 0:
            raise AirwallexProviderError("Airwallex payment has no captured amount")
        WalletService.credit(
            db,
            org,
            amount_minor=amount,
            kind="topup",
            provider="airwallex",
            provider_reference=pid,
            description="Wallet top-up via Airwallex",
        )
        AirwallexPaymentService._issue_topup_invoice(db, org, amount_minor=amount, reference=pid)
        return {"ok": True, "status": status, "credited": True, "amount_minor": amount}

    @staticmethod
    def _issue_topup_invoice(db: Session, org: Organisation, *, amount_minor: int, reference: str) -> None:
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
                provider="airwallex",
                external_invoice_id=reference,
                payment_reference=reference,
                payment_method="airwallex",
                status="paid",
                line_items=[{"description": "Wallet top-up", "quantity": 1, "unit_pence": amount_minor, "total_pence": amount_minor}],
                kind="topup",
            )
        except Exception:
            logger.exception("airwallex_topup_invoice_failed org_id=%s ref=%s", org.id, reference)

    @staticmethod
    def verify_webhook_signature(db: Session, *, payload: bytes, timestamp: str, signature: str) -> dict[str, Any]:
        cfg = AirwallexPaymentService.get_config(db)
        secret = str(cfg.get("webhook_secret") or "").strip()
        if not secret:
            raise AirwallexConfigError("Airwallex webhook secret is not configured")
        signed = f"{timestamp}{payload.decode('utf-8')}"
        expected = hmac.new(secret.encode("utf-8"), signed.encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, str(signature or "")):
            raise AirwallexProviderError("Airwallex webhook signature mismatch")
        return json.loads(payload)

    @staticmethod
    def handle_webhook_event(db: Session, event: dict[str, Any]) -> dict[str, Any]:
        from app.services.wallet_service import WalletService

        name = str(event.get("name") or "")
        intent = (event.get("data") or {}).get("object") or {}
        pid = str(intent.get("id") or "")
        meta = intent.get("metadata") or {}
        org_id = str(meta.get("voxbulk_org_id") or "")
        payment_kind = str(meta.get("voxbulk_kind") or "")

        from app.services.airwallex_billing_service import SUBSCRIPTION_RENEWAL_KIND
        from app.services.card_plan_change_service import PRO_RATA_UPGRADE_KIND

        if name in {"payment_intent.failed", "payment_intent.cancelled"} and payment_kind in {
            SUBSCRIPTION_RENEWAL_KIND,
            PRO_RATA_UPGRADE_KIND,
        }:
            if not org_id:
                return {"ok": True, "ignored": True, "reason": "missing_org"}
            org = db.get(Organisation, org_id)
            if org is None:
                return {"ok": True, "ignored": True, "reason": "org_not_found"}
            reason = str(intent.get("failure_reason") or intent.get("cancellation_reason") or "Card payment declined")
            if payment_kind == PRO_RATA_UPGRADE_KIND:
                from app.services.card_plan_change_service import CardPlanChangeService

                return CardPlanChangeService.handle_pro_rata_webhook_failure(
                    db, org=org, intent=intent, provider="airwallex", failure_reason=reason
                )
            from app.services.card_renewal_lifecycle_service import CardRenewalLifecycleService

            return CardRenewalLifecycleService.handle_renewal_webhook_failure(
                db, org=org, intent=intent, provider="airwallex", failure_reason=reason
            )

        if name != "payment_intent.succeeded":
            return {"ok": True, "ignored": True, "name": name}
        if not org_id:
            return {"ok": True, "ignored": True, "reason": "missing_org"}
        org = db.get(Organisation, org_id)
        if org is None:
            return {"ok": True, "ignored": True, "reason": "org_not_found"}

        if payment_kind == "invoice_payment":
            from app.models.billing_invoice import BillingInvoice
            from app.services.invoice_payment_service import InvoicePaymentService

            invoice_id = str(meta.get("voxbulk_invoice_id") or "")
            invoice = db.get(BillingInvoice, invoice_id)
            if invoice is None or invoice.org_id != org.id:
                return {"ok": True, "ignored": True, "reason": "invoice_not_found"}
            if str(invoice.status or "").lower() == "paid":
                return {"ok": True, "paid": True, "duplicate": True}
            amount = int(round(float(intent.get("captured_amount") or intent.get("amount") or 0) * 100))
            InvoicePaymentService.mark_paid_from_card(
                db,
                org,
                invoice,
                provider="airwallex",
                provider_reference=pid,
                amount_minor=amount,
                user_id=None,
            )
            return {"ok": True, "paid": True, "invoice_id": invoice_id}

        if payment_kind == "subscription_checkout":
            from app.services.card_subscription_activation_service import CardSubscriptionActivationService
            from app.services.airwallex_billing_service import AirwallexBillingService

            result = CardSubscriptionActivationService.activate_from_webhook_intent(
                db, org=org, intent=intent, provider="airwallex"
            )
            sub_id = result.get("subscription_id")
            if sub_id:
                sub = db.get(Subscription, sub_id)
                if sub is not None:
                    AirwallexBillingService.sync_credentials_from_intent(db, sub, payment_intent_id=pid)
            return result

        if payment_kind == "subscription_renewal":
            from app.services.airwallex_billing_service import AirwallexBillingService

            return AirwallexBillingService.handle_renewal_payment_success(db, org=org, intent=intent)

        if payment_kind == PRO_RATA_UPGRADE_KIND:
            from app.services.card_plan_change_service import CardPlanChangeService

            return CardPlanChangeService.handle_pro_rata_webhook_success(
                db, org=org, intent=intent, provider="airwallex"
            )

        if payment_kind != "wallet_topup":
            return {"ok": True, "ignored": True, "reason": "not_a_wallet_topup"}
        if WalletService.has_transaction_for_reference(db, provider="airwallex", provider_reference=pid):
            return {"ok": True, "credited": False, "duplicate": True}
        amount = int(round(float(intent.get("captured_amount") or intent.get("amount") or 0) * 100))
        if amount <= 0:
            return {"ok": True, "ignored": True, "reason": "zero_amount"}
        WalletService.credit(
            db,
            org,
            amount_minor=amount,
            kind="topup",
            provider="airwallex",
            provider_reference=pid,
            description="Wallet top-up via Airwallex",
        )
        AirwallexPaymentService._issue_topup_invoice(db, org, amount_minor=amount, reference=pid)
        return {"ok": True, "credited": True, "amount_minor": amount}
