"""Default demo_invite email (insert-missing only)."""

from app.data.brand_email_layout import cta_button, wrap_brand_email

DEMO_INVITE_EMAIL_SUBJECT = "Your VoxBulk AI demo link — valid 7 days"

DEMO_INVITE_EMAIL_BODY = wrap_brand_email(
    title="Your AI product demo",
    inner_html="""<p>Hi <strong>{{contact_name}}</strong>,</p>
  <p>Thanks for your interest in VoxBulk for <strong>{{company_name}}</strong>.</p>
  <p>Use the button below to start your live AI demo. The link is <strong>valid for 7 days</strong> and can be used <strong>once</strong>.</p>
  <p style="font-size:13px;color:#6b6560;">Allow microphone access when prompted. The call may be recorded so our sales team can follow up.</p>
  """
    + cta_button(href="{{demo_link}}", label="Start AI demo")
    + """
  <p style="word-break:break-all;font-size:13px;color:#6b6560;"><a href="{{demo_link}}" style="color:#1a2d5c;">{{demo_link}}</a></p>
  <p style="font-size:13px;color:#6b6560;">Connection failed or call dropped early? Request a fresh link (we keep your progress):</p>
  """
    + cta_button(href="{{resend_link}}", label="Resend demo link")
    + """
  <p style="word-break:break-all;font-size:13px;color:#6b6560;"><a href="{{resend_link}}" style="color:#1a2d5c;">{{resend_link}}</a></p>
  <p style="font-size:13px;color:#6b6560;">Preferred language: {{preferred_language}}. Questions? Reply to this email or contact <a href="mailto:{{support_email}}" style="color:#1a2d5c;">{{support_email}}</a>.</p>""",
    footer="Sent by VOXBULK Sales · hello@voxbulk.com",
)
