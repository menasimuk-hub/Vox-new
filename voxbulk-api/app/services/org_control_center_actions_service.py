"""Admin actions for Organisation Control Center — billing, campaigns, promos, overage."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.billing_invoice import BillingInvoice
from app.models.organisation import Organisation
from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.models.subscription import Subscription
from app.services.billing_currency import resolve_org_currency
from app.services.billing_event_email_service import BillingEventEmailService
from app.services.billing_lifecycle_service import BillingLifecycleService
from app.services.invoice_service import InvoiceService
from app.services.org_audit_service import OrgAuditService
from app.services.org_billing_profile_service import resolve_org_billing_profile, sync_org_country_code
from app.services.org_service_credit_service import OrgServiceCreditError, OrgServiceCreditService
from app.services.platform_catalog_service import ServiceOrderService
from app.services.promo_offer_service import PromoOfferError, PromoOfferService
from app.services.usage_wallet_service import UsageWalletService
from app.services.wallet_service import InsufficientWalletBalance, WalletService

_FAILED_RECIPIENT = frozenset({"failed", "error", "cancelled", "rejected", "no_answer", "busy"})


class OrgControlCenterActionsService:
    @staticmethod
    def _actor(payload: dict | None) -> tuple[str | None, str | None]:
        p = payload or {}
        return (
            str(p.get("actor_user_id") or "").strip() or None,
            str(p.get("actor_email") or "").strip() or None,
        )

    @staticmethod
    def credit_wallet(
        db: Session,
        org_id: str,
        *,
        amount_minor: int,
        reason: str,
        actor_user_id: str | None = None,
        actor_email: str | None = None,
    ) -> dict[str, Any]:
        result = BillingLifecycleService.admin_wallet_credit(
            db,
            org_id=org_id,
            amount_minor=amount_minor,
            reason=reason,
            created_by_user_id=actor_user_id,
        )
        OrgAuditService.record_admin(
            db,
            org_id=org_id,
            event_type="wallet.credit",
            action=f"Wallet credited — {amount_minor / 100:.2f}",
            entity_type="wallet_transaction",
            entity_id=result.get("wallet_transaction_id"),
            detail=reason,
            metadata={"amount_minor": amount_minor, **result},
            actor_user_id=actor_user_id,
            actor_email=actor_email,
        )
        org = db.get(Organisation, org_id)
        from app.services.payment_event_service import PaymentEventService

        PaymentEventService.record_finance(
            db,
            org_id=org_id,
            client_email=(org.contact_email if org else None) or actor_email or "admin@voxbulk.com",
            event_kind="wallet.credit",
            actor_user_id=actor_user_id,
            metadata={"amount_minor": amount_minor, **result},
        )
        return {"ok": True, **result, **WalletService.wallet_dict(db, org)}

    @staticmethod
    def debit_wallet(
        db: Session,
        org_id: str,
        *,
        amount_minor: int,
        reason: str,
        actor_user_id: str | None = None,
        actor_email: str | None = None,
    ) -> dict[str, Any]:
        org = db.get(Organisation, org_id)
        if org is None:
            raise ValueError("Organisation not found")
        amount = int(amount_minor or 0)
        if amount <= 0:
            raise ValueError("amount_minor must be positive")
        try:
            tx = WalletService.debit(
            db,
            org,
            amount_minor=amount,
            kind="admin_debit",
            description=(reason or "Admin wallet debit")[:255],
            created_by_user_id=actor_user_id,
            metadata={"trigger": "admin_debit"},
        )
        except InsufficientWalletBalance as exc:
            raise ValueError(str(exc)) from exc
        OrgAuditService.record_admin(
            db,
            org_id=org_id,
            event_type="wallet.debit",
            action=f"Wallet debited — {amount / 100:.2f}",
            entity_type="wallet_transaction",
            entity_id=tx.id,
            detail=reason,
            metadata={"amount_minor": amount, "transaction_id": tx.id},
            actor_user_id=actor_user_id,
            actor_email=actor_email,
        )
        from app.services.payment_event_service import PaymentEventService

        PaymentEventService.record_finance(
            db,
            org_id=org_id,
            client_email=org.contact_email or actor_email or "admin@voxbulk.com",
            event_kind="wallet.debit",
            actor_user_id=actor_user_id,
            metadata={"amount_minor": amount, "transaction_id": tx.id},
        )
        return {"ok": True, "wallet_transaction": WalletService.transaction_to_dict(tx), **WalletService.wallet_dict(db, org)}

    @staticmethod
    def refund_wallet(
        db: Session,
        org_id: str,
        *,
        amount_minor: int,
        reason: str,
        invoice_id: str | None = None,
        order_id: str | None = None,
        actor_user_id: str | None = None,
        actor_email: str | None = None,
    ) -> dict[str, Any]:
        org = db.get(Organisation, org_id)
        if org is None:
            raise ValueError("Organisation not found")
        currency = resolve_org_currency(db, org)
        result = BillingLifecycleService.issue_wallet_refund(
            db,
            org,
            amount_minor=amount_minor,
            currency=currency,
            reason=reason or "Admin wallet refund",
            invoice_id=invoice_id,
            order_id=order_id,
            trigger="admin_refund",
            created_by_user_id=actor_user_id,
        )
        OrgAuditService.record_admin(
            db,
            org_id=org_id,
            event_type="wallet.refund",
            action=f"Wallet refunded — {int(amount_minor or 0) / 100:.2f}",
            entity_type="wallet_transaction",
            entity_id=result.get("wallet_transaction_id"),
            detail=reason,
            metadata={"amount_minor": amount_minor, **result},
            actor_user_id=actor_user_id,
            actor_email=actor_email,
        )
        from app.services.payment_event_service import PaymentEventService

        PaymentEventService.record_finance(
            db,
            org_id=org_id,
            client_email=org.contact_email or actor_email or "admin@voxbulk.com",
            event_kind="wallet.refund",
            actor_user_id=actor_user_id,
            metadata={"amount_minor": amount_minor, "currency": currency, **result},
        )
        return {"ok": True, **result, **WalletService.wallet_dict(db, org)}

    @staticmethod
    def reverse_wallet_transaction(
        db: Session,
        org_id: str,
        transaction_id: str,
        *,
        reason: str,
        actor_user_id: str | None = None,
        actor_email: str | None = None,
    ) -> dict[str, Any]:
        from app.models.wallet_transaction import WalletTransaction

        org = db.get(Organisation, org_id)
        if org is None:
            raise ValueError("Organisation not found")
        tx = db.get(WalletTransaction, transaction_id)
        if tx is None or tx.org_id != org_id:
            raise ValueError("Wallet transaction not found")
        amount = int(tx.amount_minor or 0)
        if amount <= 0:
            raise ValueError("Invalid transaction amount")
        note = (reason or "Admin reversal")[:255]
        if tx.direction == "debit":
            result = BillingLifecycleService.issue_wallet_refund(
                db,
                org,
                amount_minor=amount,
                currency=tx.currency or resolve_org_currency(db, org),
                reason=f"Reversal of {tx.id[:8]} — {note}",
                order_id=tx.order_id,
                invoice_id=tx.invoice_id,
                trigger="admin_reversal",
                created_by_user_id=actor_user_id,
            )
            event = "wallet.reversal_credit"
        else:
            reversed_tx = WalletService.debit(
                db,
                org,
                amount_minor=amount,
                kind="admin_reversal",
                description=f"Reversal of credit {tx.id[:8]} — {note}"[:255],
                order_id=tx.order_id,
                invoice_id=tx.invoice_id,
                created_by_user_id=actor_user_id,
                metadata={"reversed_transaction_id": tx.id},
            )
            result = {"wallet_transaction_id": reversed_tx.id, "wallet_transaction": WalletService.transaction_to_dict(reversed_tx)}
            event = "wallet.reversal_debit"
        OrgAuditService.record_admin(
            db,
            org_id=org_id,
            event_type=event,
            action=f"Wallet transaction reversed — {tx.id[:8]}",
            entity_type="wallet_transaction",
            entity_id=result.get("wallet_transaction_id"),
            detail=note,
            metadata={"reversed_transaction_id": tx.id, "amount_minor": amount, **result},
            actor_user_id=actor_user_id,
            actor_email=actor_email,
        )
        from app.services.payment_event_service import PaymentEventService

        PaymentEventService.record_finance(
            db,
            org_id=org_id,
            client_email=org.contact_email or actor_email or "admin@voxbulk.com",
            event_kind=event,
            actor_user_id=actor_user_id,
            metadata={"reversed_transaction_id": tx.id, "amount_minor": amount, **result},
        )
        return {"ok": True, **result, **WalletService.wallet_dict(db, org)}

    @staticmethod
    def collect_invoice_payment(
        db: Session,
        org_id: str,
        invoice_id: str,
        *,
        method: str = "wallet",
        actor_user_id: str | None = None,
        actor_email: str | None = None,
    ) -> dict[str, Any]:
        from app.services.invoice_payment_service import InvoicePaymentError, InvoicePaymentService

        org = db.get(Organisation, org_id)
        if org is None:
            raise ValueError("Organisation not found")
        invoice = InvoiceService.get_for_org(db, invoice_id=invoice_id, org_id=org_id)
        if invoice is None:
            raise ValueError("Invoice not found")
        try:
            result = InvoicePaymentService.pay_invoice(db, org, invoice, method=method, user_id=actor_user_id)
        except InvoicePaymentError as exc:
            raise ValueError(str(exc)) from exc
        OrgAuditService.record_admin(
            db,
            org_id=org_id,
            event_type="invoice.collect",
            action=f"Invoice payment collected — {invoice.invoice_number or invoice.id[:8]}",
            entity_type="invoice",
            entity_id=invoice.id,
            metadata={"method": method},
            actor_user_id=actor_user_id,
            actor_email=actor_email,
        )
        return result

    @staticmethod
    def adjust_credits(
        db: Session,
        org_id: str,
        *,
        service_code: str,
        delta: int,
        reason: str,
        actor_user_id: str | None = None,
        actor_email: str | None = None,
    ) -> dict[str, Any]:
        org = db.get(Organisation, org_id)
        if org is None:
            raise ValueError("Organisation not found")
        code = str(service_code or "").strip().lower()
        change = int(delta or 0)
        if change == 0:
            raise ValueError("delta must be non-zero")
        if change > 0:
            org = OrgServiceCreditService.grant(db, org, service_code=code, amount=change)
        else:
            field = "survey_credits_balance" if code == "survey" else "interview_credits_balance"
            current = int(getattr(org, field) or 0)
            next_val = max(0, current + change)
            setattr(org, field, next_val)
            db.add(org)
            db.commit()
            db.refresh(org)
        OrgAuditService.record_admin(
            db,
            org_id=org_id,
            event_type="credits.adjust",
            action=f"{'Added' if change > 0 else 'Removed'} {abs(change)} {code} credits",
            entity_type="organisation",
            entity_id=org_id,
            detail=reason,
            metadata={"service_code": code, "delta": change, "balances": OrgServiceCreditService.balances_dict(org)},
            actor_user_id=actor_user_id,
            actor_email=actor_email,
        )
        return {"ok": True, **OrgServiceCreditService.balances_dict(org)}

    @staticmethod
    def apply_promo(
        db: Session,
        org_id: str,
        *,
        promo_code: str,
        actor_user_id: str | None = None,
        actor_email: str | None = None,
    ) -> dict[str, Any]:
        try:
            row = PromoOfferService.redeem_for_org(db, org_id=org_id, user_id=actor_user_id, promo_code=promo_code)
        except PromoOfferError as e:
            raise ValueError(str(e)) from e
        OrgAuditService.record_admin(
            db,
            org_id=org_id,
            event_type="promo.apply",
            action=f"Promo applied — {row.code}",
            entity_type="promo_offer",
            entity_id=row.id,
            metadata={"promo_code": row.code, "offer_type": row.offer_type},
            actor_user_id=actor_user_id,
            actor_email=actor_email,
        )
        org = db.get(Organisation, org_id)
        return {"ok": True, "promo_code": row.code, "balances": OrgServiceCreditService.balances_dict(org) if org else {}}

    @staticmethod
    def set_allow_overage(
        db: Session,
        org_id: str,
        *,
        allow_overage: bool,
        reason: str | None = None,
        actor_user_id: str | None = None,
        actor_email: str | None = None,
    ) -> dict[str, Any]:
        org = db.get(Organisation, org_id)
        if org is None:
            raise ValueError("Organisation not found")
        org.allow_overage = bool(allow_overage)
        db.add(org)
        db.commit()
        db.refresh(org)
        OrgAuditService.record_admin(
            db,
            org_id=org_id,
            event_type="overage.toggle",
            action=f"Overage {'enabled' if allow_overage else 'disabled'}",
            entity_type="organisation",
            entity_id=org_id,
            detail=reason,
            metadata={"allow_overage": allow_overage},
            actor_user_id=actor_user_id,
            actor_email=actor_email,
        )
        return {"ok": True, "allow_overage": org.allow_overage}

    @staticmethod
    def set_billing_payment_provider(
        db: Session,
        org_id: str,
        *,
        billing_payment_provider: str | None,
        reason: str | None = None,
        actor_user_id: str | None = None,
        actor_email: str | None = None,
    ) -> dict[str, Any]:
        org = db.get(Organisation, org_id)
        if org is None:
            raise ValueError("Organisation not found")
        raw = str(billing_payment_provider or "").strip().lower()
        if raw in {"", "auto", "country", "default"}:
            org.billing_payment_provider = None
        elif raw in {"gocardless", "airwallex", "stripe"}:
            org.billing_payment_provider = raw
        else:
            raise ValueError("billing_payment_provider must be auto, gocardless, airwallex, or stripe")
        db.add(org)
        db.commit()
        db.refresh(org)
        from app.services.payment_provider_router import PaymentProviderRouter

        OrgAuditService.record_admin(
            db,
            org_id=org_id,
            event_type="billing.payment_provider",
            action=f"Subscription checkout provider set to {org.billing_payment_provider or 'auto (country)'}",
            entity_type="organisation",
            entity_id=org_id,
            detail=reason,
            metadata={"billing_payment_provider": org.billing_payment_provider},
            actor_user_id=actor_user_id,
            actor_email=actor_email,
        )
        return {
            "ok": True,
            "billing_payment_provider": org.billing_payment_provider,
            "subscription_routing": PaymentProviderRouter.routing_explain(db, org),
        }

    @staticmethod
    def create_invoice(
        db: Session,
        org_id: str,
        *,
        amount_minor: int,
        invoice_type: str,
        due_date: str | None = None,
        note: str | None = None,
        actor_user_id: str | None = None,
        actor_email: str | None = None,
    ) -> dict[str, Any]:
        org = db.get(Organisation, org_id)
        if org is None:
            raise ValueError("Organisation not found")
        profile = resolve_org_billing_profile(db, org)
        email = profile.get("billing_email") or org.contact_email
        if not email:
            raise ValueError("No billing email on organisation profile")
        currency = resolve_org_currency(db, org, persist=True)
        sync_org_country_code(db, org, commit=False)
        due_dt = None
        if due_date:
            try:
                due_dt = datetime.fromisoformat(str(due_date).replace("Z", "+00:00"))
            except ValueError:
                due_dt = datetime.strptime(str(due_date)[:10], "%Y-%m-%d")
        kind_map = {
            "subscription": "subscription",
            "service_order": "campaign",
            "overage": "overage",
            "manual": "topup",
            "manual adjustment": "topup",
        }
        kind = kind_map.get(str(invoice_type or "").strip().lower(), "topup")
        external_id = f"manual-{org_id[:8]}-{uuid.uuid4().hex[:10]}"
        invoice = InvoiceService.create_from_payment(
            db,
            org_id=org_id,
            client_email=str(email).strip().lower(),
            subtotal_pence=int(amount_minor),
            currency=currency,
            description=(note or f"Manual {invoice_type} invoice")[:255],
            provider="internal",
            external_invoice_id=external_id,
            payment_method=profile.get("payment_method"),
            status="due",
            kind=kind,
            country_code=profile.get("country_code"),
        )
        if due_dt is not None:
            invoice.due_date = due_dt
            db.add(invoice)
            db.commit()
            db.refresh(invoice)
        sent = OrgControlCenterActionsService._send_invoice_email(db, invoice)
        OrgAuditService.record_admin(
            db,
            org_id=org_id,
            event_type="invoice.created",
            action=f"Invoice created — {invoice.invoice_number or invoice.id[:8]}",
            entity_type="invoice",
            entity_id=invoice.id,
            metadata={"amount_minor": amount_minor, "kind": kind, "emailed": sent},
            actor_user_id=actor_user_id,
            actor_email=actor_email,
        )
        return {"ok": True, "invoice": InvoiceService.invoice_to_dict(db, invoice), "emailed": sent}

    @staticmethod
    def edit_invoice(
        db: Session,
        org_id: str,
        invoice_id: str,
        *,
        payload: dict[str, Any],
        actor_user_id: str | None = None,
        actor_email: str | None = None,
    ) -> dict[str, Any]:
        from app.services.invoice_lifecycle_service import InvoiceLifecycleError, InvoiceLifecycleService

        invoice = InvoiceService.get_for_org(db, invoice_id=invoice_id, org_id=org_id)
        if invoice is None:
            raise ValueError("Invoice not found")
        try:
            updated = InvoiceLifecycleService.edit_invoice(
                db,
                invoice,
                description=payload.get("description"),
                due_date=payload.get("due_date"),
                amount_minor=int(payload["amount_minor"]) if payload.get("amount_minor") is not None else None,
                client_email=payload.get("client_email"),
                actor_user_id=actor_user_id,
                actor_email=actor_email,
            )
        except InvoiceLifecycleError as exc:
            raise ValueError(str(exc)) from exc
        return {"ok": True, "invoice": InvoiceService.invoice_to_dict(db, updated)}

    @staticmethod
    def void_invoice(
        db: Session,
        org_id: str,
        invoice_id: str,
        *,
        reason: str | None = None,
        actor_user_id: str | None = None,
        actor_email: str | None = None,
    ) -> dict[str, Any]:
        from app.services.invoice_lifecycle_service import InvoiceLifecycleError, InvoiceLifecycleService

        invoice = InvoiceService.get_for_org(db, invoice_id=invoice_id, org_id=org_id)
        if invoice is None:
            raise ValueError("Invoice not found")
        try:
            updated = InvoiceLifecycleService.void_invoice(
                db,
                invoice,
                reason=reason,
                actor_user_id=actor_user_id,
                actor_email=actor_email,
            )
        except InvoiceLifecycleError as exc:
            raise ValueError(str(exc)) from exc
        return {"ok": True, "invoice": InvoiceService.invoice_to_dict(db, updated)}

    @staticmethod
    def mark_invoice_paid(
        db: Session,
        org_id: str,
        invoice_id: str,
        *,
        note: str | None = None,
        actor_user_id: str | None = None,
        actor_email: str | None = None,
    ) -> dict[str, Any]:
        invoice = InvoiceService.get_for_org(db, invoice_id=invoice_id, org_id=org_id)
        if invoice is None:
            raise ValueError("Invoice not found")
        invoice.status = "paid"
        invoice.payment_reference = (note or invoice.payment_reference or "manual")[:128]
        db.add(invoice)
        from app.services.invoice_payment_service import InvoicePaymentService

        InvoicePaymentService._sync_linked_order_after_payment(db, invoice)
        db.commit()
        db.refresh(invoice)
        OrgAuditService.record_admin(
            db,
            org_id=org_id,
            event_type="invoice.paid",
            action=f"Invoice marked paid — {invoice.invoice_number or invoice.id[:8]}",
            entity_type="invoice",
            entity_id=invoice.id,
            detail=note,
            actor_user_id=actor_user_id,
            actor_email=actor_email,
        )
        return {"ok": True, "invoice": InvoiceService.invoice_to_dict(db, invoice)}

    @staticmethod
    def reissue_invoice(
        db: Session,
        org_id: str,
        invoice_id: str,
        *,
        actor_user_id: str | None = None,
        actor_email: str | None = None,
    ) -> dict[str, Any]:
        source = InvoiceService.get_for_org(db, invoice_id=invoice_id, org_id=org_id)
        if source is None:
            raise ValueError("Invoice not found")
        org = db.get(Organisation, org_id)
        currency = str(source.currency or resolve_org_currency(db, org))
        external_id = f"reissue-{source.id[:8]}-{uuid.uuid4().hex[:8]}"
        amount = int(source.subtotal_pence if source.subtotal_pence is not None else source.amount_gbp_pence or 0)
        new_inv = InvoiceService.create_from_payment(
            db,
            org_id=org_id,
            client_email=source.client_email,
            subtotal_pence=amount,
            currency=currency,
            description=f"Reissue of {source.invoice_number or source.id}"[:255],
            provider="internal",
            external_invoice_id=external_id,
            payment_method=source.payment_method,
            status=source.status if str(source.status).lower() != "paid" else "due",
            kind=source.kind,
            order_id=source.order_id,
            country_code=source.country_code,
        )
        if source.due_date:
            new_inv.due_date = source.due_date
            db.add(new_inv)
            db.commit()
            db.refresh(new_inv)
        sent = OrgControlCenterActionsService._send_invoice_email(db, new_inv)
        OrgAuditService.record_admin(
            db,
            org_id=org_id,
            event_type="invoice.reissued",
            action=f"Invoice reissued from {source.invoice_number or source.id[:8]}",
            entity_type="invoice",
            entity_id=new_inv.id,
            metadata={"source_invoice_id": source.id, "emailed": sent},
            actor_user_id=actor_user_id,
            actor_email=actor_email,
        )
        return {"ok": True, "invoice": InvoiceService.invoice_to_dict(db, new_inv), "emailed": sent}

    @staticmethod
    def resend_invoice_email(
        db: Session,
        org_id: str,
        invoice_id: str,
        *,
        actor_user_id: str | None = None,
        actor_email: str | None = None,
    ) -> dict[str, Any]:
        invoice = InvoiceService.get_for_org(db, invoice_id=invoice_id, org_id=org_id)
        if invoice is None:
            raise ValueError("Invoice not found")
        sent = OrgControlCenterActionsService._send_invoice_email(db, invoice, resent=True)
        OrgAuditService.record_admin(
            db,
            org_id=org_id,
            event_type="invoice.email_resent",
            action=f"Invoice email resent — {invoice.invoice_number or invoice.id[:8]}",
            entity_type="invoice",
            entity_id=invoice.id,
            metadata={"sent": sent},
            actor_user_id=actor_user_id,
            actor_email=actor_email,
        )
        return {"ok": sent, "sent": sent, "invoice": InvoiceService.invoice_to_dict(db, invoice)}

    @staticmethod
    def _send_invoice_email(db: Session, invoice: BillingInvoice, *, resent: bool = False) -> bool:
        invoice.invoice_email_attempts = int(getattr(invoice, "invoice_email_attempts", 0) or 0) + 1
        ok, err = BillingEventEmailService.send_invoice_email(db, invoice=invoice)
        if ok:
            invoice.emailed_at = datetime.utcnow()
            invoice.invoice_email_status = "resent" if resent else "sent"
            invoice.invoice_email_last_error = None
        else:
            invoice.invoice_email_status = "failed"
            invoice.invoice_email_last_error = (err or "send failed")[:2000]
        db.add(invoice)
        db.commit()
        db.refresh(invoice)
        return ok

    @staticmethod
    def issue_order_payment_invoice(
        db: Session,
        order: ServiceOrder,
        *,
        actor_user_id: str | None = None,
        actor_email: str | None = None,
    ) -> dict[str, Any] | None:
        if int(order.quote_total_pence or 0) <= 0:
            return None
        org = db.get(Organisation, order.org_id)
        if org is None:
            return None
        profile = resolve_org_billing_profile(db, org)
        email = profile.get("billing_email") or org.contact_email
        if not email:
            return None
        currency = resolve_org_currency(db, org, persist=True)
        external_id = f"order-{order.id}"
        existing = InvoiceService.get_by_external(db, provider="internal", external_invoice_id=external_id)
        if existing is not None:
            return {"invoice": InvoiceService.invoice_to_dict(db, existing), "created": False}
        amount = int(order.quote_total_pence or 0)
        from app.services.invoice_line_item_service import InvoiceLineItemService

        line_items = InvoiceLineItemService.from_order(order)
        invoice, created, sent = InvoiceService.issue_from_payment(
            db,
            org_id=order.org_id,
            client_email=str(email).strip().lower(),
            subtotal_pence=amount,
            currency=currency,
            description=f"Service order — {order.title or order.service_code}"[:255],
            provider="internal",
            external_invoice_id=external_id,
            payment_method=order.payment_method or profile.get("payment_method"),
            status="paid",
            line_items=line_items or [
                {
                    "description": order.title or order.service_code,
                    "quantity": max(1, int(order.recipient_count or 1)),
                    "unit_pence": amount,
                    "total_pence": amount,
                }
            ],
            country_code=profile.get("country_code"),
            kind="campaign",
            order_id=order.id,
        )
        if created:
            OrgAuditService.record_admin(
                db,
                org_id=order.org_id,
                event_type="invoice.issued",
                action=f"Invoice issued for order {order.id[:8]}",
                entity_type="invoice",
                entity_id=invoice.id,
                metadata={"order_id": order.id, "emailed": sent},
                actor_user_id=actor_user_id,
                actor_email=actor_email,
            )
        return {"invoice": InvoiceService.invoice_to_dict(db, invoice), "created": created, "emailed": sent}

    @staticmethod
    def campaign_action(
        db: Session,
        org_id: str,
        order_id: str,
        action: str,
        *,
        actor_user_id: str | None = None,
        actor_email: str | None = None,
    ) -> dict[str, Any]:
        order = db.get(ServiceOrder, order_id)
        if order is None or order.org_id != org_id:
            raise ValueError("Order not found")
        act = str(action or "").strip().lower()
        if act == "pause":
            order = ServiceOrderService.pause_order(db, order)
        elif act == "resume":
            order = ServiceOrderService.resume_order(db, order)
        elif act == "stop":
            order = ServiceOrderService.stop_order(db, order, reason="Stopped by admin")
        elif act == "start":
            order = ServiceOrderService.start_order(db, order)
        else:
            raise ValueError(f"Unknown campaign action: {action}")
        OrgAuditService.record_admin(
            db,
            org_id=org_id,
            event_type=f"campaign.{act}",
            action=f"Campaign {act} — order {order.id[:8]}",
            entity_type="service_order",
            entity_id=order.id,
            metadata={"status": order.status},
            actor_user_id=actor_user_id,
            actor_email=actor_email,
        )
        return {"ok": True, "order": ServiceOrderService.order_to_admin_dict(db, order)}

    @staticmethod
    def stop_all_campaigns(
        db: Session,
        org_id: str,
        *,
        actor_user_id: str | None = None,
        actor_email: str | None = None,
    ) -> dict[str, Any]:
        rows = list(
            db.execute(
                select(ServiceOrder).where(
                    ServiceOrder.org_id == org_id,
                    ServiceOrder.status.in_(("running", "paused", "scheduled", "paid")),
                )
            )
            .scalars()
            .all()
        )
        stopped = []
        for order in rows:
            ServiceOrderService.stop_order(db, order, reason="Stopped by admin (bulk)")
            stopped.append(order.id)
        if stopped:
            OrgAuditService.record_admin(
                db,
                org_id=org_id,
                event_type="campaign.stop_all",
                action=f"Stopped {len(stopped)} campaign(s)",
                entity_type="organisation",
                entity_id=org_id,
                metadata={"order_ids": stopped},
                actor_user_id=actor_user_id,
                actor_email=actor_email,
            )
        return {"ok": True, "stopped": len(stopped), "order_ids": stopped}

    @staticmethod
    def retry_failed_recipients(
        db: Session,
        org_id: str,
        order_id: str,
        *,
        actor_user_id: str | None = None,
        actor_email: str | None = None,
    ) -> dict[str, Any]:
        order = db.get(ServiceOrder, order_id)
        if order is None or order.org_id != org_id:
            raise ValueError("Order not found")
        recipients = list(
            db.execute(select(ServiceOrderRecipient).where(ServiceOrderRecipient.order_id == order.id)).scalars().all()
        )
        retried = 0
        for r in recipients:
            if str(r.status or "").lower() in _FAILED_RECIPIENT:
                r.status = "pending"
                r.updated_at = datetime.utcnow()
                db.add(r)
                retried += 1
        if retried:
            db.commit()
            if str(order.status or "").lower() in {"paused", "paid", "scheduled"}:
                try:
                    order = ServiceOrderService.start_order(db, order)
                except ValueError:
                    order = ServiceOrderService.resume_order(db, order)
        OrgAuditService.record_admin(
            db,
            org_id=org_id,
            event_type="campaign.retry_failed",
            action=f"Retried {retried} failed recipient(s) on order {order.id[:8]}",
            entity_type="service_order",
            entity_id=order.id,
            metadata={"retried": retried},
            actor_user_id=actor_user_id,
            actor_email=actor_email,
        )
        return {"ok": True, "retried": retried}

    @staticmethod
    def purge_queued_campaigns(
        db: Session,
        org_id: str,
        *,
        actor_user_id: str | None = None,
        actor_email: str | None = None,
    ) -> dict[str, Any]:
        rows = list(
            db.execute(
                select(ServiceOrder).where(
                    ServiceOrder.org_id == org_id,
                    ServiceOrder.status.in_(("scheduled", "paid", "draft")),
                    ServiceOrder.payment_status == "approved",
                )
            )
            .scalars()
            .all()
        )
        purged = []
        for order in rows:
            ServiceOrderService.stop_order(db, order, reason="Purged queued campaign")
            purged.append(order.id)
        if purged:
            OrgAuditService.record_admin(
                db,
                org_id=org_id,
                event_type="campaign.purge_queue",
                action=f"Purged {len(purged)} queued campaign(s)",
                entity_type="organisation",
                entity_id=org_id,
                metadata={"order_ids": purged},
                actor_user_id=actor_user_id,
                actor_email=actor_email,
            )
        return {"ok": True, "purged": len(purged), "order_ids": purged}

    @staticmethod
    def set_suspended(
        db: Session,
        org_id: str,
        *,
        suspended: bool,
        reason: str | None = None,
        actor_user_id: str | None = None,
        actor_email: str | None = None,
    ) -> dict[str, Any]:
        org = db.get(Organisation, org_id)
        if org is None:
            raise ValueError("Organisation not found")
        org.is_suspended = bool(suspended)
        db.add(org)
        db.commit()
        db.refresh(org)
        OrgAuditService.record_admin(
            db,
            org_id=org_id,
            event_type="account.freeze" if suspended else "account.unfreeze",
            action="Account frozen" if suspended else "Account activated",
            entity_type="organisation",
            entity_id=org_id,
            detail=reason,
            actor_user_id=actor_user_id,
            actor_email=actor_email,
        )
        return {"ok": True, "is_suspended": org.is_suspended}

    @staticmethod
    def save_profile_notes(
        db: Session,
        org_id: str,
        *,
        profile_notes: str | None,
        actor_user_id: str | None = None,
        actor_email: str | None = None,
    ) -> dict[str, Any]:
        org = db.get(Organisation, org_id)
        if org is None:
            raise ValueError("Organisation not found")
        org.profile_notes = str(profile_notes).strip() if profile_notes else None
        db.add(org)
        db.commit()
        db.refresh(org)
        OrgAuditService.record_admin(
            db,
            org_id=org_id,
            event_type="support.notes",
            action="Support notes updated",
            entity_type="organisation",
            entity_id=org_id,
            actor_user_id=actor_user_id,
            actor_email=actor_email,
        )
        return {"ok": True, "profile_notes": org.profile_notes}

    @staticmethod
    def wallet_history(db: Session, org_id: str, *, limit: int = 250) -> list[dict[str, Any]]:
        rows = WalletService.list_transactions(db, org_id, limit=limit)
        return [WalletService.transaction_to_dict(r) for r in rows]
