"""Default HTML for the sales_offer system email template (matches VOXBULK transactional theme)."""

SALES_OFFER_EMAIL_SUBJECT = "Your VOXBULK offer is ready"

SALES_OFFER_EMAIL_BODY = """<!DOCTYPE html><html><body style="font-family:system-ui,sans-serif;max-width:560px;margin:24px auto;color:#0f172a;line-height:1.6;">
  <p>Hi <strong>{{first_name}}</strong>,</p>
  <p>Thanks for speaking with us today. Your VOXBULK <strong>{{offer_line}}</strong> is ready:</p>
  <div style="margin:16px 0;padding:16px;border:1px solid #e2e8f0;border-radius:12px;background:#f8fafc;">
    <strong style="display:block;font-size:16px;color:#0f172a;">{{promo_name}}</strong>
    <span style="color:#64748b;font-size:14px;">{{offer_summary}}</span>
  </div>
  <p><a href="{{signup_url}}" style="display:inline-block;background:#00C896;color:#ffffff;padding:12px 20px;border-radius:8px;text-decoration:none;font-weight:600;">Start your account</a></p>
  <p style="word-break:break-all;font-size:13px;"><a href="{{signup_url}}" style="color:#00C896;">{{signup_url}}</a></p>
  <p>Your offer applies automatically when you sign up with this link.</p>
  <p style="font-size:12px;color:#64748b;">— VOXBULK Sales</p>
</body></html>"""

SALES_OFFER_WHATSAPP_BODY = """Hi {{first_name}},

Great speaking with you. Here is your VOXBULK {{offer_line}}:
{{promo_name}}
{{offer_summary}}

Start here: {{signup_url}}

Open the link to create your account — your offer applies automatically.

— VOXBULK Sales"""
