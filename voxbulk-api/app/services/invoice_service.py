from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.data.invoice_document_default import INVOICE_ACCENT, INVOICE_BORDER, INVOICE_DOCUMENT_BODY, INVOICE_MUTED
from app.services.brand_assets import logo_data_uri
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


def _payment_method_label(invoice: BillingInvoice) -> str:
    method = str(invoice.payment_method or "").strip().lower()
    provider = str(invoice.provider or "").strip().lower()
    if method == "gocardless" or provider == "gocardless":
        return "GoCardless direct debit"
    if provider == "internal_overage":
        return "Account billing"
    if method:
        return method.replace("_", " ").title()
    if provider:
        return provider.replace("_", " ").title()
    return "Invoice"


def _invoice_template_body(raw: str) -> str:
    body = str(raw or "").strip()
    if not body:
        return INVOICE_DOCUMENT_BODY
    if re.search(r"\{\{#|\{\{/", body):
        logger.warning("invoice_document_template_uses_handlebars_fallback_to_default")
        return INVOICE_DOCUMENT_BODY
    if "#0f766e" in body.lower():
        logger.warning("invoice_document_template_uses_legacy_green_fallback_to_default")
        return INVOICE_DOCUMENT_BODY
    return body


def _company_logo_html() -> str:
    data = logo_data_uri(variant="logo-black")
    if data:
        return (
            f'<img src="{data}" alt="VOXBULK" '
            f'style="height:40px;width:auto;max-width:200px;display:block;margin-bottom:4px;" />'
        )
    settings = get_settings()
    return (
        f'<div style="font-size:22px;font-weight:800;color:{INVOICE_ACCENT};letter-spacing:-0.02em;">'
        f"{settings.invoice_company_name}</div>"
    )


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
            f'<tr><td colspan="4" style="padding:12px;border-bottom:1px solid {INVOICE_BORDER};color:{INVOICE_MUTED};">'
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
            f'<td style="padding:10px 12px;border-bottom:1px solid {INVOICE_BORDER};">{desc}</td>'
            f'<td style="padding:10px 8px;border-bottom:1px solid {INVOICE_BORDER};text-align:center;">{qty}</td>'
            f'<td style="padding:10px 12px;border-bottom:1px solid {INVOICE_BORDER};text-align:right;">{_money(unit_pence, currency)}</td>'
            f'<td style="padding:10px 12px;border-bottom:1px solid {INVOICE_BORDER};text-align:right;font-weight:600;">{_money(total_pence, currency)}</td>'
            "</tr>"
        )
    return "".join(rows)


class InvoiceDocumentService:
    @staticmethod
    def _company_defaults(db: Session | None = None) -> dict[str, str]:
        settings = get_settings()
        address = str(settings.invoice_company_address or "").replace("\\n", "\n")
        out = {
            "company_name": settings.invoice_company_name,
            "company_address": address,
            "company_email": settings.invoice_company_email,
            "company_vat": settings.invoice_company_vat or "—",
            "company_logo_html": _company_logo_html(),
        }
        if db is not None:
            try:
                from app.services.billing_settings_service import BillingSettingsService

                billing = BillingSettingsService.get(db)
                if str(billing.company_name or "").strip():
                    out["company_name"] = billing.company_name.strip()
                if str(billing.company_address or "").strip():
                    out["company_address"] = billing.company_address.strip()
                if str(billing.company_email or "").strip():
                    out["company_email"] = billing.company_email.strip()
                if str(billing.vat_number or "").strip():
                    out["company_vat"] = billing.vat_number.strip()
            except Exception:
                logger.exception("invoice_company_defaults_billing_settings_failed")
        return out

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
        if not line_items and invoice.amount_gbp_pence:
            total_pence = int(invoice.subtotal_pence if invoice.subtotal_pence is not None else invoice.amount_gbp_pence or 0)
            if total_pence > 0:
                desc = (invoice.description or "").strip() or "Plan usage overage"
                line_items = [
                    {
                        "description": desc,
                        "quantity": 1,
                        "unit_pence": total_pence,
                        "total_pence": total_pence,
                    }
                ]

        created = invoice.created_at or datetime.utcnow()
        due = getattr(invoice, "due_date", None) or (created + timedelta(days=7))
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
            "payment_method": _payment_method_label(invoice),
            "payment_reference": invoice.payment_reference or invoice.external_invoice_id or "—",
            "line_items_html": _line_items_html(line_items, currency),
            "notes": "Thank you for your business. Please retain this invoice for your records.",
            "first_name": first_name,
            "dashboard_invoice_url": f"{dashboard_origin}/account/billing?pay={invoice.id}",
            "pay_invoice_url": f"{dashboard_origin}/account/billing?pay={invoice.id}",
        }
        vars_.update(InvoiceDocumentService._company_defaults(db))
        return vars_

    @staticmethod
    def _append_pay_cta(html: str, *, invoice: BillingInvoice, dashboard_origin: str) -> str:
        st = str(invoice.status or "").lower()
        if st in {"paid", "void", "cancelled", "refunded", "credited"}:
            return html
        if st == "collecting" or (st == "pending" and getattr(invoice, "dd_payment_id", None)):
            return html
        pay_url = f"{dashboard_origin.rstrip('/')}/account/billing?pay={invoice.id}"
        cta = (
            f'<div style="margin-top:28px;padding:16px 20px;border:1px solid #e5e7eb;border-radius:8px;background:#f9fafb;">'
            f'<p style="margin:0 0 12px;font-size:14px;color:#374151;">This invoice is unpaid. Pay securely from your VoxBulk account.</p>'
            f'<a href="{pay_url}" style="display:inline-block;padding:10px 18px;background:#111827;color:#fff;text-decoration:none;border-radius:6px;font-weight:600;font-size:14px;">Pay invoice</a>'
            f"</div>"
        )
        if "</body>" in html.lower():
            return re.sub(r"</body>", f"{cta}</body>", html, count=1, flags=re.IGNORECASE)
        return html + cta

    @staticmethod
    def render_html(db: Session, *, invoice: BillingInvoice, org: Organisation | None = None) -> str:
        _, template_body, _enabled = EmailTemplateService.get_send_content(db, key="invoice_document")
        template_body = _invoice_template_body(template_body)
        variables = InvoiceDocumentService.build_variables(db, invoice=invoice, org=org)
        html = substitute_placeholders(template_body, variables)
        if re.search(r"\{\{[a-z_#]", html):
            logger.warning("invoice_document_unresolved_placeholders_fallback_to_default")
            html = substitute_placeholders(INVOICE_DOCUMENT_BODY, variables)
        settings = get_settings()
        dashboard_origin = str(getattr(settings, "dashboard_app_origin", None) or "http://localhost:5175")
        return InvoiceDocumentService._append_pay_cta(html, invoice=invoice, dashboard_origin=dashboard_origin)

    @staticmethod
    def render_pdf(db: Session, *, invoice: BillingInvoice, org: Organisation | None = None) -> bytes:
        from app.services.invoice_pdf_service import render_html_to_pdf_bytes

        html = InvoiceDocumentService.render_html(db, invoice=invoice, org=org)
        return render_html_to_pdf_bytes(html)


class InvoiceService:
    @staticmethod
    def allocate_invoice_number(db: Session) -> str:
        """Sequential, gap-aware invoice number from billing settings (e.g. INV-2026-000123)."""
        from app.services.billing_settings_service import BillingSettingsService

        try:
            return BillingSettingsService.allocate_invoice_number(db)
        except Exception:
            logger.exception("invoice_number_settings_allocation_failed_fallback_to_count")
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
    def invoice_to_dict(
        db: Session,
        invoice: BillingInvoice,
        *,
        include_org_name: bool = True,
        enrich_payment: bool = False,
    ) -> dict[str, Any]:
        org = db.get(Organisation, invoice.org_id) if include_org_name else None
        currency = invoice.currency or "GBP"
        total = int(invoice.amount_gbp_pence or 0)
        base = {
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
            "kind": getattr(invoice, "kind", None),
            "order_id": getattr(invoice, "order_id", None),
            "due_date": invoice.due_date.isoformat() if getattr(invoice, "due_date", None) else None,
            "disputed": bool(getattr(invoice, "disputed", False)),
            "dispute_note": getattr(invoice, "dispute_note", None),
            "dd_status": getattr(invoice, "dd_status", None),
            "dd_retry_count": int(getattr(invoice, "dd_retry_count", 0) or 0),
            "dd_next_retry_at": (
                invoice.dd_next_retry_at.isoformat() if getattr(invoice, "dd_next_retry_at", None) else None
            ),
            "emailed_at": invoice.emailed_at.isoformat() if invoice.emailed_at else None,
            "invoice_email_status": getattr(invoice, "invoice_email_status", None) or ("sent" if invoice.emailed_at else "pending"),
            "invoice_email_last_error": getattr(invoice, "invoice_email_last_error", None),
            "invoice_email_attempts": int(getattr(invoice, "invoice_email_attempts", 0) or 0),
            "issued_at": invoice.created_at.isoformat() if invoice.created_at else None,
            "created_at": invoice.created_at.isoformat() if invoice.created_at else None,
            "total_pence": total,
            "total_gbp": _money(total, currency),
        }
        if enrich_payment:
            org = db.get(Organisation, invoice.org_id)
            if org is not None:
                from app.services.invoice_payment_service import InvoicePaymentService

                return InvoicePaymentService.enrich_invoice_dict(db, org, invoice, base)
        from app.services.invoice_lifecycle_service import InvoiceLifecycleService

        return InvoiceLifecycleService.enrich_invoice_dict(base, invoice)

    @staticmethod
    def get_for_org(db: Session, *, invoice_id: str, org_id: str) -> BillingInvoice | None:
        return db.execute(
            select(BillingInvoice).where(BillingInvoice.id == invoice_id, BillingInvoice.org_id == org_id)
        ).scalar_one_or_none()

    @staticmethod
    def resolve_for_admin(db: Session, invoice_key: str) -> BillingInvoice | None:
        """Find invoice by UUID, invoice number, or external id (admin billing routes)."""
        key = str(invoice_key or "").strip()
        if not key:
            return None
        row = db.get(BillingInvoice, key)
        if row is not None:
            return row
        return db.execute(
            select(BillingInvoice)
            .where(
                sa.or_(
                    BillingInvoice.invoice_number == key,
                    BillingInvoice.external_invoice_id == key,
                )
            )
            .order_by(BillingInvoice.created_at.desc())
            .limit(1)
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
    def get_for_order(db: Session, *, order_id: str) -> BillingInvoice | None:
        oid = str(order_id or "").strip()
        if not oid:
            return None
        return db.execute(
            select(BillingInvoice)
            .where(BillingInvoice.order_id == oid)
            .order_by(BillingInvoice.created_at.desc())
            .limit(1)
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
        kind: str | None = None,
        order_id: str | None = None,
    ) -> tuple[BillingInvoice, bool, bool]:
        from app.services.billing_event_email_service import BillingEventEmailService

        existing = InvoiceService.get_by_external(db, provider=provider, external_invoice_id=external_invoice_id)
        if existing is not None:
            return existing, False, False

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
            kind=kind,
            order_id=order_id,
        )
        _, _, sent = BillingEventEmailService.issue_payment_invoice(db, invoice=invoice)
        from app.core.logging import safe_log_extra

        logger.info(
            "invoice_issue_from_payment",
            extra=safe_log_extra(
                org_id=org_id,
                external_invoice_id=external_invoice_id,
                invoice_id=invoice.id,
                invoice_was_new=True,
                emailed=sent,
            ),
        )
        return invoice, True, sent

    @staticmethod
    def effective_vat_rate(db: Session, *, country_code: str) -> float:
        """UK VAT applies only when VAT is enabled in billing settings; non-UK markets get the
        rate configured for their country (default 0 — no GB fallback for foreign customers)."""
        from app.models.country_vat_rate import CountryVatRate

        try:
            from app.services.billing_settings_service import BillingSettingsService

            settings = BillingSettingsService.get(db)
            vat_enabled = bool(settings.vat_enabled)
        except Exception:
            vat_enabled = False
        if not vat_enabled:
            return 0.0
        code = str(country_code or "GB").upper()[:2]
        row = db.execute(select(CountryVatRate).where(CountryVatRate.country_code == code)).scalar_one_or_none()
        if row is None or not row.is_enabled:
            return 20.0 if code == "GB" else 0.0
        return float(row.vat_rate_percent or 0)

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
        kind: str | None = None,
        order_id: str | None = None,
    ) -> BillingInvoice:
        org = db.get(Organisation, org_id)
        code = (country_code or CountryVatService.resolve_org_country_code(db, org)).upper()[:2]
        rate = InvoiceService.effective_vat_rate(db, country_code=code)
        subtotal = max(0, int(subtotal_pence or 0))
        tax = CountryVatService.compute_tax(subtotal, rate)
        total = subtotal + tax
        invoice_number = InvoiceService.allocate_invoice_number(db)
        due_days = 7
        try:
            from app.services.billing_settings_service import BillingSettingsService

            due_days = int(BillingSettingsService.get(db).invoice_due_days or 7)
        except Exception:
            pass
        now = datetime.utcnow()
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
            kind=(kind or "").strip().lower() or None,
            order_id=(order_id or "").strip() or None,
            due_date=now + timedelta(days=due_days),
            created_at=now,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row
