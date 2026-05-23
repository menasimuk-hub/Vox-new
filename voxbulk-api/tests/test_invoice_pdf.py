from __future__ import annotations

from unittest.mock import patch

from app.data.invoice_document_default import INVOICE_DOCUMENT_BODY
from app.services.invoice_pdf_service import render_html_to_pdf_bytes


def _filled_invoice_html() -> str:
    html = INVOICE_DOCUMENT_BODY
    values = {
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
