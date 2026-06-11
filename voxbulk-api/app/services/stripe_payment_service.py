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
        return StripePaymentService._create_payment_intent(
            db,
            org,
            amount_minor=amount_minor,
            kind="wallet_topup",
            description=f"VoxBulk wallet top-up — {org.name}",
            metadata_extra=None,
        )

    @staticmethod
    def create_invoice_payment_intent(
        db: Session,
        org: Organisation,
        *,
        invoice_id: str,
        amount_minor: int,
        invoice_number: str | None = None,
    ) -> dict[str, Any]:
        label = invoice_number or invoice_id[:8]
        return StripePaymentService._create_payment_intent(
            db,
            org,
            amount_minor=amount_minor,
            kind="invoice_payment",
            description=f"Invoice payment — {label}",
            metadata_extra={"voxbulk_invoice_id": invoice_id},
        )

    @staticmethod
    def _create_payment_intent(
        db: Session,
        org: Organisation,
        *,
        amount_minor: int,
        kind: str,
        description: str,
        metadata_extra: dict[str, str] | None,
    ) -> dict[str, Any]:
        currency = resolve_org_currency(db, org, persist=True)
        data: dict[str, Any] = {
            "amount": int(amount_minor),
            "currency": currency.lower(),
            "automatic_payment_methods[enabled]": "true",
            "metadata[voxbulk_org_id]": org.id,
            "metadata[voxbulk_kind]": kind,
            "description": description[:255],
        }
        if metadata_extra:
            for key, value in metadata_extra.items():
                data[f"metadata[{key}]"] = value
        intent = StripePaymentService._request(db, "POST", "/payment_intents", data=data)
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
    def confirm_invoice_payment(
        db: Session,
        org: Organisation,
        *,
        invoice_id: str,
        payment_intent_id: str,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        """Verify Stripe PaymentIntent for invoice settlement and mark invoice paid once."""
        from app.models.billing_invoice import BillingInvoice
        from app.services.invoice_payment_service import InvoicePaymentError, InvoicePaymentService

        pid = str(payment_intent_id or "").strip()
        if not pid:
            raise StripeProviderError("payment_intent_id required")
        intent = StripePaymentService.retrieve_intent(db, pid)
        meta = intent.get("metadata") or {}
        if str(meta.get("voxbulk_org_id") or "") != org.id:
            raise StripeProviderError("Payment does not belong to this organisation")
        if str(meta.get("voxbulk_kind") or "") != "invoice_payment":
            raise StripeProviderError("Payment is not for invoice settlement")
        if str(meta.get("voxbulk_invoice_id") or "") != str(invoice_id):
            raise StripeProviderError("Payment does not match this invoice")

        invoice = db.get(BillingInvoice, invoice_id)
        if invoice is None or invoice.org_id != org.id:
            raise StripeProviderError("Invoice not found")
        if not InvoicePaymentService.is_payable(invoice):
            raise StripeProviderError("This invoice is no longer payable")

        status = str(intent.get("status") or "")
        if status != "succeeded":
            return {"ok": False, "status": status, "paid": False}

        amount = int(intent.get("amount_received") or intent.get("amount") or 0)
        due = InvoicePaymentService.amount_due_minor(invoice)
        if amount < due:
            raise StripeProviderError("Card payment amount is less than invoice due")

        if str(invoice.payment_reference or "") == pid and str(invoice.status or "").lower() == "paid":
            return {"ok": True, "status": status, "paid": True, "duplicate": True, "invoice_id": invoice.id}

        return InvoicePaymentService.mark_paid_from_card(
            db,
            org,
            invoice,
            provider="stripe",
            provider_reference=pid,
            amount_minor=amount,
            user_id=user_id,
        )

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
    def issue_refund(
        db: Session,
        *,
        payment_intent_id: str,
        amount_minor: int | None = None,
        reason: str = "requested_by_customer",
    ) -> dict[str, Any]:
        """Create a Stripe refund against a captured PaymentIntent."""
        pid = str(payment_intent_id or "").strip()
        if not pid:
            raise StripeProviderError("payment_intent_id required")
        data: dict[str, Any] = {
            "payment_intent": pid,
            "reason": reason,
        }
        if amount_minor is not None and int(amount_minor) > 0:
            data["amount"] = int(amount_minor)
        refund = StripePaymentService._request(db, "POST", "/refunds", data=data)
        return {
            "refund_id": str(refund.get("id") or ""),
            "amount_minor": int(refund.get("amount") or amount_minor or 0),
            "status": str(refund.get("status") or ""),
            "payment_intent_id": pid,
        }

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
        payment_kind = str(meta.get("voxbulk_kind") or "")
        org = db.get(Organisation, org_id)
        if org is None:
            logger.warning("stripe_webhook_unknown_org org_id=%s intent=%s", org_id, pid)
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
            amount = int(intent.get("amount_received") or intent.get("amount") or 0)
            InvoicePaymentService.mark_paid_from_card(
                db,
                org,
                invoice,
                provider="stripe",
                provider_reference=pid,
                amount_minor=amount,
                user_id=None,
            )
            return {"ok": True, "paid": True, "invoice_id": invoice_id}

        if payment_kind != "wallet_topup":
            return {"ok": True, "ignored": True, "reason": "unsupported_kind"}
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
