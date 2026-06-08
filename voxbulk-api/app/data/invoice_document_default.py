"""Default HTML for printable invoice documents (PDF + dashboard view)."""

INVOICE_DOCUMENT_SUBJECT = "Invoice {{invoice_number}}"

INVOICE_DOCUMENT_BODY = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <title>Invoice {{invoice_number}}</title>
  <style>
    @page { size: A4; margin: 14mm; }
    html, body { margin: 0; padding: 0; }
    body { page-break-inside: avoid; }
    table { page-break-inside: avoid; }
  </style>
</head>
<body style="font-family:system-ui,-apple-system,Segoe UI,sans-serif;max-width:720px;margin:0 auto;padding:24px 20px;color:#0f172a;line-height:1.45;font-size:13px;">
  <table style="width:100%;border-collapse:collapse;margin-bottom:28px;">
    <tr>
      <td style="vertical-align:top;width:55%;">
        <div style="font-size:22px;font-weight:800;color:#0f766e;letter-spacing:-0.02em;">{{company_name}}</div>
        <div style="font-size:12px;color:#64748b;margin-top:8px;white-space:pre-line;">{{company_address}}</div>
        <div style="font-size:12px;color:#64748b;margin-top:6px;">{{company_email}}</div>
        <div style="font-size:12px;color:#64748b;">VAT / TRN: {{company_vat}}</div>
      </td>
      <td style="vertical-align:top;text-align:right;">
        <div style="font-size:28px;font-weight:800;color:#0f172a;">INVOICE</div>
        <div style="font-size:13px;margin-top:10px;"><strong>No.</strong> {{invoice_number}}</div>
        <div style="font-size:13px;"><strong>Date</strong> {{invoice_date}}</div>
        <div style="font-size:13px;"><strong>Due</strong> {{due_date}}</div>
        <div style="font-size:13px;"><strong>Status</strong> {{invoice_status}}</div>
      </td>
    </tr>
  </table>

  <table style="width:100%;border-collapse:collapse;margin-bottom:24px;">
    <tr>
      <td style="width:50%;vertical-align:top;padding:14px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;">
        <div style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.06em;color:#64748b;margin-bottom:8px;">Bill to</div>
        <div style="font-size:15px;font-weight:700;">{{organisation_name}}</div>
        <div style="font-size:12px;color:#475569;margin-top:6px;white-space:pre-line;">{{billing_address}}</div>
        <div style="font-size:12px;color:#475569;margin-top:6px;">{{client_email}}</div>
        <div style="font-size:12px;color:#475569;">{{country_name}} ({{country_code}})</div>
      </td>
      <td style="width:8px;"></td>
      <td style="width:50%;vertical-align:top;padding:14px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;">
        <div style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.06em;color:#64748b;margin-bottom:8px;">Payment</div>
        <div style="font-size:13px;"><strong>Method</strong> {{payment_method}}</div>
        <div style="font-size:13px;"><strong>Reference</strong> {{payment_reference}}</div>
        <div style="font-size:13px;"><strong>Currency</strong> {{currency}}</div>
      </td>
    </tr>
  </table>

  <table style="width:100%;border-collapse:collapse;margin-bottom:20px;font-size:13px;">
    <thead>
      <tr style="background:#0f766e;color:#ffffff;">
        <th style="text-align:left;padding:10px 12px;border-radius:8px 0 0 0;">Description</th>
        <th style="text-align:center;padding:10px 8px;width:56px;">Qty</th>
        <th style="text-align:right;padding:10px 12px;width:96px;">Unit</th>
        <th style="text-align:right;padding:10px 12px;border-radius:0 8px 0 0;width:96px;">Total</th>
      </tr>
    </thead>
    <tbody>
      {{line_items_html}}
    </tbody>
  </table>

  <table style="width:100%;border-collapse:collapse;margin-bottom:28px;">
    <tr>
      <td style="width:58%;vertical-align:top;padding-right:16px;">
        <div style="font-size:12px;color:#64748b;white-space:pre-line;">{{notes}}</div>
      </td>
      <td style="width:42%;vertical-align:top;">
        <table style="width:100%;border-collapse:collapse;font-size:13px;">
          <tr><td style="padding:6px 0;color:#64748b;">Subtotal</td><td style="text-align:right;font-weight:600;">{{subtotal}}</td></tr>
          <tr><td style="padding:6px 0;color:#64748b;">VAT / Tax ({{tax_rate}})</td><td style="text-align:right;font-weight:600;">{{tax_amount}}</td></tr>
          <tr style="border-top:2px solid #0f172a;">
            <td style="padding:10px 0;font-size:15px;font-weight:800;">Total due</td>
            <td style="text-align:right;font-size:15px;font-weight:800;color:#0f766e;">{{amount}}</td>
          </tr>
        </table>
      </td>
    </tr>
  </table>

  <div style="border-top:1px solid #e2e8f0;padding-top:16px;font-size:11px;color:#94a3b8;text-align:center;">
    Thank you for your business · {{company_name}} · {{company_email}}
  </div>
</body>
</html>"""

NEW_INVOICE_EMAIL_BODY = """<!DOCTYPE html><html><body style="font-family:system-ui,sans-serif;max-width:560px;margin:24px auto;color:#0f172a;line-height:1.6;">
  <p>Hi <strong>{{first_name}}</strong>,</p>
  <p>Your invoice <strong>{{invoice_number}}</strong> for <strong>{{amount}}</strong> is ready.</p>
  <p style="color:#64748b;font-size:14px;">{{description}}</p>
  <p><a href="{{dashboard_invoice_url}}" style="display:inline-block;background:#0f766e;color:#ffffff;padding:12px 20px;border-radius:8px;text-decoration:none;font-weight:600;">View invoice in dashboard</a></p>
  <p style="font-size:13px;color:#64748b;">A PDF copy is attached to this email.</p>
  <p style="font-size:12px;color:#94a3b8;">— VOXBULK Billing</p>
</body></html>"""
