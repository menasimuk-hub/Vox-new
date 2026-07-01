"""Default HTML for the sales_offer system email template (matches VOXBULK transactional theme)."""

from app.data.brand_email_layout import cta_button, wrap_brand_email

SALES_OFFER_EMAIL_SUBJECT = "Your VOXBULK offer is ready"

SALES_OFFER_EMAIL_BODY = wrap_brand_email(
    title="Your VOXBULK offer",
    inner_html="""<p>Hi <strong>{{first_name}}</strong>,</p>
  <p>Thanks for speaking with us today. Your VOXBULK <strong>{{offer_line}}</strong> is ready:</p>
  <div style="margin:16px 0;padding:16px;border:1px solid #e5e0d8;border-radius:12px;background:#f5f1ea;">
    <strong style="display:block;font-size:16px;color:#1a2d5c;">{{promo_name}}</strong>
    <span style="color:#6b6560;font-size:14px;">{{offer_summary}}</span>
  </div>
  """
    + cta_button(href="{{signup_url}}", label="Start your account")
    + """
  <p style="word-break:break-all;font-size:13px;color:#6b6560;"><a href="{{signup_url}}" style="color:#1a2d5c;">{{signup_url}}</a></p>
  <p>Your offer applies automatically when you sign up with this link.</p>""",
    footer="Sent by VOXBULK Sales · careers@voxbulk.com",
)

SALES_OFFER_WHATSAPP_BODY = """Hi {{first_name}},

Your VOXBULK {{offer_line}} is ready:
{{offer_summary}}

Tap **Start account** below to sign up — your offer applies automatically.

Tap **Stop** if you don't want further messages.

— VOXBULK Sales"""
