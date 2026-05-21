"""Default content for system email templates (upserted when missing)."""

from app.data.sales_offer_email_default import SALES_OFFER_EMAIL_BODY, SALES_OFFER_EMAIL_SUBJECT

SYSTEM_EMAIL_DEFAULTS: dict[str, dict[str, str]] = {
    "new_user": {
        "title": "New user",
        "subject": "Welcome to VOXBULK",
        "body": """<!DOCTYPE html><html><body style="font-family:system-ui,sans-serif;max-width:560px;margin:24px auto;color:#0f172a;">
  <p>Hi <strong>{{user_email}}</strong>,</p>
  <p>Welcome to VOXBULK — your account is ready.</p>
  <p style="color:#64748b;font-size:13px;">This email uses HTML. Replace placeholders like <code>{{user_email}}</code>.</p>
</body></html>""",
    },
    "forgot_password": {
        "title": "Forgot password",
        "subject": "Reset your password",
        "body": "<p>Hello,</p><p>We received a password reset for <strong>{{user_email}}</strong>.</p><p>If this was not you, ignore this email.</p>",
    },
    "new_invoice": {
        "title": "New invoice",
        "subject": "New invoice",
        "body": "<p>Hello,</p><p>New invoice <strong>#{{invoice_id}}</strong> — amount <strong>{{amount_gbp_pence}}</strong> pence ({{currency}}), status {{invoice_status}}.</p>",
    },
    "payment_failed": {
        "title": "Cancel / failed payment",
        "subject": "Payment issue",
        "body": "<p>Payment issue for <strong>{{user_email}}</strong>.</p><p>Amount due: <strong>{{amount}}</strong> · Invoice <strong>{{invoice_number}}</strong>.</p>",
    },
    "general_notification": {
        "title": "General activity",
        "subject": "Notification",
        "body": '<p>Hello {{user_name}},</p><p>{{message}}</p><p style="font-size:12px;color:#64748b;">Sent by VOXBULK notifications.</p>',
    },
    "sales_offer": {
        "title": "Sales offer link",
        "subject": SALES_OFFER_EMAIL_SUBJECT,
        "body": SALES_OFFER_EMAIL_BODY,
    },
    "usage_warning": {
        "title": "Usage alert (80%)",
        "subject": "VOXBULK usage alert — {{usage_summary}}",
        "body": """<!DOCTYPE html><html><body style="font-family:system-ui,sans-serif;max-width:560px;margin:24px auto;color:#0f172a;line-height:1.6;">
  <p>Hi <strong>{{organisation_name}}</strong>,</p>
  <p>You have used <strong>80% or more</strong> of an included allowance on your <strong>{{plan_code}}</strong> plan.</p>
  <div style="margin:16px 0;padding:16px;border:1px solid #e2e8f0;border-radius:12px;background:#f8fafc;font-size:14px;">
    {{usage_details_html}}
  </div>
  <p style="font-size:13px;color:#64748b;">Billing period ends {{period_end}}. Overage is invoiced separately when applicable.</p>
  <p style="font-size:12px;color:#64748b;">— VOXBULK Billing</p>
</body></html>""",
    },
}
