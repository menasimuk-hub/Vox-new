"""Customer and admin invoice payment orchestration."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.billing_invoice import BillingInvoice
from app.models.organisation import Organisation
from app.services.billing_access_service import BillingAccessService, OUTSTANDING_STATUSES
from app.services.billing_currency import money_display, resolve_org_currency
from app.services.gocardless_service import BillingService, GoCardlessConfigError, GoCardlessProviderError
from app.services.invoice_lifecycle_service import InvoiceLifecycleService
from app.services.invoice_service import InvoiceService
from app.services.org_audit_service import OrgAuditService
from app.services.stripe_payment_service import StripePaymentService
from app.services.wallet_service import InsufficientWalletBalance, WalletService

logger = logging.getLogger(__name__)

PAYABLE_STATUSES = frozenset(
    {"issued", "due", "open", "failed", "past_due", "pending", "draft", "overdue", "unpaid", "sent"}
)
AUTO_COLLECT_STATUSES = frozenset({"collecting"})


class InvoicePaymentError(ValueError):
    pass


class InvoicePaymentService:
    @staticmethod
    def is_outstanding(invoice: BillingInvoice) -> bool:
        return str(invoice.status or "").strip().lower() in OUTSTANDING_STATUSES

    @staticmethod
    def is_payable(invoice: BillingInvoice) -> bool:
        st = str(invoice.status or "").strip().lower()
        if st in {"paid", "refunded", "credited", "void", "cancelled"}:
            return False
        if bool(getattr(invoice, "disputed", False)):
            return False
        if InvoiceLifecycleService.is_dd_collection_active(invoice):
            return False
        return st in PAYABLE_STATUSES or InvoicePaymentService.is_outstanding(invoice)

    @staticmethod
    def amount_due_minor(invoice: BillingInvoice) -> int:
        return int(invoice.amount_gbp_pence if invoice.amount_gbp_pence is not None else invoice.subtotal_pence or 0)

    @staticmethod
    def payment_context(db: Session, org: Organisation, invoice: BillingInvoice) -> dict[str, Any]:
        from app.services.stripe_payment_service import StripePaymentService as StripeSvc

        currency = invoice.currency or resolve_org_currency(db, org)
        amount = InvoicePaymentService.amount_due_minor(invoice)
        wallet = WalletService.balance_minor(org)
        sub = BillingAccessService.get_subscription(db, org.id)
        mandate_active = sub is not None and str(sub.mandate_status or "").strip().lower() == "active"
        from app.services.airwallex_payment_service import AirwallexPaymentService

        stripe_available = StripeSvc.is_available(db)
        airwallex_available = AirwallexPaymentService.is_available(db)
        card_available = stripe_available or airwallex_available
        payable = InvoicePaymentService.is_payable(invoice)
        st = str(invoice.status or "").strip().lower()
        lifecycle = InvoiceLifecycleService.policy(invoice)
        shortfall = max(0, amount - wallet)

        methods: list[dict[str, Any]] = []
        next_steps: list[str] = []

        if not payable:
            if InvoiceLifecycleService.is_dd_collection_active(invoice):
                next_steps.append("Direct Debit collection is in progress — payment completes in 3–5 working days.")
            elif st == "paid":
                next_steps.append("This invoice is already paid.")
            elif st in {"void", "cancelled"}:
                next_steps.append("This invoice was voided. Contact support if you still owe this amount.")
            else:
                next_steps.append("This invoice is not payable online.")
        else:
            if amount <= 0:
                next_steps.append("Nothing is due on this invoice.")
            else:
                if wallet >= amount:
                    methods.append(
                        {
                            "method": "wallet",
                            "label": "Pay from wallet",
                            "available": True,
                            "amount_minor": amount,
                            "amount_display": money_display(amount, currency),
                            "wallet_balance_minor": wallet,
                            "wallet_balance_display": money_display(wallet, currency),
                            "outcome": "instant",
                            "outcome_label": "Paid instantly from your wallet balance.",
                        }
                    )
                elif wallet > 0:
                    methods.append(
                        {
                            "method": "wallet",
                            "label": "Pay from wallet",
                            "available": False,
                            "amount_minor": amount,
                            "amount_display": money_display(amount, currency),
                            "wallet_balance_minor": wallet,
                            "wallet_balance_display": money_display(wallet, currency),
                            "shortfall_minor": shortfall,
                            "shortfall_display": money_display(shortfall, currency),
                            "outcome": "unavailable",
                            "outcome_label": "Wallet cannot partially pay invoices — use card or Direct Debit for the full amount.",
                        }
                    )

                if stripe_available:
                    methods.append(
                        {
                            "method": "card",
                            "label": "Pay by card (Stripe)",
                            "available": True,
                            "provider": "stripe",
                            "amount_minor": amount,
                            "amount_display": money_display(amount, currency),
                            "outcome": "instant",
                            "outcome_label": "Card payment settles this invoice immediately after confirmation.",
                        }
                    )
                if airwallex_available:
                    methods.append(
                        {
                            "method": "card",
                            "label": "Pay by card (Airwallex)",
                            "available": True,
                            "provider": "airwallex",
                            "amount_minor": amount,
                            "amount_display": money_display(amount, currency),
                            "outcome": "instant",
                            "outcome_label": "Card payment settles this invoice immediately after confirmation.",
                        }
                    )

                if mandate_active:
                    methods.append(
                        {
                            "method": "direct_debit",
                            "label": "Pay by Direct Debit",
                            "available": True,
                            "amount_minor": amount,
                            "amount_display": money_display(amount, currency),
                            "outcome": "collecting",
                            "outcome_label": "Direct Debit collection starts now and completes in 3–5 working days.",
                        }
                    )

                if not any(m.get("available") for m in methods):
                    next_steps.append(
                        "No online payment method is available. Top up your wallet, set up Direct Debit, or pay by bank transfer and contact support."
                    )

        return {
            "payable": payable,
            "partial_wallet_supported": False,
            "amount_due_minor": amount,
            "amount_due_display": money_display(amount, currency),
            "payment_status": st,
            "payment_method": invoice.payment_method,
            "dd_status": getattr(invoice, "dd_status", None),
            "kind": getattr(invoice, "kind", None),
            "order_id": getattr(invoice, "order_id", None),
            "methods": [m for m in methods if m.get("available") is not False or m.get("method") == "wallet"],
            "available_methods": [m for m in methods if m.get("available")],
            "wallet_balance_minor": wallet,
            "wallet_balance_display": money_display(wallet, currency),
            "wallet_shortfall_minor": shortfall if wallet < amount else 0,
            "wallet_shortfall_display": money_display(shortfall, currency) if wallet < amount else None,
            "card_available": card_available,
            "stripe_available": stripe_available,
            "airwallex_available": airwallex_available,
            "mandate_active": mandate_active,
            "next_steps": next_steps,
            "lifecycle": lifecycle,
        }

    @staticmethod
    def enrich_invoice_dict(db: Session, org: Organisation, invoice: BillingInvoice, base: dict[str, Any]) -> dict[str, Any]:
        ctx = InvoicePaymentService.payment_context(db, org, invoice)
        enriched = InvoiceLifecycleService.enrich_invoice_dict(base, invoice)
        return {**enriched, "payment_context": ctx, "payable": ctx["payable"]}

    @staticmethod
    def mark_paid_from_card(
        db: Session,
        org: Organisation,
        invoice: BillingInvoice,
        *,
        provider: str,
        provider_reference: str,
        amount_minor: int,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        invoice.status = "paid"
        invoice.payment_method = provider
        invoice.payment_reference = provider_reference
        db.add(invoice)
        InvoicePaymentService._sync_linked_order_after_payment(db, invoice)
        OrgAuditService.record(
            db,
            org_id=org.id,
            event_type="invoice.paid",
            action=f"Invoice paid by card — {invoice.invoice_number or invoice.id[:8]}",
            entity_type="invoice",
            entity_id=invoice.id,
            metadata={"provider": provider, "provider_reference": provider_reference, "amount_minor": amount_minor},
            actor_user_id=user_id,
            commit=False,
        )
        db.commit()
        db.refresh(invoice)
        logger.info("invoice_paid_card invoice_id=%s org_id=%s ref=%s", invoice.id, org.id, provider_reference)
        return {
            "ok": True,
            "paid": True,
            "method": "card",
            "provider": provider,
            "invoice": InvoiceService.invoice_to_dict(db, invoice),
            "wallet": WalletService.wallet_dict(db, org),
        }

    @staticmethod
    def pay_with_wallet(
        db: Session,
        org: Organisation,
        invoice: BillingInvoice,
        *,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        if not InvoicePaymentService.is_payable(invoice):
            raise InvoicePaymentError("This invoice is not payable from your wallet.")
        amount = InvoicePaymentService.amount_due_minor(invoice)
        if amount <= 0:
            raise InvoicePaymentError("Nothing due on this invoice.")

        try:
            tx = WalletService.debit(
                db,
                org,
                amount_minor=amount,
                kind="invoice_payment",
                description=f"Invoice payment — {invoice.invoice_number or invoice.id[:8]}",
                invoice_id=invoice.id,
                order_id=getattr(invoice, "order_id", None),
                created_by_user_id=user_id,
                commit=False,
            )
        except InsufficientWalletBalance as exc:
            raise InvoicePaymentError(
                "Wallet balance is insufficient for the full invoice amount. "
                "Partial wallet payment is not supported — pay by card or Direct Debit instead."
            ) from exc
        invoice.status = "paid"
        invoice.payment_method = "wallet"
        invoice.payment_reference = tx.id
        db.add(invoice)
        InvoicePaymentService._sync_linked_order_after_payment(db, invoice)
        OrgAuditService.record(
            db,
            org_id=org.id,
            event_type="invoice.paid",
            action=f"Invoice paid from wallet — {invoice.invoice_number or invoice.id[:8]}",
            entity_type="invoice",
            entity_id=invoice.id,
            metadata={"wallet_transaction_id": tx.id, "amount_minor": amount},
            actor_user_id=user_id,
            commit=False,
        )
        db.commit()
        db.refresh(invoice)
        db.refresh(tx)
        logger.info("invoice_paid_wallet invoice_id=%s org_id=%s amount=%s", invoice.id, org.id, amount)
        return {
            "ok": True,
            "method": "wallet",
            "invoice": InvoiceService.invoice_to_dict(db, invoice),
            "wallet_transaction": WalletService.transaction_to_dict(tx),
            "wallet": WalletService.wallet_dict(db, org),
        }

    @staticmethod
    def start_direct_debit(
        db: Session,
        org: Organisation,
        invoice: BillingInvoice,
        *,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        if not InvoicePaymentService.is_payable(invoice):
            raise InvoicePaymentError("This invoice cannot be collected by Direct Debit.")
        sub = BillingAccessService.get_subscription(db, org.id)
        mandate_active = sub is not None and str(sub.mandate_status or "").strip().lower() == "active"
        if not mandate_active:
            raise InvoicePaymentError("No active Direct Debit mandate on this account.")

        amount = InvoicePaymentService.amount_due_minor(invoice)
        currency = invoice.currency or resolve_org_currency(db, org)
        desc = (invoice.description or f"Invoice {invoice.invoice_number or invoice.id}")[:255]

        try:
            payment = BillingService.collect_mandate_payment(
                db,
                org_id=org.id,
                amount_pence=amount,
                description=desc,
                currency=currency,
                metadata={"invoice_id": invoice.id},
            )
        except GoCardlessConfigError as exc:
            raise InvoicePaymentError("Direct Debit is not configured for your account.") from exc
        except GoCardlessProviderError as exc:
            raise InvoicePaymentError(str(exc) or "Direct Debit collection failed.") from exc

        invoice.dd_payment_id = str(payment.get("payment_id") or "")
        invoice.dd_status = str(payment.get("status") or "pending_submission")
        invoice.payment_reference = invoice.dd_payment_id
        invoice.status = "collecting"
        invoice.payment_method = "gocardless"
        db.add(invoice)
        OrgAuditService.record(
            db,
            org_id=org.id,
            event_type="invoice.dd_started",
            action=f"Direct Debit collection started — {invoice.invoice_number or invoice.id[:8]}",
            entity_type="invoice",
            entity_id=invoice.id,
            metadata={"dd_payment_id": invoice.dd_payment_id, "amount_minor": amount},
            actor_user_id=user_id,
        )
        db.commit()
        db.refresh(invoice)
        return {
            "ok": True,
            "method": "direct_debit",
            "status": "collecting",
            "invoice": InvoiceService.invoice_to_dict(db, invoice),
            "dd_payment_id": invoice.dd_payment_id,
            "outcome_label": "Direct Debit collection is in progress.",
        }

    @staticmethod
    def pay_invoice(
        db: Session,
        org: Organisation,
        invoice: BillingInvoice,
        *,
        method: str,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        m = str(method or "wallet").strip().lower()
        if m == "wallet":
            return InvoicePaymentService.pay_with_wallet(db, org, invoice, user_id=user_id)
        if m in {"direct_debit", "direct_debit_retry", "dd"}:
            return InvoicePaymentService.start_direct_debit(db, org, invoice, user_id=user_id)
        if m == "card":
            raise InvoicePaymentError("Use the card payment intent flow for card settlement.")
        raise InvoicePaymentError(f"Unsupported payment method: {method}")

    @staticmethod
    def create_card_payment_intent(
        db: Session,
        org: Organisation,
        invoice: BillingInvoice,
        *,
        provider: str = "stripe",
    ) -> dict[str, Any]:
        from app.services.airwallex_payment_service import AirwallexPaymentService

        if not InvoicePaymentService.is_payable(invoice):
            raise InvoicePaymentError("This invoice is not payable by card.")
        amount = InvoicePaymentService.amount_due_minor(invoice)
        if amount <= 0:
            raise InvoicePaymentError("Nothing due on this invoice.")
        prov = str(provider or "stripe").strip().lower()
        if prov == "stripe":
            if not StripePaymentService.is_available(db):
                raise InvoicePaymentError("Stripe card payments are not configured.")
            payload = StripePaymentService.create_invoice_payment_intent(
                db,
                org,
                invoice_id=invoice.id,
                amount_minor=amount,
                invoice_number=invoice.invoice_number,
            )
        elif prov == "airwallex":
            if not AirwallexPaymentService.is_available(db):
                raise InvoicePaymentError("Airwallex card payments are not configured.")
            payload = AirwallexPaymentService.create_invoice_payment_intent(
                db,
                org,
                invoice_id=invoice.id,
                amount_minor=amount,
                invoice_number=invoice.invoice_number,
            )
        else:
            raise InvoicePaymentError("provider must be stripe or airwallex")
        return {"ok": True, **payload}

    @staticmethod
    def confirm_card_payment(
        db: Session,
        org: Organisation,
        invoice: BillingInvoice,
        *,
        payment_intent_id: str,
        provider: str = "stripe",
        user_id: str | None = None,
    ) -> dict[str, Any]:
        from app.services.airwallex_payment_service import AirwallexPaymentService, AirwallexProviderError
        from app.services.stripe_payment_service import StripeProviderError

        prov = str(provider or "stripe").strip().lower()
        try:
            if prov == "stripe":
                return StripePaymentService.confirm_invoice_payment(
                    db,
                    org,
                    invoice_id=invoice.id,
                    payment_intent_id=payment_intent_id,
                    user_id=user_id,
                )
            if prov == "airwallex":
                return AirwallexPaymentService.confirm_invoice_payment(
                    db,
                    org,
                    invoice_id=invoice.id,
                    payment_intent_id=payment_intent_id,
                    user_id=user_id,
                )
            raise InvoicePaymentError("provider must be stripe or airwallex")
        except (StripeProviderError, AirwallexProviderError) as exc:
            raise InvoicePaymentError(str(exc)) from exc

    @staticmethod
    def _sync_linked_order_after_payment(db: Session, invoice: BillingInvoice) -> None:
        order_id = getattr(invoice, "order_id", None)
        if not order_id:
            return
        from app.models.service_order import ServiceOrder

        order = db.get(ServiceOrder, order_id)
        if order is None:
            return
        if str(order.payment_status or "").lower() not in {"unpaid", "pending_approval", "rejected"}:
            return
        order.payment_status = "approved"
        if not order.payment_method:
            order.payment_method = str(invoice.payment_method or "wallet")
        order.updated_at = datetime.utcnow()
        db.add(order)
