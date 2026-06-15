"""Default team invite email template."""

from app.data.brand_email_layout import cta_button, wrap_brand_email

TEAM_INVITE_EMAIL_SUBJECT = "Join {{organisation_name}} on VOXBULK"

TEAM_INVITE_EMAIL_BODY = wrap_brand_email(
    title="Team invitation",
    inner_html="""<p>Hi <strong>{{first_name}}</strong>,</p>
  <p>You have been invited to join <strong>{{organisation_name}}</strong> on VOXBULK as <strong>{{invite_role}}</strong>.</p>
  <p>Click below to create your password and open the dashboard.</p>
  """
    + cta_button(href="{{signup_url}}", label="Accept invitation")
    + """
  <p style="word-break:break-all;font-size:13px;color:#6b6560;"><a href="{{signup_url}}" style="color:#1a2d5c;">{{signup_url}}</a></p>
  <p style="font-size:13px;color:#6b6560;">This invite expires in 21 days. If you did not expect this email, you can ignore it.</p>""",
    footer='Sent by VOXBULK · careers@voxbulk.com · <a href="https://voxbulk.com/privacy" style="color:#6b6560;">Privacy</a>',
)
