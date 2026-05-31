"""Default content for system email templates (upserted when missing)."""

from app.data.interview_email_layout import cta_button, wrap_interview_email
from app.data.invoice_document_default import INVOICE_DOCUMENT_BODY, INVOICE_DOCUMENT_SUBJECT, NEW_INVOICE_EMAIL_BODY
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
        "title": "New invoice notification",
        "subject": "Your VOXBULK invoice {{invoice_number}}",
        "body": NEW_INVOICE_EMAIL_BODY,
    },
    "invoice_document": {
        "title": "Invoice document (PDF)",
        "subject": INVOICE_DOCUMENT_SUBJECT,
        "body": INVOICE_DOCUMENT_BODY,
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
    "interview_scheduling_invite": {
        "title": "Interview scheduling invite",
        "subject": "Next step — {{role}}",
        "body": wrap_interview_email(
            title="Interview scheduling",
            inner_html="""<p>Hi <strong>{{candidate_name}}</strong>,</p>
  <p>Thank you for completing your screening call for <strong>{{role}}</strong>.</p>
  <p>Please book your next interview with our team using the link below.</p>
  """ + cta_button(href="{{scheduling_url}}", label="Book interview") + """
  <p style="word-break:break-all;font-size:13px;color:#6b6560;"><a href="{{scheduling_url}}" style="color:#1a2d5c;">{{scheduling_url}}</a></p>""",
        ),
    },
    "interview_booking_invite": {
        "title": "Interview booking invite",
        "subject": "Your interview — {{role}} at {{company_name}}",
        "body": wrap_interview_email(
            title="Book your interview",
            inner_html="""<p>Hi <strong>{{candidate_name}}</strong>,</p>
  <p>You have been shortlisted for the <strong>{{role}}</strong> position at <strong>{{company_name}}</strong>.</p>
  <p>Please choose a time for your AI phone interview within our calling window.</p>
  """ + cta_button(href="{{booking_url}}", label="Book my interview slot") + """
  <p style="font-size:13px;color:#6b6560;">If the button does not work, copy this link:<br />
  <a href="{{booking_url}}" style="color:#1a2d5c;word-break:break-all;">{{booking_url}}</a></p>
  <p style="font-size:13px;color:#6b6560;">This message was sent from careers@voxbulk.com — please check your Spam or Junk folder if you cannot find it.</p>""",
        ),
    },
    "interview_booking_confirm": {
        "title": "Interview booking confirmation",
        "subject": "Interview confirmed — {{role}} on {{interview_date}}",
        "body": wrap_interview_email(
            title="Interview confirmed",
            inner_html="""<p>Hi <strong>{{candidate_name}}</strong>,</p>
  <p>Your <strong>{{role}}</strong> interview is confirmed.</p>
  <div style="margin:20px 0;padding:16px;background:#f5f1ea;border-radius:10px;border:1px solid #e5e0d8;">
    <p style="margin:0 0 6px;"><strong>Date:</strong> {{interview_date}}</p>
    <p style="margin:0;"><strong>Time:</strong> {{interview_time}}</p>
  </div>
  <p style="font-size:13px;color:#6b6560;">We will call you at the booked time. Reply to this email if you need to reschedule.</p>""",
        ),
    },
    "interview_booking_cancel": {
        "title": "Interview booking cancellation",
        "subject": "Interview cancelled — {{role}} at {{company_name}}",
        "body": wrap_interview_email(
            title="Interview cancelled",
            inner_html="""<p>Hi <strong>{{candidate_name}}</strong>,</p>
  <p>Your <strong>{{role}}</strong> interview at <strong>{{company_name}}</strong> has been cancelled.</p>
  <div style="margin:20px 0;padding:16px;background:#f5f1ea;border-radius:10px;border:1px solid #e5e0d8;">
    <p style="margin:0 0 6px;"><strong>Was scheduled for:</strong> {{interview_date}}</p>
    <p style="margin:0;"><strong>Time:</strong> {{interview_time}}</p>
  </div>
  """ + cta_button(href="{{booking_url}}", label="Book a new time") + """
  <p style="font-size:13px;color:#6b6560;">If you still want to take part, choose another slot using the link above.</p>""",
        ),
    },
    "interview_zoom_invite": {
        "title": "Interview Zoom invite",
        "subject": "Your Zoom interview — {{role}}",
        "body": """<!DOCTYPE html><html><body style="font-family:system-ui,sans-serif;max-width:560px;margin:24px auto;color:#0f172a;line-height:1.6;">
  <p>Hi <strong>{{candidate_name}}</strong>,</p>
  <p>Your Zoom interview for <strong>{{role}}</strong> is ready.</p>
  <p><a href="{{join_url}}" style="display:inline-block;background:#00C896;color:#ffffff;padding:12px 20px;border-radius:8px;text-decoration:none;font-weight:600;">Join Zoom meeting</a></p>
  <p style="word-break:break-all;font-size:13px;"><a href="{{join_url}}" style="color:#00C896;">{{join_url}}</a></p>
  <p style="font-size:12px;color:#64748b;">— VOXBULK</p>
</body></html>""",
    },
}
