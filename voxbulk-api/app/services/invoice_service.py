from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.data.invoice_document_default import INVOICE_DOCUMENT_BODY
from app.data.system_email_defaults import SYSTEM_EMAIL_DEFAULTS
from app.models.billing_invoice import BillingInvoice
from app.models.organisation import Organisation
from app.services.country_vat_service import CountryVatService
from app.services.email_template_service import EmailTemplateService
from app.services.transactional_email_service import substitute_placeholders

logger = logging.getLogger(__name__)


def _money(pence: int, currency: str = "GBP") -> str:
    amount = max(0, int(pence or 0)) / 100.0
    code = (currency or "GBP").upper()
    if code == "GBP":
        return f"£{amount:,.2f}"
    return f"{code} {amount:,.2f}"


def _format_address(org: Organisation | None) -> str:
    if org is None:
        return ""
    parts = [
        org.address_line1,
        org.address_line2,
        ", ".join(p for p in [org.city, org.county_state] if p),
        org.postcode,
        org.country,
    ]
    return "\n".join(p.strip() for p in parts if p and str(p).strip())


def _line_items_html(items: list[dict[str, Any]], currency: str) -> str:
    if not items:
        return (
            '<tr><td colspan="4" style="padding:12px;border-bottom:1px solid #e2e8f0;color:#64748b;">'
            "No line items</td></tr>"
        )
    rows: list[str] = []
    for item in items:
        desc = str(item.get("description") or "Item")
        qty = int(item.get("quantity") or 1)
        unit_pence = int(item.get("unit_pence") or item.get("total_pence") or 0)
        total_pence = int(item.get("total_pence") or unit_pence * qty)
        rows.append(
            "<tr>"
            f'<td style="padding:10px 12px;border-bottom:1px solid #e2e8f0;">{desc}</td>'
            f'<td style="padding:10px 8px;border-bottom:1px solid #e2e8f0;text-align:center;">{qty}</td>'
            f'<td style="padding:10px 12px;border-bottom:1px solid #e2e8f0;text-align:right;">{_money(unit_pence, currency)}</td>'
            f'<td style="padding:10px 12px;border-bottom:1px solid #e2e8f0;text-align:right;font-weight:600;">{_money(total_pence, currency)}</td>'
            "</tr>"
        )
    return "".join(rows)


class InvoiceDocumentService:
    @staticmethod
    def _company_defaults() -> dict[str, str]:
        settings = get_settings()
        address = str(settings.invoice_company_address or "").replace("\\n", "\n")
        return {
            "company_name": settings.invoice_company_name,
            "company_address": address,
            "company_email": settings.invoice_company_email,
            "company_vat": settings.invoice_company_vat or "—",
        }

    @staticmethod
    def build_variables(
        db: Session,
        *,
        invoice: BillingInvoice,
        org: Organisation | None = None,
    ) -> dict[str, str]:
        org = org or db.get(Organisation, invoice.org_id)
        currency = (invoice.currency or "GBP").upper()
        subtotal = int(invoice.subtotal_pence if invoice.subtotal_pence is not None else invoice.amount_gbp_pence or 0)
        tax = int(invoice.tax_pence or 0)
        total = int(invoice.amount_gbp_pence or subtotal + tax)
        rate = float(invoice.tax_rate_percent or 0)
        country_code = (invoice.country_code or CountryVatService.resolve_org_country_code(db, org)).upper()
        _, country_name = CountryVatService.get_rate(db, country_code)

        line_items: list[dict[str, Any]] = []
        if invoice.line_items_json:
            try:
                parsed = json.loads(invoice.line_items_json)
                if isinstance(parsed, list):
                    line_items = parsed
            except json.JSONDecodeError:
                pass
        if not line_items and invoice.description:
            line_items = [
                {
                    "description": invoice.description,
                    "quantity": 1,
                    "unit_pence": subtotal,
                    "total_pence": subtotal,
                }
            ]

        created = invoice.created_at or datetime.utcnow()
        due = created + timedelta(days=7)
        settings = get_settings()
        dashboard_origin = str(getattr(settings, "dashboard_app_origin", None) or "http://localhost:5175").rstrip("/")
        first_name = (org.contact_name or "").strip().split()[0] if org and org.contact_name else "there"

        vars_: dict[str, str] = {
            "invoice_number": invoice.invoice_number or invoice.external_invoice_id,
            "invoice_id": invoice.invoice_number or invoice.external_invoice_id,
            "invoice_date": created.strftime("%d %b %Y"),
            "due_date": due.strftime("%d %b %Y"),
            "invoice_status": (invoice.status or "issued").replace("_", " ").title(),
            "organisation_name": (org.name if org else "Customer") or "Customer",
            "client_email": invoice.client_email,
            "billing_address": _format_address(org),
            "country_code": country_code,
            "country_name": country_name,
            "description": invoice.description or "",
            "amount": _money(total, currency),
            "amount_gbp_pence": str(total),
            "subtotal": _money(subtotal, currency),
            "tax_amount": _money(tax, currency),
            "tax_rate": f"{rate:g}%",
            "currency": currency,
            "payment_method": (invoice.payment_method or invoice.provider or "—").replace("_", " ").title(),
            "payment_reference": invoice.payment_reference or invoice.external_invoice_id or "—",
            "line_items_html": _line_items_html(line_items, currency),
            "notes": "Thank you for your business. Please retain this invoice for your records.",
            "first_name": first_name,
            "dashboard_invoice_url": f"{dashboard_origin}/billing#invoice-{invoice.id}",
        }
        vars_.update(InvoiceDocumentService._company_defaults())
        return vars_

    @staticmethod
    def render_html(db: Session, *, invoice: BillingInvoice, org: Organisation | None = None) -> str:
        EmailTemplateService.ensure_system_templates(db)
        row = EmailTemplateService.get(db, key="invoice_document")
        defaults = SYSTEM_EMAIL_DEFAULTS.get("invoice_document", {})
        template_body = (row.body if row and row.body else None) or defaults.get("body") or INVOICE_DOCUMENT_BODY
        variables = InvoiceDocumentService.build_variables(db, invoice=invoice, org=org)
        return substitute_placeholders(template_body, variables)

    @staticmethod
    def render_pdf(db: Session, *, invoice: BillingInvoice, org: Organisation | None = None) -> bytes:
        from app.services.invoice_pdf_service import render_html_to_pdf_bytes

        html = InvoiceDocumentService.render_html(db, invoice=invoice, org=org)
        return render_html_to_pdf_bytes(html)


class InvoiceService:
    @staticmethod
    def allocate_invoice_number(db: Session) -> str:
        year = datetime.utcnow().year
        prefix = f"INV-{year}-"
        count = (
            db.execute(
                select(func.count())
                .select_from(BillingInvoice)
                .where(BillingInvoice.invoice_number.like(f"{prefix}%"))
            ).scalar_one()
            or 0
        )
        return f"{prefix}{int(count) + 1:04d}"

    @staticmethod
    def invoice_to_dict(db: Session, invoice: BillingInvoice, *, include_org_name: bool = True) -> dict[str, Any]:
        org = db.get(Organisation, invoice.org_id) if include_org_name else None
        currency = invoice.currency or "GBP"
        total = int(invoice.amount_gbp_pence or 0)
        return {
            "id": invoice.id,
            "invoice_number": invoice.invoice_number or invoice.external_invoice_id,
            "external_invoice_id": invoice.external_invoice_id,
            "org_id": invoice.org_id,
            "organisation_name": org.name if org else None,
            "provider": invoice.provider,
            "client_email": invoice.client_email,
            "description": invoice.description,
            "amount_gbp_pence": total,
            "subtotal_pence": invoice.subtotal_pence,
            "tax_pence": invoice.tax_pence,
            "tax_rate_percent": float(invoice.tax_rate_percent or 0) if invoice.tax_rate_percent is not None else None,
            "currency": currency,
            "status": invoice.status,
            "country_code": invoice.country_code,
            "payment_method": invoice.payment_method,
            "payment_reference": invoice.payment_reference,
            "emailed_at": invoice.emailed_at.isoformat() if invoice.emailed_at else None,
            "created_at": invoice.created_at.isoformat() if invoice.created_at else None,
        }

    @staticmethod
    def get_for_org(db: Session, *, invoice_id: str, org_id: str) -> BillingInvoice | None:
        return db.execute(
            select(BillingInvoice).where(BillingInvoice.id == invoice_id, BillingInvoice.org_id == org_id)
        ).scalar_one_or_none()

    @staticmethod
    def list_for_org(db: Session, *, org_id: str, limit: int = 50) -> list[BillingInvoice]:
        cap = max(1, min(int(limit or 50), 200))
        return list(
            db.execute(
                select(BillingInvoice)
                .where(BillingInvoice.org_id == org_id)
                .order_by(BillingInvoice.created_at.desc())
                .limit(cap)
            )
            .scalars()
            .all()
        )

    @staticmethod
    def list_admin(
        db: Session,
        *,
        limit: int = 100,
        status: str | None = None,
        provider: str | None = None,
        search: str | None = None,
    ) -> list[BillingInvoice]:
        cap = max(1, min(int(limit or 100), 500))
        q = select(BillingInvoice).order_by(BillingInvoice.created_at.desc()).limit(cap)
        rows = list(db.execute(q).scalars().all())
        st = (status or "").strip().lower()
        prov = (provider or "").strip().lower()
        term = (search or "").strip().lower()
        if st:
            rows = [r for r in rows if (r.status or "").lower() == st]
        if prov:
            rows = [r for r in rows if (r.provider or "").lower() == prov]
        if term:
            rows = [
                r
                for r in rows
                if term in (r.invoice_number or "").lower()
                or term in (r.external_invoice_id or "").lower()
                or term in (r.client_email or "").lower()
                or term in (r.org_id or "").lower()
            ]
        return rows

    @staticmethod
    def get_by_external(db: Session, *, provider: str, external_invoice_id: str) -> BillingInvoice | None:
        prov = (provider or "internal").strip().lower()
        ext = str(external_invoice_id or "").strip()
        if not ext:
            return None
        return db.execute(
            select(BillingInvoice).where(
                BillingInvoice.provider == prov,
                BillingInvoice.external_invoice_id == ext,
            )
        ).scalar_one_or_none()

    @staticmethod
    def issue_from_payment(
        db: Session,
        *,
        org_id: str,
        client_email: str,
        subtotal_pence: int,
        currency: str,
        description: str,
        provider: str,
        external_invoice_id: str,
        payment_reference: str | None = None,
        payment_method: str = "gocardless",
        status: str = "paid",
        line_items: list[dict[str, Any]] | None = None,
        country_code: str | None = None,
    ) -> tuple[BillingInvoice, bool, bool]:
        from app.services.billing_event_email_service import BillingEventEmailService

        existing = InvoiceService.get_by_external(db, provider=provider, external_invoice_id=external_invoice_id)
        if existing is not None:
            _, _, sent = BillingEventEmailService.issue_payment_invoice(db, invoice=existing)
            return existing, False, sent

        invoice = InvoiceService.create_from_payment(
            db,
            org_id=org_id,
            client_email=client_email,
            subtotal_pence=subtotal_pence,
            currency=currency,
            description=description,
            provider=provider,
            external_invoice_id=external_invoice_id,
            payment_reference=payment_reference,
            payment_method=payment_method,
            status=status,
            line_items=line_items,
            country_code=country_code,
        )
        _, _, sent = BillingEventEmailService.issue_payment_invoice(db, invoice=invoice)
        logger.info(
            "invoice_issue_from_payment",
            extra={
                "org_id": org_id,
                "external_invoice_id": external_invoice_id,
                "invoice_id": invoice.id,
                "created": True,
                "emailed": sent,
            },
        )
        return invoice, True, sent

    @staticmethod
    def create_from_payment(
        db: Session,
        *,
        org_id: str,
        client_email: str,
        subtotal_pence: int,
        currency: str,
        description: str,
        provider: str,
        external_invoice_id: str,
        payment_reference: str | None = None,
        payment_method: str = "gocardless",
        status: str = "paid",
        line_items: list[dict[str, Any]] | None = None,
        country_code: str | None = None,
    ) -> BillingInvoice:
        org = db.get(Organisation, org_id)
        code = (country_code or CountryVatService.resolve_org_country_code(db, org)).upper()[:2]
        rate, _ = CountryVatService.get_rate(db, code)
        subtotal = max(0, int(subtotal_pence or 0))
        tax = CountryVatService.compute_tax(subtotal, rate)
        total = subtotal + tax
        invoice_number = InvoiceService.allocate_invoice_number(db)
        row = BillingInvoice(
            org_id=str(org_id),
            provider=(provider or "internal").strip().lower(),
            external_invoice_id=str(external_invoice_id).strip(),
            invoice_number=invoice_number,
            client_email=str(client_email).strip().lower(),
            amount_gbp_pence=total,
            subtotal_pence=subtotal,
            tax_pence=tax,
            tax_rate_percent=rate,
            currency=(currency or "GBP").upper(),
            status=(status or "paid").strip().lower(),
            description=(description or "").strip() or None,
            country_code=code,
            line_items_json=json.dumps(line_items or []) if line_items else None,
            payment_reference=(payment_reference or "").strip() or None,
            payment_method=(payment_method or "gocardless").strip().lower(),
            created_at=datetime.utcnow(),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row
