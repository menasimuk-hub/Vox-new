"""Invoice edit/void lifecycle rules — admin billing policy."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.billing_invoice import BillingInvoice
from app.models.organisation import Organisation
from app.services.country_vat_service import CountryVatService
from app.services.invoice_service import InvoiceService
from app.services.org_audit_service import OrgAuditService

LOCKED_STATUSES = frozenset({"paid", "refunded", "credited", "void", "cancelled", "disputed"})
COLLECTION_STATUSES = frozenset({"collecting", "pending"})
EDITABLE_STATUSES = frozenset({"draft", "open", "issued", "due", "failed", "past_due", "overdue", "unpaid", "sent"})
VOIDABLE_STATUSES = frozenset({"draft", "open", "issued", "due", "failed", "past_due", "overdue", "unpaid", "sent"})


class InvoiceLifecycleError(ValueError):
    pass


class InvoiceLifecycleService:
    @staticmethod
    def _status(invoice: BillingInvoice) -> str:
        return str(invoice.status or "issued").strip().lower()

    @staticmethod
    def is_dd_collection_active(invoice: BillingInvoice) -> bool:
        st = InvoiceLifecycleService._status(invoice)
        if st in COLLECTION_STATUSES:
            return True
        if st == "pending" and getattr(invoice, "dd_payment_id", None):
            return True
        return False

    @staticmethod
    def policy(invoice: BillingInvoice) -> dict[str, Any]:
        st = InvoiceLifecycleService._status(invoice)
        disputed = bool(getattr(invoice, "disputed", False))
        dd_active = InvoiceLifecycleService.is_dd_collection_active(invoice)

        if disputed or st in {"disputed", "refunded", "credited"}:
            return {
                "can_edit": False,
                "can_void": False,
                "is_locked": True,
                "lock_reason": "This invoice is locked after dispute or refund processing.",
                "suggested_action": "issue_credit_note",
                "suggested_action_label": "Issue a credit note or reissue instead of editing.",
                "editable_fields": [],
                "status": st,
            }

        if st == "paid":
            return {
                "can_edit": False,
                "can_void": False,
                "is_locked": True,
                "lock_reason": "Paid invoices cannot be edited or voided.",
                "suggested_action": "credit_note_or_reissue",
                "suggested_action_label": "Use refund, credit note, or reissue for corrections.",
                "editable_fields": [],
                "status": st,
            }

        if st in {"void", "cancelled"}:
            return {
                "can_edit": False,
                "can_void": False,
                "is_locked": True,
                "lock_reason": "This invoice is already void/cancelled.",
                "suggested_action": "reissue",
                "suggested_action_label": "Create a new invoice if billing is still required.",
                "editable_fields": [],
                "status": st,
            }

        if dd_active:
            return {
                "can_edit": False,
                "can_void": False,
                "is_locked": True,
                "lock_reason": "Direct Debit collection is in progress.",
                "suggested_action": "stop_collection",
                "suggested_action_label": "Stop DD collection safely before editing or voiding.",
                "editable_fields": [],
                "status": st,
            }

        can_void = st in VOIDABLE_STATUSES
        can_edit = st in EDITABLE_STATUSES
        editable_fields = ["description", "due_date", "amount_minor", "client_email"] if can_edit else []

        return {
            "can_edit": can_edit,
            "can_void": can_void,
            "is_locked": False,
            "lock_reason": None,
            "suggested_action": None,
            "suggested_action_label": None,
            "editable_fields": editable_fields,
            "status": st,
        }

    @staticmethod
    def enrich_invoice_dict(base: dict[str, Any], invoice: BillingInvoice) -> dict[str, Any]:
        policy = InvoiceLifecycleService.policy(invoice)
        return {**base, "lifecycle": policy}

    @staticmethod
    def edit_invoice(
        db: Session,
        invoice: BillingInvoice,
        *,
        description: str | None = None,
        due_date: str | None = None,
        amount_minor: int | None = None,
        client_email: str | None = None,
        actor_user_id: str | None = None,
        actor_email: str | None = None,
    ) -> BillingInvoice:
        policy = InvoiceLifecycleService.policy(invoice)
        if not policy["can_edit"]:
            raise InvoiceLifecycleError(policy.get("lock_reason") or "This invoice cannot be edited.")

        org = db.get(Organisation, invoice.org_id)
        if org is None:
            raise InvoiceLifecycleError("Organisation not found")

        changes: dict[str, Any] = {}
        if description is not None:
            invoice.description = str(description).strip()[:255] or None
            changes["description"] = invoice.description
        if client_email is not None:
            invoice.client_email = str(client_email).strip().lower()[:320]
            changes["client_email"] = invoice.client_email
        if due_date is not None:
            raw = str(due_date).strip()
            if raw:
                try:
                    invoice.due_date = datetime.fromisoformat(raw.replace("Z", "+00:00")).replace(tzinfo=None)
                except ValueError as exc:
                    raise InvoiceLifecycleError("Invalid due_date") from exc
                changes["due_date"] = invoice.due_date.isoformat()
        if amount_minor is not None:
            subtotal = max(0, int(amount_minor))
            code = (invoice.country_code or CountryVatService.resolve_org_country_code(db, org)).upper()[:2]
            rate = InvoiceService.effective_vat_rate(db, country_code=code)
            tax = CountryVatService.compute_tax(subtotal, rate)
            total = subtotal + tax
            invoice.subtotal_pence = subtotal
            invoice.tax_pence = tax
            invoice.tax_rate_percent = rate
            invoice.amount_gbp_pence = total
            changes["subtotal_pence"] = subtotal
            changes["amount_gbp_pence"] = total

        if not changes:
            raise InvoiceLifecycleError("No editable fields provided.")

        db.add(invoice)
        OrgAuditService.record_admin(
            db,
            org_id=invoice.org_id,
            event_type="invoice.edited",
            action=f"Invoice edited — {invoice.invoice_number or invoice.id[:8]}",
            entity_type="invoice",
            entity_id=invoice.id,
            metadata=changes,
            actor_user_id=actor_user_id,
            actor_email=actor_email,
        )
        db.commit()
        db.refresh(invoice)
        return invoice

    @staticmethod
    def void_invoice(
        db: Session,
        invoice: BillingInvoice,
        *,
        reason: str | None = None,
        actor_user_id: str | None = None,
        actor_email: str | None = None,
    ) -> BillingInvoice:
        policy = InvoiceLifecycleService.policy(invoice)
        if not policy["can_void"]:
            msg = policy.get("lock_reason") or "This invoice cannot be voided."
            suggested = policy.get("suggested_action_label")
            if suggested:
                msg = f"{msg} {suggested}"
            raise InvoiceLifecycleError(msg)

        invoice.status = "void"
        invoice.dd_next_retry_at = None
        note = (reason or "Voided by admin")[:512]
        if invoice.description:
            invoice.description = f"{invoice.description}\n[VOID: {note}]"[:255]
        db.add(invoice)
        OrgAuditService.record_admin(
            db,
            org_id=invoice.org_id,
            event_type="invoice.voided",
            action=f"Invoice voided — {invoice.invoice_number or invoice.id[:8]}",
            entity_type="invoice",
            entity_id=invoice.id,
            detail=note,
            actor_user_id=actor_user_id,
            actor_email=actor_email,
        )
        from app.models.organisation import Organisation
        from app.services.payment_event_service import PaymentEventService

        org = db.get(Organisation, invoice.org_id)
        PaymentEventService.record_finance(
            db,
            org_id=invoice.org_id,
            client_email=(org.contact_email if org else None) or actor_email or "admin@voxbulk.com",
            event_kind="invoice.voided",
            actor_user_id=actor_user_id,
            metadata={"invoice_id": invoice.id, "reason": note},
            commit=False,
        )
        db.commit()
        db.refresh(invoice)
        return invoice

    @staticmethod
    def stop_dd_collection(
        db: Session,
        invoice: BillingInvoice,
        *,
        reason: str | None = None,
        actor_user_id: str | None = None,
        actor_email: str | None = None,
    ) -> BillingInvoice:
        if not InvoiceLifecycleService.is_dd_collection_active(invoice):
            raise InvoiceLifecycleError("No active Direct Debit collection on this invoice.")

        payment_id = str(getattr(invoice, "dd_payment_id", None) or "").strip()
        if payment_id:
            try:
                from app.services.gocardless_service import BillingService

                BillingService.cancel_gocardless_payment(db, payment_id)
            except Exception:
                pass

        note = (reason or "DD collection stopped by admin")[:512]
        invoice.status = "pending"
        invoice.dd_status = "cancelled"
        invoice.dd_next_retry_at = None
        db.add(invoice)
        OrgAuditService.record_admin(
            db,
            org_id=invoice.org_id,
            event_type="invoice.dd_stopped",
            action=f"DD collection stopped — {invoice.invoice_number or invoice.id[:8]}",
            entity_type="invoice",
            entity_id=invoice.id,
            detail=note,
            metadata={"dd_payment_id": payment_id or None},
            actor_user_id=actor_user_id,
            actor_email=actor_email,
        )
        from app.services.payment_event_service import PaymentEventService

        org = db.get(Organisation, invoice.org_id)
        PaymentEventService.record_finance(
            db,
            org_id=invoice.org_id,
            client_email=(org.contact_email if org else None) or actor_email or "admin@voxbulk.com",
            event_kind="invoice.dd_stopped",
            actor_user_id=actor_user_id,
            metadata={"invoice_id": invoice.id, "dd_payment_id": payment_id or None, "reason": note},
            provider="gocardless",
            commit=False,
        )
        db.commit()
        db.refresh(invoice)
        return invoice
