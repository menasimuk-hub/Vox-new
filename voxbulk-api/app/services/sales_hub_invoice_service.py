"""Admin Sales Hub invoices — create, status workflow, payment collect hooks."""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.sales_hub_invoice import SalesHubInvoice, SalesHubInvoiceItem
from app.models.sales_rep import SalesRep
from app.services.billing_currency import money_display, normalize_currency
from app.services.sales_hub_benefits import currency_of_rep, parse_partner_terms
from app.services.sales_rep_service import SalesRepError, SalesRepService

logger = logging.getLogger(__name__)

STATUS_NEW = "new"
STATUS_SENT = "sent"
STATUS_PAID = "paid"
STATUS_REJECTED = "rejected"
VALID_STATUSES = frozenset({STATUS_NEW, STATUS_SENT, STATUS_PAID, STATUS_REJECTED})
KIND_COMMISSION = "commission"
KIND_CHARGE = "charge"
VALID_KINDS = frozenset({KIND_COMMISSION, KIND_CHARGE})


class SalesHubInvoiceService:
    @staticmethod
    def _next_number(db: Session) -> str:
        for _ in range(12):
            num = f"SH-{datetime.utcnow().strftime('%Y%m')}-{secrets.token_hex(3).upper()}"
            if db.execute(select(SalesHubInvoice).where(SalesHubInvoice.number == num)).scalar_one_or_none() is None:
                return num
        return f"SH-{secrets.token_hex(6).upper()}"

    @staticmethod
    def invoice_subtotal_minor(items: list[SalesHubInvoiceItem] | list[dict]) -> int:
        total = 0
        for it in items:
            if isinstance(it, dict):
                qty = max(1, int(it.get("quantity") or 1))
                unit = int(it.get("unit_price_minor") or 0)
            else:
                qty = max(1, int(it.quantity or 1))
                unit = int(it.unit_price_minor or 0)
            total += qty * unit
        return total

    @staticmethod
    def invoice_total_minor(inv: SalesHubInvoice, items: list[SalesHubInvoiceItem] | None = None) -> int:
        if items is None:
            items = []
        sub = SalesHubInvoiceService.invoice_subtotal_minor(items)
        disc = float(inv.discount_percent or 0)
        tax = float(inv.tax_percent or 0)
        after_disc = sub - int(round(sub * disc / 100.0))
        return max(0, after_disc + int(round(after_disc * tax / 100.0)))

    @staticmethod
    def invoice_to_dict(inv: SalesHubInvoice, items: list[SalesHubInvoiceItem] | None = None) -> dict[str, Any]:
        if items is None:
            items = []
        total = SalesHubInvoiceService.invoice_total_minor(inv, items)
        return {
            "id": inv.id,
            "sales_rep_id": inv.sales_rep_id,
            "number": inv.number,
            "kind": inv.kind,
            "customer": inv.customer,
            "customer_email": getattr(inv, "customer_email", None),
            "customer_tax_number": inv.customer_tax_number,
            "currency": inv.currency,
            "discount_percent": float(inv.discount_percent or 0),
            "tax_percent": float(inv.tax_percent or 0),
            "issued_at": inv.issued_at.isoformat() if inv.issued_at else None,
            "due_at": inv.due_at.isoformat() if inv.due_at else None,
            "status": inv.status,
            "commission_amount_minor": int(inv.commission_amount_minor or 0),
            "commission_amount_display": money_display(int(inv.commission_amount_minor or 0), inv.currency),
            "commission_approved": bool(inv.commission_approved),
            "reminders_sent": int(inv.reminders_sent or 0),
            "payment_provider": inv.payment_provider,
            "payment_provider_ref": inv.payment_provider_ref,
            "payment_link": inv.payment_link,
            "notes": inv.notes,
            "reject_reason": inv.reject_reason,
            "subtotal_minor": SalesHubInvoiceService.invoice_subtotal_minor(items),
            "total_minor": total,
            "total_display": money_display(total, inv.currency),
            "items": [
                {
                    "id": it.id,
                    "service_id": it.service_id,
                    "description": it.description,
                    "quantity": int(it.quantity or 1),
                    "unit_price_minor": int(it.unit_price_minor or 0),
                    "unit_price_display": money_display(int(it.unit_price_minor or 0), inv.currency),
                }
                for it in items
            ],
            "created_at": inv.created_at.isoformat() if inv.created_at else None,
            "updated_at": inv.updated_at.isoformat() if inv.updated_at else None,
        }

    @staticmethod
    def list_items(db: Session, invoice_id: str) -> list[SalesHubInvoiceItem]:
        return (
            db.execute(
                select(SalesHubInvoiceItem)
                .where(SalesHubInvoiceItem.invoice_id == invoice_id)
                .order_by(SalesHubInvoiceItem.created_at.asc())
            )
            .scalars()
            .all()
        )

    @staticmethod
    def get(db: Session, invoice_id: str) -> SalesHubInvoice | None:
        return db.get(SalesHubInvoice, str(invoice_id))

    @staticmethod
    def list_invoices(
        db: Session,
        *,
        rep_id: str | None = None,
        status: str | None = None,
        kind: str | None = None,
    ) -> list[dict[str, Any]]:
        q = select(SalesHubInvoice).order_by(SalesHubInvoice.created_at.desc())
        if rep_id:
            q = q.where(SalesHubInvoice.sales_rep_id == str(rep_id))
        if status:
            q = q.where(SalesHubInvoice.status == str(status).strip().lower())
        if kind:
            q = q.where(SalesHubInvoice.kind == str(kind).strip().lower())
        rows = db.execute(q).scalars().all()
        out = []
        for inv in rows:
            items = SalesHubInvoiceService.list_items(db, inv.id)
            d = SalesHubInvoiceService.invoice_to_dict(inv, items)
            rep = db.get(SalesRep, inv.sales_rep_id)
            d["rep_name"] = rep.name if rep else None
            out.append(d)
        return out

    @staticmethod
    def kpi_totals(db: Session) -> dict[str, Any]:
        rows = db.execute(select(SalesHubInvoice)).scalars().all()
        totals = {s: 0 for s in VALID_STATUSES}
        for inv in rows:
            items = SalesHubInvoiceService.list_items(db, inv.id)
            totals[str(inv.status)] = totals.get(str(inv.status), 0) + SalesHubInvoiceService.invoice_total_minor(
                inv, items
            )
        return totals

    @staticmethod
    def _rep_contact_email(db: Session, rep: SalesRep) -> str | None:
        from app.models.user import User

        email = (getattr(rep, "email", None) or "").strip().lower()
        if email and "@" in email:
            return email
        user = db.get(User, rep.user_id) if getattr(rep, "user_id", None) else None
        if user and (user.email or "").strip():
            return str(user.email).strip().lower()
        return None

    @staticmethod
    def _ensure_recipient_email(db: Session, inv: SalesHubInvoice) -> str:
        """Resolve To address: invoice.customer_email, else sales rep login email (backfill)."""
        to_email = (getattr(inv, "customer_email", None) or "").strip().lower()
        if to_email and "@" in to_email:
            return to_email
        rep = db.get(SalesRep, inv.sales_rep_id) if inv.sales_rep_id else None
        if rep is None:
            raise SalesRepError("Customer email is required to send this invoice. Set customer_email first.")
        fallback = SalesHubInvoiceService._rep_contact_email(db, rep)
        if not fallback:
            raise SalesRepError("Customer email is required to send this invoice. Set customer_email first.")
        inv.customer_email = fallback
        if not (inv.customer or "").strip():
            inv.customer = (rep.company_name or rep.name or "").strip() or inv.customer
        inv.updated_at = datetime.utcnow()
        db.add(inv)
        db.commit()
        db.refresh(inv)
        return fallback

    @staticmethod
    def create(db: Session, *, rep: SalesRep, payload: dict[str, Any]) -> SalesHubInvoice:
        kind = str(payload.get("kind") or KIND_COMMISSION).strip().lower()
        if kind not in VALID_KINDS:
            raise SalesRepError("kind must be commission or charge")
        currency = normalize_currency(payload.get("currency") or currency_of_rep(rep))
        now = datetime.utcnow()
        discount = float(payload.get("discount_percent") or 0)
        if kind == KIND_CHARGE:
            terms = parse_partner_terms(rep)
            if not discount and terms.get("discount_percent"):
                discount = float(terms["discount_percent"])
        customer_email = (str(payload.get("customer_email") or "").strip().lower() or None)
        if not customer_email:
            customer_email = SalesHubInvoiceService._rep_contact_email(db, rep)
        customer = str(payload.get("customer") or "").strip() or (rep.company_name or rep.name or "").strip()
        inv = SalesHubInvoice(
            sales_rep_id=rep.id,
            number=SalesHubInvoiceService._next_number(db),
            kind=kind,
            customer=customer,
            customer_email=customer_email,
            customer_tax_number=(str(payload.get("customer_tax_number") or "").strip() or None),
            currency=currency,
            discount_percent=discount,
            tax_percent=float(payload.get("tax_percent") or 0),
            issued_at=now,
            due_at=now + timedelta(days=int(payload.get("due_days") or 14)),
            status=STATUS_NEW,
            commission_amount_minor=max(0, int(payload.get("commission_amount_minor") or 0)),
            commission_approved=False,
            reminders_sent=0,
            notes=(str(payload.get("notes") or "").strip() or None),
            created_at=now,
            updated_at=now,
        )
        db.add(inv)
        db.flush()
        raw_items = payload.get("items") if isinstance(payload.get("items"), list) else []
        if not raw_items:
            raise SalesRepError("At least one line item is required")
        for raw in raw_items:
            if not isinstance(raw, dict):
                continue
            db.add(
                SalesHubInvoiceItem(
                    invoice_id=inv.id,
                    service_id=(str(raw.get("service_id") or "").strip() or None),
                    description=str(raw.get("description") or "").strip() or "Line item",
                    quantity=max(1, int(raw.get("quantity") or 1)),
                    unit_price_minor=max(0, int(raw.get("unit_price_minor") or 0)),
                    created_at=now,
                )
            )
        db.commit()
        db.refresh(inv)
        return inv

    @staticmethod
    def update(db: Session, *, inv: SalesHubInvoice, payload: dict[str, Any]) -> SalesHubInvoice:
        if inv.status == STATUS_PAID:
            raise SalesRepError("Paid invoices cannot be edited")
        if "customer" in payload:
            inv.customer = str(payload.get("customer") or "").strip()
        if "customer_email" in payload:
            inv.customer_email = (str(payload.get("customer_email") or "").strip().lower() or None)
        if "customer_tax_number" in payload:
            inv.customer_tax_number = (str(payload.get("customer_tax_number") or "").strip() or None)
        if "discount_percent" in payload:
            inv.discount_percent = float(payload.get("discount_percent") or 0)
        if "tax_percent" in payload:
            inv.tax_percent = float(payload.get("tax_percent") or 0)
        if "commission_amount_minor" in payload:
            inv.commission_amount_minor = max(0, int(payload.get("commission_amount_minor") or 0))
        if "notes" in payload:
            inv.notes = (str(payload.get("notes") or "").strip() or None)
        if "items" in payload and isinstance(payload.get("items"), list):
            for old in SalesHubInvoiceService.list_items(db, inv.id):
                db.delete(old)
            now = datetime.utcnow()
            for raw in payload["items"]:
                if not isinstance(raw, dict):
                    continue
                db.add(
                    SalesHubInvoiceItem(
                        invoice_id=inv.id,
                        service_id=(str(raw.get("service_id") or "").strip() or None),
                        description=str(raw.get("description") or "").strip() or "Line item",
                        quantity=max(1, int(raw.get("quantity") or 1)),
                        unit_price_minor=max(0, int(raw.get("unit_price_minor") or 0)),
                        created_at=now,
                    )
                )
        inv.updated_at = datetime.utcnow()
        db.add(inv)
        db.commit()
        db.refresh(inv)
        return inv

    @staticmethod
    def set_status(db: Session, *, inv: SalesHubInvoice, status: str, reason: str | None = None) -> SalesHubInvoice:
        status = str(status or "").strip().lower()
        if status not in VALID_STATUSES:
            raise SalesRepError("Invalid invoice status")
        inv.status = status
        if status == STATUS_REJECTED:
            inv.reject_reason = (str(reason or "").strip() or None)
        if status == STATUS_SENT and inv.issued_at is None:
            inv.issued_at = datetime.utcnow()
        inv.updated_at = datetime.utcnow()
        db.add(inv)
        db.commit()
        db.refresh(inv)
        return inv

    @staticmethod
    def remind(db: Session, *, inv: SalesHubInvoice) -> SalesHubInvoice:
        if inv.status not in {STATUS_SENT, STATUS_NEW}:
            raise SalesRepError("Reminders only apply to open invoices")
        inv.reminders_sent = int(inv.reminders_sent or 0) + 1
        if inv.status == STATUS_NEW:
            inv.status = STATUS_SENT
        inv.updated_at = datetime.utcnow()
        db.add(inv)
        db.commit()
        db.refresh(inv)
        return inv

    @staticmethod
    def approve_commission(db: Session, *, inv: SalesHubInvoice, approved: bool = True) -> SalesHubInvoice:
        if inv.kind != KIND_COMMISSION:
            raise SalesRepError("Only commission invoices have commission approval")
        inv.commission_approved = bool(approved)
        inv.updated_at = datetime.utcnow()
        db.add(inv)
        db.commit()
        db.refresh(inv)
        return inv

    @staticmethod
    def start_collect(
        db: Session,
        *,
        inv: SalesHubInvoice,
        provider: str | None = None,
        org=None,
    ) -> dict[str, Any]:
        """Attach a payment collect path for charge invoices.

        Near-term: Stripe (card) or GoCardless (DD). Airwallex remains wired for Admin enable.
        Actual PaymentIntent / redirect creation reuses platform services when available;
        otherwise stores provider choice and returns a manual-collect marker.
        """
        if inv.kind != KIND_CHARGE:
            raise SalesRepError("Payment links apply to charge invoices only")
        if inv.status == STATUS_PAID:
            raise SalesRepError("Invoice already paid")

        from app.services.payment_provider_router import PaymentProviderRouter

        chosen = str(provider or "").strip().lower() or None
        if chosen not in {None, "stripe", "gocardless", "airwallex", "manual"}:
            raise SalesRepError("provider must be stripe, gocardless, airwallex, or manual")

        if chosen is None and org is not None:
            # Card vs DD: prefer GoCardless when primary sub provider is GC; else Stripe for card.
            primary = PaymentProviderRouter.primary_subscription_provider(db, org)
            if primary == "gocardless":
                chosen = "gocardless"
            elif primary == "airwallex":
                chosen = "airwallex"
            else:
                chosen = "stripe"
        if chosen is None:
            chosen = "stripe"

        items = SalesHubInvoiceService.list_items(db, inv.id)
        total = SalesHubInvoiceService.invoice_total_minor(inv, items)
        link = None
        ref = None
        try:
            if chosen == "stripe":
                from app.services.stripe_payment_service import StripePaymentService

                if StripePaymentService.is_available(db):
                    # Placeholder collect marker — full Checkout Session can be added when partner billing org exists.
                    ref = f"sh_stripe_{inv.id}"
                    link = f"/billing/pay/sales-hub/{inv.id}?provider=stripe"
            elif chosen == "gocardless":
                from app.services.gocardless_service import BillingService

                opts = BillingService.payment_options(db)
                if opts.get("gocardless_available"):
                    ref = f"sh_gc_{inv.id}"
                    link = f"/billing/pay/sales-hub/{inv.id}?provider=gocardless"
            elif chosen == "airwallex":
                from app.services.airwallex_payment_service import AirwallexPaymentService

                if AirwallexPaymentService.is_available(db):
                    ref = f"sh_awx_{inv.id}"
                    link = f"/billing/pay/sales-hub/{inv.id}?provider=airwallex"
            else:
                chosen = "manual"
        except Exception:
            logger.exception("Sales hub collect provider %s failed for %s", chosen, inv.id)
            chosen = "manual"

        inv.payment_provider = chosen
        inv.payment_provider_ref = ref
        inv.payment_link = link
        if inv.status == STATUS_NEW:
            inv.status = STATUS_SENT
        inv.updated_at = datetime.utcnow()
        db.add(inv)
        db.commit()
        db.refresh(inv)
        return {
            "ok": True,
            "provider": chosen,
            "payment_link": link,
            "payment_provider_ref": ref,
            "amount_minor": total,
            "currency": inv.currency,
            "invoice": SalesHubInvoiceService.invoice_to_dict(inv, items),
        }

    @staticmethod
    def render_html(db: Session, inv: SalesHubInvoice, items: list[SalesHubInvoiceItem] | None = None) -> str:
        """Printable invoice HTML — same Admin `invoice_document` theme as billing invoices."""
        from app.data.invoice_document_default import INVOICE_DOCUMENT_BODY
        from app.services.email_template_service import EmailTemplateService
        from app.services.invoice_service import (
            InvoiceDocumentService,
            _invoice_template_body,
            _line_items_html,
            _money,
        )
        from app.services.transactional_email_service import substitute_placeholders

        if items is None:
            items = SalesHubInvoiceService.list_items(db, inv.id)
        total = SalesHubInvoiceService.invoice_total_minor(inv, items)
        sub = SalesHubInvoiceService.invoice_subtotal_minor(items)
        disc = float(inv.discount_percent or 0)
        tax = float(inv.tax_percent or 0)
        disc_minor = int(round(sub * disc / 100.0))
        after = sub - disc_minor
        tax_minor = int(round(after * tax / 100.0))
        currency = (inv.currency or "GBP").upper()

        line_dicts = []
        for it in items:
            qty = max(1, int(it.quantity or 1))
            unit = max(0, int(it.unit_price_minor or 0))
            line_dicts.append(
                {
                    "description": (it.description or "Sales commission").strip() or "Sales commission",
                    "quantity": qty,
                    "unit_pence": unit,
                    "total_pence": unit * qty,
                }
            )
        if not line_dicts:
            line_dicts = [
                {
                    "description": "Sales commission",
                    "quantity": 1,
                    "unit_pence": total,
                    "total_pence": total,
                }
            ]

        company = InvoiceDocumentService._company_defaults(db)
        issued = inv.issued_at or inv.created_at
        due = inv.due_at
        notes_bits = []
        if disc:
            notes_bits.append(f"Discount {disc:g}% (−{_money(disc_minor, currency)})")
        if inv.notes:
            notes_bits.append(str(inv.notes))
        if inv.kind:
            notes_bits.append(f"Kind: {inv.kind}")

        variables = {
            **company,
            "invoice_number": inv.number or "",
            "invoice_date": issued.strftime("%d %b %Y") if issued else "—",
            "due_date": due.strftime("%d %b %Y") if due else "—",
            "invoice_status": str(inv.status or "new").replace("_", " ").title(),
            "organisation_name": (inv.customer or "").strip() or "—",
            "billing_address": "",
            "client_email": (inv.customer_email or "").strip() or "—",
            "country_name": "—",
            "country_code": "—",
            "payment_method": "Bank transfer / as agreed",
            "payment_reference": inv.number or "—",
            "currency": currency,
            "line_items_html": _line_items_html(line_dicts, currency, vat_inclusive=False),
            "notes": "\n".join(notes_bits) if notes_bits else "—",
            "subtotal_label": "Subtotal (ex VAT)",
            "subtotal": _money(after, currency),
            "tax_rate": f"{tax:g}%",
            "tax_amount": _money(tax_minor, currency),
            "total_label": "Total due",
            "amount": _money(total, currency),
        }

        try:
            _, template_body, _enabled = EmailTemplateService.get_send_content(db, key="invoice_document")
            template_body = _invoice_template_body(template_body)
        except Exception:
            template_body = INVOICE_DOCUMENT_BODY
        html = substitute_placeholders(template_body, variables)
        if "{{invoice_number}}" in html or "{{company_logo_html}}" in html:
            html = substitute_placeholders(INVOICE_DOCUMENT_BODY, variables)
        return html

    @staticmethod
    def render_pdf_bytes(db: Session, inv: SalesHubInvoice) -> bytes:
        from app.services.invoice_pdf_service import render_html_to_pdf_bytes

        items = SalesHubInvoiceService.list_items(db, inv.id)
        html = SalesHubInvoiceService.render_html(db, inv, items)
        return render_html_to_pdf_bytes(html)

    @staticmethod
    def send_email(
        db: Session,
        *,
        inv: SalesHubInvoice,
        reminder: bool = False,
    ) -> dict[str, Any]:
        """Email PDF to customer_email using sales@ sender from Emails table."""
        from app.services.platform_sender_email_service import PlatformSenderEmailService
        from app.services.smtp_mailer_service import SmtpMailerError, SmtpMailerService
        from app.services.transactional_email_service import TransactionalEmailService, substitute_placeholders

        to_email = SalesHubInvoiceService._ensure_recipient_email(db, inv)
        outbound = PlatformSenderEmailService.resolve_outbound(db, "sales")
        if outbound is None or not outbound.get("from_email"):
            raise SalesRepError("Configure sales@ in Messaging → Emails (purpose: sales, active).")
        from_name = outbound["from_name"]
        from_email = outbound["from_email"]
        # Prefer mailbox password when set; otherwise use Messaging → SMTP login (same as billing).
        smtp_username = outbound.get("smtp_username")
        smtp_password = outbound.get("smtp_password")
        template_key = "sales_hub_invoice_reminder" if reminder else "sales_hub_invoice_sent"
        from app.services.email_template_service import EmailTemplateService

        EmailTemplateService.ensure_system_templates(db)
        subject_tpl, body_tpl, enabled = TransactionalEmailService.load_template_fields(db, template_key=template_key)
        if not enabled:
            raise SalesRepError(f"Email template '{template_key}' is disabled in Admin → Email templates")
        items = SalesHubInvoiceService.list_items(db, inv.id)
        total = SalesHubInvoiceService.invoice_total_minor(inv, items)
        vars_map = {
            "invoice_number": inv.number,
            "customer_name": inv.customer or "",
            "customer_email": to_email,
            "total": money_display(total, inv.currency),
            "currency": inv.currency,
            "kind": inv.kind or "",
            "due_at": inv.due_at.strftime("%Y-%m-%d") if inv.due_at else "",
        }
        subject = substitute_placeholders(subject_tpl or f"Invoice {inv.number}", vars_map)
        body = substitute_placeholders(
            body_tpl or f"<p>Please find invoice <strong>{inv.number}</strong> attached ({vars_map['total']}).</p>",
            vars_map,
        )
        pdf_bytes = SalesHubInvoiceService.render_pdf_bytes(db, inv)
        attachments = [
            {
                "filename": f"{inv.number}.pdf",
                "content": pdf_bytes,
                "maintype": "application",
                "subtype": "pdf",
            }
        ]
        try:
            SmtpMailerService.send_html(
                db,
                to_addr=to_email,
                subject=subject,
                body=body,
                from_email=from_email,
                from_name=from_name,
                attachments=attachments,
                smtp_username=smtp_username,
                smtp_password=smtp_password,
            )
        except SmtpMailerError as e:
            raise SalesRepError(
                f"SMTP send failed: {e}. "
                "Check Messaging → SMTP (enabled + password), or Edit sales@ password and click Test (connection only)."
            ) from e
        if reminder:
            SalesHubInvoiceService.remind(db, inv=inv)
        else:
            SalesHubInvoiceService.set_status(db, inv=inv, status=STATUS_SENT)
        return {"ok": True, "to": to_email, "from": from_email}
