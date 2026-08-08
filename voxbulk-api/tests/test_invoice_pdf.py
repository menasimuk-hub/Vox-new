from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.data.invoice_document_default import INVOICE_DOCUMENT_BODY
from app.services.invoice_pdf_service import render_html_to_pdf_bytes
from app.services.invoice_service import InvoiceDocumentService


def _filled_invoice_html() -> str:
    html = INVOICE_DOCUMENT_BODY
    values = {
        "company_logo_html": '<img src="data:image/svg+xml;base64,TEST" alt="VOXBULK" style="height:40px;" />',
        "company_name": "VOXBULK",
        "company_address": "London",
        "company_email": "billing@voxbulk.com",
        "company_vat": "GB123",
        "invoice_number": "INV-TEST-1",
        "invoice_date": "2026-05-20",
        "due_date": "2026-05-20",
        "invoice_status": "paid",
        "organisation_name": "Test Org",
        "billing_address": "1 High Street",
        "client_email": "client@example.com",
        "country_name": "United Kingdom",
        "country_code": "GB",
        "payment_method": "GoCardless",
        "payment_reference": "PM123",
        "currency": "GBP",
        "line_items_html": "<tr><td>Starter plan</td><td>1</td><td>£10.00</td><td>£10.00</td></tr>",
        "notes": "Thank you",
        "subtotal": "£10.00",
        "tax_rate": "20%",
        "tax_amount": "£2.00",
        "amount": "£12.00",
    }
    for key, val in values.items():
        html = html.replace(f"{{{{{key}}}}}", val)
    return html


def test_render_html_to_pdf_prefers_weasyprint():
    fake_pdf = b"%PDF-1.7 weasyprint-test"

    with patch("app.services.invoice_pdf_service._render_with_weasyprint", return_value=fake_pdf):
        out = render_html_to_pdf_bytes(_filled_invoice_html())

    assert out == fake_pdf


def test_render_html_to_pdf_falls_back_to_fpdf_when_weasyprint_unavailable():
    with patch("app.services.invoice_pdf_service._render_with_weasyprint", return_value=None):
        out = render_html_to_pdf_bytes("<html><body><p>Invoice INV-1</p></body></html>")

    assert out.startswith(b"%PDF")


def test_build_variables_does_not_compare_due_date_to_int():
    """Regression: amount_due was overwritten by due_date, then compared with <= 0."""
    inv = SimpleNamespace(
        id="i1",
        org_id="o1",
        currency="GBP",
        country_code="GB",
        line_items_json="[]",
        amount_gbp_pence=0,
        subtotal_pence=0,
        tax_pence=0,
        tax_rate_percent=0,
        description="Covered",
        invoice_number="INV-0",
        external_invoice_id="x0",
        client_email="a@b.com",
        status="paid",
        payment_method="gocardless",
        payment_reference="PM1",
        provider="gocardless",
        created_at=datetime.utcnow() - timedelta(days=3),
        due_date=datetime.utcnow() + timedelta(days=4),
        dd_payment_id=None,
    )
    org = SimpleNamespace(
        name="Org",
        contact_name="Sam",
        contact_email="a@b.com",
        address_line1=None,
        address_line2=None,
        city=None,
        county_state=None,
        postcode=None,
        country=None,
        country_code="GB",
    )
    db = MagicMock()
    db.get.return_value = org
    with (
        patch("app.services.invoice_service.CountryVatService.resolve_org_country_code", return_value="GB"),
        patch("app.services.invoice_service.CountryVatService.get_rate", return_value=(0.0, "United Kingdom")),
        patch("app.services.invoice_service.CountryVatService.is_vat_inclusive_pricing", return_value=False),
        patch("app.services.invoice_service.CountryVatService.display_line_items_ex_vat", return_value=[]),
        patch("app.services.invoice_service.InvoiceLineItemService.catalog_value_pence", return_value=5000),
        patch("app.services.invoice_service.InvoiceLineItemService.amount_due_pence", return_value=0),
        patch.object(InvoiceDocumentService, "_company_defaults", return_value={}),
    ):
        vars_ = InvoiceDocumentService.build_variables(db, invoice=inv, org=org)
    assert "Campaign value" in vars_["notes"]
    assert vars_["due_date"]
