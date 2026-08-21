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
from app.models.subscription import Subscription
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
    def mask_secret_prefix(secret: str) -> str:
        secret = str(secret or "").strip()
        for prefix in ("sk_live_", "sk_test_", "rk_live_", "rk_test_", "pk_live_", "pk_test_"):
            if secret.startswith(prefix):
                return f"{prefix}…{secret[-4:]}" if len(secret) > len(prefix) + 4 else f"{prefix}…"
        return "unknown"

    @staticmethod
    def mode_fields(cfg: dict[str, Any]) -> dict[str, Any]:
        env = ProviderSettingsService.normalize_stripe_environment(cfg.get("environment"))
        return {
            "environment": env,
            "livemode": env == "live",
            "stripe_mode": env,
        }

    @staticmethod
    def get_config(db: Session) -> dict[str, Any]:
        cfg, enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="stripe")
        if not enabled or not cfg:
            raise StripeConfigError("Stripe is not enabled in admin settings")
        cfg = ProviderSettingsService.apply_stripe_active_credentials(cfg)
        env = str(cfg.get("environment") or "").strip()
        if env not in {"sandbox", "live"}:
            raise StripeConfigError(
                "Stripe environment is not set to sandbox or live. "
                "Open Admin → Integrations → Stripe, choose Environment, and Save."
            )
        secret = str(cfg.get("secret_key") or "").strip()
        publishable = str(cfg.get("publishable_key") or "").strip()
        webhook = str(cfg.get("webhook_secret") or "").strip()
        env_label = "Live" if env == "live" else "Sandbox"
        missing: list[str] = []
        if not secret:
            missing.append(f"{env_label} secret key")
        elif not ProviderSettingsService._stripe_secret_matches_env(secret, env):
            raise StripeConfigError(
                f"Active Stripe mode is {env_label} but the {env_label} secret key bucket is wrong or empty. "
                f"Save a matching {'sk_live_' if env == 'live' else 'sk_test_'} key and Save again."
            )
        if not publishable:
            missing.append(f"{env_label} publishable key")
        elif not ProviderSettingsService._stripe_publishable_matches_env(publishable, env):
            raise StripeConfigError(
                f"Active Stripe mode is {env_label} but the {env_label} publishable key bucket is wrong or empty."
            )
        if not webhook:
            missing.append(f"{env_label} webhook signing secret")
        if missing:
            raise StripeConfigError(
                "Stripe active mode is incomplete: "
                + ", ".join(missing)
                + f". Select Environment={env_label}, paste the missing values, and Save. "
                "The other mode's keys are never used as a fallback."
            )
        logger.info(
            "stripe_mode=%s secret_prefix=%s publishable_prefix=%s",
            env,
            StripePaymentService.mask_secret_prefix(secret),
            StripePaymentService.mask_secret_prefix(publishable),
        )
        return cfg

    @staticmethod
    def active_mode_snapshot(db: Session) -> dict[str, Any]:
        """Fresh resolve of active Stripe mode for Admin ground-truth checks."""
        cfg = StripePaymentService.get_config(db)
        env = str(cfg.get("environment") or "")
        return {
            "ok": True,
            "environment": env,
            "livemode": env == "live",
            "stripe_mode": env,
            "secret_key_prefix": StripePaymentService.mask_secret_prefix(str(cfg.get("secret_key") or "")),
            "publishable_key_prefix": StripePaymentService.mask_secret_prefix(str(cfg.get("publishable_key") or "")),
            "webhook_secret_set": bool(str(cfg.get("webhook_secret") or "").strip()),
            "source": "StripePaymentService.get_config",
        }

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
    def _request_with_secret(
        secret: str,
        method: str,
        path: str,
        data: dict[str, Any] | None = None,
        *,
        mode: str | None = None,
    ) -> dict[str, Any]:
        secret = str(secret or "").strip()
        if not secret:
            raise StripeConfigError("Stripe secret key is not configured")
        mode_label = (
            ProviderSettingsService.normalize_stripe_environment(mode)
            if mode
            else ("live" if secret.startswith(("sk_live_", "rk_live_")) else "sandbox")
        )
        logger.info(
            "stripe_mode=%s request=%s %s secret_prefix=%s",
            mode_label,
            method.upper(),
            path,
            StripePaymentService.mask_secret_prefix(secret),
        )
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
    def _request(db: Session, method: str, path: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
        cfg = StripePaymentService.get_config(db)
        return StripePaymentService._request_with_secret(
            str(cfg.get("secret_key") or ""),
            method,
            path,
            data,
            mode=str(cfg.get("environment") or ""),
        )

    @staticmethod
    def test_connection(db: Session, environment: str | None = None) -> dict[str, Any]:
        """Verify sandbox or live keys. Does not change the mode used for customer payments."""
        raw_cfg, _enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="stripe")
        if not raw_cfg:
            raise StripeConfigError("Stripe is not configured")
        active_before = ProviderSettingsService.normalize_stripe_environment(raw_cfg.get("environment"))
        requested = ProviderSettingsService.normalize_stripe_environment(
            environment if environment else raw_cfg.get("environment"),
        )
        creds = ProviderSettingsService.stripe_credentials_for_environment(raw_cfg, requested)
        secret = str(creds.get("secret_key") or "").strip()
        label = "Live" if requested == "live" else "Sandbox (test)"
        if not secret:
            raise StripeConfigError(
                f"{label} secret key is not saved yet. Select {requested}, paste the key, and Save. "
                "Test does not switch the active payment mode."
            )
        balance = StripePaymentService._request_with_secret(secret, "GET", "/balance", mode=requested)
        livemode = bool(balance.get("livemode"))
        actual = "live" if livemode else "sandbox"
        if actual != requested:
            raise StripeProviderError(
                f"You tested {label} but Stripe responded in {'Live' if livemode else 'Sandbox (test)'} mode. "
                f"Paste the matching {'sk_live_' if requested == 'live' else 'sk_test_'} key and Save."
            )
        available = balance.get("available") or []
        raw_after, _ = ProviderSettingsService.get_platform_config_decrypted(db, provider="stripe")
        active_after = ProviderSettingsService.normalize_stripe_environment((raw_after or {}).get("environment"))
        return {
            "ok": True,
            "environment": actual,
            "livemode": livemode,
            "label": "Live" if livemode else "Sandbox (test)",
            "active_environment": active_after,
            "active_environment_unchanged": active_before == active_after,
            "secret_key_prefix": StripePaymentService.mask_secret_prefix(secret),
            "currencies": sorted({str(b.get("currency") or "").upper() for b in available if b.get("currency")}),
            "note": "Test does not change active payment mode. Save Stripe with Environment set to switch.",
        }

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
        seat_quantity: int | None = None,
    ) -> dict[str, Any]:
        from app.services.billing_currency import resolve_org_currency
        from app.services.stripe_billing_service import StripeBillingService

        cfg = StripePaymentService.get_config(db)
        data = StripeBillingService.subscription_checkout_data(
            db,
            org,
            amount_minor=amount_minor,
            plan_id=plan_id,
            billing_interval=billing_interval,
            service_code=service_code,
            customer_email=customer_email,
            seat_quantity=seat_quantity,
        )
        intent = StripePaymentService._request(db, "POST", "/payment_intents", data=data)
        currency = resolve_org_currency(db, org, persist=True)
        return {
            "provider": "stripe",
            "payment_intent_id": str(intent.get("id") or ""),
            "client_secret": str(intent.get("client_secret") or ""),
            "publishable_key": str(cfg.get("publishable_key") or ""),
            "amount_minor": int(intent.get("amount") or amount_minor),
            "currency": currency,
            "status": str(intent.get("status") or ""),
            "customer_id": data.get("customer"),
            **StripePaymentService.mode_fields(cfg),
        }

    @staticmethod
    def create_subscription_setup_intent(
        db: Session,
        org: Organisation,
        *,
        plan_id: str,
        billing_interval: str,
        service_code: str = "voxbulk",
        customer_email: str = "",
        seat_quantity: int | None = None,
        trial_days: int = 0,
        catalog_amount_minor: int = 0,
    ) -> dict[str, Any]:
        """Collect card for a free trial without charging (SetupIntent)."""
        from app.services.billing_currency import resolve_org_currency
        from app.services.stripe_billing_service import StripeBillingService

        cfg = StripePaymentService.get_config(db)
        data = StripeBillingService.subscription_setup_data(
            db,
            org,
            plan_id=plan_id,
            billing_interval=billing_interval,
            service_code=service_code,
            customer_email=customer_email,
            seat_quantity=seat_quantity,
            trial_days=trial_days,
            catalog_amount_minor=catalog_amount_minor,
        )
        intent = StripePaymentService._request(db, "POST", "/setup_intents", data=data)
        currency = resolve_org_currency(db, org, persist=True)
        return {
            "provider": "stripe",
            "setup_intent_id": str(intent.get("id") or ""),
            "payment_intent_id": str(intent.get("id") or ""),
            "client_secret": str(intent.get("client_secret") or ""),
            "publishable_key": str(cfg.get("publishable_key") or ""),
            "amount_minor": 0,
            "currency": currency,
            "status": str(intent.get("status") or ""),
            "customer_id": data.get("customer"),
            "mode": "setup",
            "trial_days": max(0, int(trial_days or 0)),
            **StripePaymentService.mode_fields(cfg),
        }

    @staticmethod
    def retrieve_setup_intent(db: Session, setup_intent_id: str) -> dict[str, Any]:
        return StripePaymentService._request(db, "GET", f"/setup_intents/{setup_intent_id}")

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
        cfg = StripePaymentService.get_config(db)
        currency = resolve_org_currency(db, org, persist=True)
        data: dict[str, Any] = {
            "amount": int(amount_minor),
            "currency": currency.lower(),
            "payment_method_types[0]": "card",
            "payment_method_types[1]": "link",
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
            "publishable_key": str(cfg.get("publishable_key") or ""),
            "amount_minor": int(intent.get("amount") or amount_minor),
            "currency": currency,
            "status": str(intent.get("status") or ""),
            **StripePaymentService.mode_fields(cfg),
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
        if str(meta.get("voxbulk_kind") or "") != "wallet_topup":
            raise StripeProviderError("Payment is not a wallet top-up")
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
        from app.services.promo_discount_service import PromoDiscountService

        PromoDiscountService.apply_and_consume(
            db, org_id=org.id, service_kind="wallet", amount_minor=amount, commit=False
        )
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
        """Verify using the ACTIVE mode webhook secret only.

        Dual-secret acceptance was removed: accepting both sandbox and live secrets on one
        endpoint could verify an inactive-mode event and process it while payments use the
        other mode. Stripe Test and Live dashboards may both POST to /webhooks/stripe; only
        events signed with the active mode secret are accepted, then livemode is checked.
        """
        cfg = StripePaymentService.get_config(db)
        env = str(cfg.get("environment") or "")
        secret = str(cfg.get("webhook_secret") or "").strip()
        if not secret:
            raise StripeConfigError(
                f"Stripe {env} webhook secret is not configured for the active mode"
            )
        pieces = [p.strip() for p in str(signature_header or "").split(",") if "=" in p]
        timestamp = next((p.split("=", 1)[1] for p in pieces if p.startswith("t=")), None)
        v1_sigs = [p.split("=", 1)[1] for p in pieces if p.startswith("v1=")]
        if not timestamp or not v1_sigs:
            raise StripeProviderError("Invalid Stripe signature header")
        if abs(time.time() - int(timestamp)) > 300:
            raise StripeProviderError("Stripe webhook timestamp outside tolerance")
        signed = f"{timestamp}.{payload.decode('utf-8')}"
        expected = hmac.new(secret.encode("utf-8"), signed.encode("utf-8"), hashlib.sha256).hexdigest()
        if not any(hmac.compare_digest(expected, sig) for sig in v1_sigs):
            raise StripeProviderError(
                "Stripe webhook signature mismatch for active mode "
                f"({env}). Use the webhook signing secret from the Stripe Dashboard "
                f"{'Live' if env == 'live' else 'Test'} endpoint."
            )
        event = json.loads(payload)
        event_live = bool(event.get("livemode"))
        expected_live = env == "live"
        if event_live != expected_live:
            raise StripeProviderError(
                f"Stripe webhook livemode={event_live} does not match active mode={env}. "
                "Ignored to prevent cross-mode processing."
            )
        logger.info(
            "stripe_mode=%s request=webhook.verify event_type=%s livemode=%s",
            env,
            str(event.get("type") or ""),
            event_live,
        )
        return event

    @staticmethod
    def handle_webhook_event(db: Session, event: dict[str, Any]) -> dict[str, Any]:
        from app.services.wallet_service import WalletService

        kind = str(event.get("type") or "")
        intent = (event.get("data") or {}).get("object") or {}
        pid = str(intent.get("id") or "")
        meta = intent.get("metadata") or {}
        org_id = str(meta.get("voxbulk_org_id") or "")
        payment_kind = str(meta.get("voxbulk_kind") or "")

        from app.services.card_plan_change_service import PRO_RATA_UPGRADE_KIND
        from app.services.stripe_billing_service import SUBSCRIPTION_RENEWAL_KIND

        if kind == "payment_intent.payment_failed" and payment_kind in {SUBSCRIPTION_RENEWAL_KIND, PRO_RATA_UPGRADE_KIND}:
            org = db.get(Organisation, org_id)
            if org is None:
                return {"ok": True, "ignored": True, "reason": "org_not_found"}
            last_error = intent.get("last_payment_error") or {}
            reason = str(last_error.get("message") or "Card payment declined")
            if payment_kind == PRO_RATA_UPGRADE_KIND:
                from app.services.card_plan_change_service import CardPlanChangeService

                return CardPlanChangeService.handle_pro_rata_webhook_failure(
                    db, org=org, intent=intent, provider="stripe", failure_reason=reason
                )
            from app.services.card_renewal_lifecycle_service import CardRenewalLifecycleService

            return CardRenewalLifecycleService.handle_renewal_webhook_failure(
                db, org=org, intent=intent, provider="stripe", failure_reason=reason
            )

        if kind in {"charge.refunded", "charge.dispute.created", "charge.dispute.closed"}:
            charge = intent if str(intent.get("object") or "") == "charge" else (event.get("data") or {}).get("object") or {}
            pid = str(charge.get("payment_intent") or charge.get("id") or pid)
            charge_meta = charge.get("metadata") or meta
            org_id = str(charge_meta.get("voxbulk_org_id") or org_id)
            payment_kind = str(charge_meta.get("voxbulk_kind") or payment_kind)
            refunds = charge.get("refunds") or {}
            refund_id = ""
            if isinstance(refunds, dict):
                data = refunds.get("data") or []
                if data and isinstance(data[0], dict):
                    refund_id = str(data[0].get("id") or "")
            from app.services.billing_refund_service import BillingRefundService

            return BillingRefundService.handle_provider_refund(
                db,
                provider="stripe",
                org_id=org_id,
                payment_kind=payment_kind,
                payment_intent_id=pid,
                refund_id=refund_id or str(charge.get("id") or pid),
                amount_minor=int(charge.get("amount_refunded") or charge.get("amount") or 0),
                metadata=charge_meta if isinstance(charge_meta, dict) else {},
            )

        if kind == "setup_intent.succeeded":
            from app.services.card_subscription_activation_service import CardSubscriptionActivationService

            setup_kind = str(meta.get("voxbulk_kind") or "")
            if setup_kind != "subscription_checkout":
                return {"ok": True, "ignored": True, "reason": "unsupported_setup_kind"}
            org = db.get(Organisation, org_id)
            if org is None:
                return {"ok": True, "ignored": True, "reason": "org_not_found"}
            result = CardSubscriptionActivationService.activate_from_webhook_intent(
                db, org=org, intent=intent, provider="stripe"
            )
            sub_id = result.get("subscription_id")
            if sub_id:
                from app.services.stripe_billing_service import StripeBillingService

                sub = db.get(Subscription, sub_id)
                if sub is not None:
                    StripeBillingService.sync_credentials_from_setup_intent(db, sub, setup_intent_id=pid)
            return result

        if kind != "payment_intent.succeeded":
            return {"ok": True, "ignored": True, "type": kind}
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

        if payment_kind == "expo_package_checkout":
            from app.services.expo.booth_payment_service import ExpoBoothPaymentService

            return ExpoBoothPaymentService.mark_paid_from_webhook(
                db, org=org, intent=intent, provider="stripe"
            )

        if payment_kind == "subscription_checkout":
            from app.services.card_subscription_activation_service import CardSubscriptionActivationService
            from app.services.stripe_billing_service import StripeBillingService

            result = CardSubscriptionActivationService.activate_from_webhook_intent(
                db, org=org, intent=intent, provider="stripe"
            )
            sub_id = result.get("subscription_id")
            if sub_id:
                sub = db.get(Subscription, sub_id)
                if sub is not None:
                    StripeBillingService.sync_credentials_from_intent(db, sub, payment_intent_id=pid)
            return result

        if payment_kind == "subscription_renewal":
            from app.services.stripe_billing_service import StripeBillingService

            return StripeBillingService.handle_renewal_payment_success(db, org=org, intent=intent)

        if payment_kind == PRO_RATA_UPGRADE_KIND:
            from app.services.card_plan_change_service import CardPlanChangeService

            return CardPlanChangeService.handle_pro_rata_webhook_success(db, org=org, intent=intent, provider="stripe")

        if payment_kind != "wallet_topup":
            return {"ok": True, "ignored": True, "reason": "unsupported_kind"}
        if WalletService.has_transaction_for_reference(db, provider="stripe", provider_reference=pid):
            return {"ok": True, "credited": False, "duplicate": True}
        amount = int(intent.get("amount_received") or intent.get("amount") or 0)
        if amount <= 0:
            return {"ok": True, "ignored": True, "reason": "zero_amount"}
        balance_before = WalletService.balance_minor(org)
        WalletService.credit(
            db,
            org,
            amount_minor=amount,
            kind="topup",
            provider="stripe",
            provider_reference=pid,
            description="Wallet top-up via Stripe",
        )
        db.refresh(org)
        if WalletService.balance_minor(org) == balance_before:
            return {"ok": True, "credited": False, "duplicate": True}
        StripePaymentService._issue_topup_invoice(db, org, amount_minor=amount, reference=pid, provider="stripe")
        return {"ok": True, "credited": True, "amount_minor": amount}
