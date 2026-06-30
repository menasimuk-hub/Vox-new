"""Default weekly digest email template (simple {{key}} placeholders)."""

from app.data.brand_email_layout import cta_button, wrap_brand_email

WEEKLY_DIGEST_SUBJECT = "Your VOXBULK weekly digest — {{digest_week_date}}"

WEEKLY_DIGEST_BODY = wrap_brand_email(
    title="Weekly digest",
    badge="Weekly digest",
    inner_html="""<p style="margin:0 0 8px;font-size:13px;color:#6b6560;">{{digest_greeting}}</p>
  <h2 style="margin:0 0 16px;font-size:20px;color:#1a2d5c;">{{organisation_name}}</h2>
  <p style="margin:0 0 20px;font-size:14px;color:#3d3832;">Week of <strong>{{digest_week_date}}</strong></p>
  {{message_html}}
  <div style="margin:20px 0;padding:16px;background:#f5f1ea;border-radius:12px;border:1px solid #e5e0d8;">
    <p style="margin:0 0 10px;font-size:13px;font-weight:600;color:#1a2d5c;">Account summary</p>
    {{usage_summary_html}}
  </div>
  <div style="margin:20px 0;padding:16px;background:#f5f1ea;border-radius:12px;border:1px solid #e5e0d8;">
    <p style="margin:0 0 10px;font-size:13px;font-weight:600;color:#1a2d5c;">Billing & support</p>
    {{system_alerts}}
  </div>
  """
    + cta_button(href="{{dashboard_link}}", label="Open dashboard")
    + """
  <p style="font-size:12px;color:#6b6560;margin-top:20px;">
    <a href="{{privacy_link}}" style="color:#6b6560;">Privacy</a> ·
    <a href="{{frequency_link}}" style="color:#6b6560;">Email preferences</a>
  </p>""",
    footer="Sent by VOXBULK · careers@voxbulk.com",
)
