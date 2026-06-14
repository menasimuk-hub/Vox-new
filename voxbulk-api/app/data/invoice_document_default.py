"""Default HTML for printable invoice documents (PDF + dashboard view)."""

from app.data.brand_email_layout import wrap_brand_email

INVOICE_ACCENT = "#D4A93A"
INVOICE_INK = "#2a2824"
INVOICE_MUTED = "#6b6560"
INVOICE_SURFACE = "#fbf8f3"
INVOICE_BORDER = "#e5e0d8"
INVOICE_BG = "#f5f1ea"

INVOICE_DOCUMENT_SUBJECT = "Invoice {{invoice_number}}"

INVOICE_DOCUMENT_BODY = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <title>Invoice {{{{invoice_number}}}}</title>
  <style>
    @page {{ size: A4; margin: 14mm; }}
    html, body {{ margin: 0; padding: 0; }}
    body {{ page-break-inside: avoid; background: {INVOICE_BG}; }}
    table {{ page-break-inside: avoid; }}
  </style>
</head>
<body style="font-family:system-ui,-apple-system,Segoe UI,sans-serif;max-width:720px;margin:0 auto;padding:24px 20px;color:{INVOICE_INK};line-height:1.45;font-size:13px;">
  <table style="width:100%;border-collapse:collapse;margin-bottom:28px;">
    <tr>
      <td style="vertical-align:top;width:55%;">
        {{{{company_logo_html}}}}
        <div style="font-size:12px;color:{INVOICE_MUTED};margin-top:4px;white-space:pre-line;">{{{{company_address}}}}</div>
        <div style="font-size:12px;color:{INVOICE_MUTED};margin-top:6px;">{{{{company_email}}}}</div>
        <div style="font-size:12px;color:{INVOICE_MUTED};">VAT / TRN: {{{{company_vat}}}}</div>
      </td>
      <td style="vertical-align:top;text-align:right;">
        <div style="font-size:28px;font-weight:800;color:{INVOICE_INK};letter-spacing:0.04em;">INVOICE</div>
        <div style="font-size:13px;margin-top:10px;"><strong>No.</strong> {{{{invoice_number}}}}</div>
        <div style="font-size:13px;"><strong>Date</strong> {{{{invoice_date}}}}</div>
        <div style="font-size:13px;"><strong>Due</strong> {{{{due_date}}}}</div>
        <div style="font-size:13px;"><strong>Status</strong> {{{{invoice_status}}}}</div>
      </td>
    </tr>
  </table>

  <table style="width:100%;border-collapse:collapse;margin-bottom:24px;">
    <tr>
      <td style="width:50%;vertical-align:top;padding:14px;background:{INVOICE_SURFACE};border:1px solid {INVOICE_BORDER};border-radius:10px;">
        <div style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.06em;color:{INVOICE_MUTED};margin-bottom:8px;">Bill to</div>
        <div style="font-size:15px;font-weight:700;">{{{{organisation_name}}}}</div>
        <div style="font-size:12px;color:{INVOICE_MUTED};margin-top:6px;white-space:pre-line;">{{{{billing_address}}}}</div>
        <div style="font-size:12px;color:{INVOICE_MUTED};margin-top:6px;">{{{{client_email}}}}</div>
        <div style="font-size:12px;color:{INVOICE_MUTED};">{{{{country_name}}}} ({{{{country_code}}}})</div>
      </td>
      <td style="width:8px;"></td>
      <td style="width:50%;vertical-align:top;padding:14px;background:{INVOICE_SURFACE};border:1px solid {INVOICE_BORDER};border-radius:10px;">
        <div style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.06em;color:{INVOICE_MUTED};margin-bottom:8px;">Payment</div>
        <div style="font-size:13px;"><strong>Method</strong> {{{{payment_method}}}}</div>
        <div style="font-size:13px;"><strong>Reference</strong> {{{{payment_reference}}}}</div>
        <div style="font-size:13px;"><strong>Currency</strong> {{{{currency}}}}</div>
      </td>
    </tr>
  </table>

  <table style="width:100%;border-collapse:collapse;margin-bottom:20px;font-size:13px;">
    <thead>
      <tr style="background:{INVOICE_ACCENT};color:#ffffff;">
        <th style="text-align:left;padding:10px 12px;border-radius:8px 0 0 0;">Description</th>
        <th style="text-align:center;padding:10px 8px;width:56px;">Qty</th>
        <th style="text-align:right;padding:10px 12px;width:96px;">Unit</th>
        <th style="text-align:right;padding:10px 12px;border-radius:0 8px 0 0;width:96px;">Total</th>
      </tr>
    </thead>
    <tbody>
      {{{{line_items_html}}}}
    </tbody>
  </table>

  <table style="width:100%;border-collapse:collapse;margin-bottom:28px;">
    <tr>
      <td style="width:58%;vertical-align:top;padding-right:16px;">
        <div style="font-size:12px;color:{INVOICE_MUTED};white-space:pre-line;">{{{{notes}}}}</div>
      </td>
      <td style="width:42%;vertical-align:top;">
        <table style="width:100%;border-collapse:collapse;font-size:13px;">
          <tr><td style="padding:6px 0;color:{INVOICE_MUTED};">{{{{subtotal_label}}}}</td><td style="text-align:right;font-weight:600;">{{{{subtotal}}}}</td></tr>
          <tr><td style="padding:6px 0;color:{INVOICE_MUTED};">VAT / Tax ({{{{tax_rate}}}})</td><td style="text-align:right;font-weight:600;">{{{{tax_amount}}}}</td></tr>
          <tr style="border-top:2px solid {INVOICE_INK};">
            <td style="padding:10px 0;font-size:15px;font-weight:800;">{{{{total_label}}}}</td>
            <td style="text-align:right;font-size:15px;font-weight:800;color:{INVOICE_ACCENT};">{{{{amount}}}}</td>
          </tr>
        </table>
      </td>
    </tr>
  </table>

  <div style="border-top:1px solid {INVOICE_BORDER};padding-top:16px;font-size:11px;color:{INVOICE_MUTED};text-align:center;">
    Thank you for your business · {{{{company_name}}}} · {{{{company_email}}}}
  </div>
</body>
</html>"""

NEW_INVOICE_EMAIL_BODY = wrap_brand_email(
    title="Your invoice",
    footer="— VOXBULK Billing",
    inner_html=f"""
  <p>Hi <strong>{{{{first_name}}}}</strong>,</p>
  <p>Your invoice <strong>{{{{invoice_number}}}}</strong> for <strong>{{{{amount}}}}</strong> is ready.</p>
  <p style="color:{INVOICE_MUTED};font-size:14px;">{{{{description}}}}</p>
  <p style="margin:24px 0;">
    <a href="{{{{dashboard_invoice_url}}}}" style="display:inline-block;background:{INVOICE_ACCENT};color:#ffffff;padding:12px 20px;border-radius:10px;text-decoration:none;font-weight:600;">View invoice in dashboard</a>
  </p>
  <p style="font-size:13px;color:{INVOICE_MUTED};">A PDF copy is attached to this email.</p>
""",
)
