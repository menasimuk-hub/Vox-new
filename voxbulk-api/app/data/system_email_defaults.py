"""Default content for system email templates (upserted when missing)."""

from app.data.brand_email_layout import cta_button, wrap_brand_email
from app.data.interview_email_layout import wrap_interview_email
from app.data.invoice_document_default import INVOICE_DOCUMENT_BODY, INVOICE_DOCUMENT_SUBJECT, NEW_INVOICE_EMAIL_BODY
from app.data.sales_offer_email_default import SALES_OFFER_EMAIL_BODY, SALES_OFFER_EMAIL_SUBJECT
from app.data.team_invite_email_default import TEAM_INVITE_EMAIL_BODY, TEAM_INVITE_EMAIL_SUBJECT
from app.data.weekly_digest_email_default import WEEKLY_DIGEST_BODY, WEEKLY_DIGEST_SUBJECT

SYSTEM_EMAIL_DEFAULTS: dict[str, dict[str, str]] = {
    "new_user": {
        "title": "New user",
        "subject": "Welcome to VOXBULK",
        "body": wrap_brand_email(
            title="Welcome to VOXBULK",
            inner_html="""<p>Hi <strong>{{first_name}}</strong>,</p>
  <p>Welcome to VOXBULK — your account for <strong>{{organisation_name}}</strong> is ready.</p>
  <p>Sign in to open your dashboard and finish setup.</p>
  """
            + cta_button(href="{{dashboard_url}}", label="Open dashboard")
            + """
  <p style="word-break:break-all;font-size:13px;color:#6b6560;"><a href="{{dashboard_url}}" style="color:#1a2d5c;">{{dashboard_url}}</a></p>
  <p style="font-size:13px;color:#6b6560;">Sign-in page: <a href="{{signin_url}}" style="color:#1a2d5c;">{{signin_url}}</a></p>
  <p style="font-size:13px;color:#6b6560;">If you did not create this account, contact support.</p>""",
        ),
    },
    "account_deletion_completed": {
        "title": "Account deletion completed",
        "subject": "Your VOXBULK account has been deleted",
        "body": wrap_brand_email(
            title="Account deleted",
            inner_html="""<p>Hi <strong>{{first_name}}</strong>,</p>
  <p>Your VOXBULK account for <strong>{{organisation_name}}</strong> has been deleted as requested.</p>
  <p><strong>Completed:</strong> {{deleted_at}}</p>
  <p style="font-size:13px;color:#6b6560;">{{retention_note}}</p>
  <p style="font-size:13px;color:#6b6560;">If you have questions, contact us at <a href="mailto:{{support_email}}" style="color:#1a2d5c;">{{support_email}}</a>.</p>""",
            footer="Sent by VOXBULK · billing@voxbulk.com",
        ),
    },
    "forgot_password": {
        "title": "Forgot password",
        "subject": "Reset your password",
        "body": wrap_brand_email(
            title="Reset your password",
            inner_html="""<p>Hi <strong>{{user_email}}</strong>,</p>
  <p>We received a request to reset the password for your VOXBULK account.</p>
  <p>Click the button below to set a new password. This link expires in 60 minutes.</p>
  """ + cta_button(href="{{reset_link}}", label="Reset password") + """
  <p style="word-break:break-all;font-size:13px;color:#6b6560;"><a href="{{reset_link}}" style="color:#1a2d5c;">{{reset_link}}</a></p>
  <p style="font-size:13px;color:#6b6560;"><strong>Didn't request this?</strong> You can safely ignore this email. Your password won't change unless you click the link above.</p>""",
        ),
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
        "subject": "Payment issue — {{invoice_number}}",
        "body": wrap_brand_email(
            title="Payment issue",
            inner_html="""<p>Hi,</p>
  <p>We could not collect payment for invoice <strong>{{invoice_number}}</strong>.</p>
  <p>Amount due: <strong>{{amount}}</strong></p>
  <p style="font-size:13px;color:#6b6560;">Please update your payment method or pay the invoice from your billing page.</p>
  """
            + cta_button(href="{{billing_url}}", label="View billing")
            + """<p style="font-size:13px;color:#6b6560;">Account: {{user_email}}</p>""",
            footer="Sent by VOXBULK Billing · billing@voxbulk.com",
        ),
    },
    "general_notification": {
        "title": "General activity",
        "subject": "Notification from VOXBULK",
        "body": wrap_brand_email(
            title="Notification",
            inner_html="""<p>Hello <strong>{{user_name}}</strong>,</p>
  <p>{{message}}</p>""",
        ),
    },
    "team_invite": {
        "title": "Team invitation",
        "subject": TEAM_INVITE_EMAIL_SUBJECT,
        "body": TEAM_INVITE_EMAIL_BODY,
    },
    "weekly_digest": {
        "title": "Weekly digest",
        "subject": WEEKLY_DIGEST_SUBJECT,
        "body": WEEKLY_DIGEST_BODY,
    },
    "sales_offer": {
        "title": "Sales offer link",
        "subject": SALES_OFFER_EMAIL_SUBJECT,
        "body": SALES_OFFER_EMAIL_BODY,
    },
    "usage_warning": {
        "title": "Usage alert (80%)",
        "subject": "VOXBULK usage alert — {{usage_summary}}",
        "body": wrap_brand_email(
            title="Usage alert",
            badge="80% used",
            inner_html="""<p>Hi <strong>{{organisation_name}}</strong>,</p>
  <p>You have used <strong>80% or more</strong> of an included allowance on your <strong>{{plan_code}}</strong> plan.</p>
  <div style="margin:16px 0;padding:16px;border:1px solid #e5e0d8;border-radius:12px;background:#f5f1ea;font-size:14px;">
    {{usage_details_html}}
  </div>
  <p style="font-size:13px;color:#6b6560;">Billing period ends {{period_end}}. Overage is invoiced separately when applicable.</p>""",
            footer="Sent by VOXBULK Billing · billing@voxbulk.com",
        ),
    },
    "usage_warning_100": {
        "title": "Usage alert (100%)",
        "subject": "VOXBULK allowance fully used — {{usage_summary}}",
        "body": wrap_brand_email(
            title="Allowance fully used",
            badge="100% used",
            inner_html="""<p>Hi <strong>{{organisation_name}}</strong>,</p>
  <p>You have <strong>fully used</strong> an included allowance on your <strong>{{plan_code}}</strong> plan.</p>
  <div style="margin:16px 0;padding:16px;border:1px solid #fecaca;border-radius:12px;background:#fef2f2;font-size:14px;">
    {{usage_details_html}}
  </div>
  <p style="font-size:13px;color:#6b6560;">Billing period ends {{period_end}}. Further usage may be invoiced as overage.</p>""",
            footer="Sent by VOXBULK Billing · billing@voxbulk.com",
        ),
    },
    "payment_receipt": {
        "title": "Payment receipt",
        "subject": "Payment received — {{invoice_number}}",
        "body": wrap_brand_email(
            title="Payment received",
            inner_html="""<p>Hi,</p>
  <p>We have received your payment of <strong>{{total}}</strong> for invoice <strong>{{invoice_number}}</strong>.</p>
  <p style="font-size:13px;color:#6b6560;">Your invoice PDF is attached for your records.</p>""",
            footer="Sent by VOXBULK Billing · billing@voxbulk.com",
        ),
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
  <p>Please choose a time for your AI interview. You can take it by phone call or in a browser audio meeting, depending on your number.</p>
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
  <p>Your <strong>{{role}}</strong> interview at <strong>{{company_name}}</strong> is confirmed.</p>
  <div style="margin:20px 0;padding:16px;background:#f5f1ea;border-radius:10px;border:1px solid #e5e0d8;">
    <p style="margin:0 0 6px;"><strong>Date:</strong> {{interview_date}}</p>
    <p style="margin:0 0 6px;"><strong>Time:</strong> {{interview_time}} UK time (GMT/BST)</p>
    <p style="margin:0;font-size:13px;color:#6b6560;">{{interview_channel_note}}</p>
  </div>
  {{meeting_link_html}}
  {{calendar_links_html}}
  <p style="font-size:13px;color:#6b6560;">Need to change your time? Reply to this email or use the reschedule link from your original booking message.</p>
  <p style="font-size:13px;color:#6b6560;">This message was sent from careers@voxbulk.com — please check your Spam or Junk folder if you cannot find it.</p>""",
        ),
    },
    "interview_booking_reminder": {
        "title": "Interview reminder (30 min)",
        "subject": "Reminder — {{role}} interview in 30 minutes",
        "body": wrap_interview_email(
            title="Interview starting soon",
            inner_html="""<p>Hi <strong>{{candidate_name}}</strong>,</p>
  <p>This is a reminder that your <strong>{{role}}</strong> interview with <strong>{{company_name}}</strong> starts soon.</p>
  <div style="margin:20px 0;padding:16px;background:#f5f1ea;border-radius:10px;border:1px solid #e5e0d8;">
    <p style="margin:0 0 6px;"><strong>Date:</strong> {{interview_date}}</p>
    <p style="margin:0;"><strong>Time:</strong> {{interview_time}}</p>
  </div>
  {{meeting_link_html}}
  {{calendar_links_html}}
  <p style="font-size:13px;color:#6b6560;">{{interview_channel_note}}</p>""",
        ),
    },
    "interview_booking_reschedule_link": {
        "title": "Interview reschedule link",
        "subject": "Reschedule your interview — {{role}} at {{company_name}}",
        "body": wrap_interview_email(
            title="Reschedule your interview",
            inner_html="""<p>Hi <strong>{{candidate_name}}</strong>,</p>
  <p>Your <strong>{{role}}</strong> interview at <strong>{{company_name}}</strong> is currently booked for <strong>{{current_slot}}</strong>.</p>
  <p>Tap below to pick a new time:</p>
  """ + cta_button(href="{{reschedule_url}}", label="Pick a new time") + """
  <p style="font-size:13px;color:#6b6560;">If the button does not work, copy this link:<br />
  <a href="{{reschedule_url}}" style="color:#1a2d5c;word-break:break-all;">{{reschedule_url}}</a></p>
  <p style="font-size:13px;color:#6b6560;">This message was sent from careers@voxbulk.com — please check your Spam or Junk folder if you cannot find it.</p>""",
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
  <p style="font-size:13px;color:#6b6560;">You will not receive an AI call, booking link, or any further emails or messages about this job.</p>""",
        ),
    },
    "interview_campaign_cancelled": {
        "title": "Interview campaign cancelled",
        "subject": "{{role}} at {{company_name}} — campaign closed",
        "body": wrap_interview_email(
            title="Interview campaign closed",
            inner_html="""<p>Hi <strong>{{candidate_name}}</strong>,</p>
  <p>The <strong>{{role}}</strong> position at <strong>{{company_name}}</strong> is no longer running interviews.</p>
  <p style="font-size:14px;color:#3d3832;">{{closure_reason}}</p>
  <p style="font-size:13px;color:#6b6560;">Your booking link is now closed. You will not receive any further messages about this job.</p>""",
        ),
    },
    "interview_meeting_missed": {
        "title": "Missed online interview",
        "subject": "Missed interview — {{role}} at {{company_name}}",
        "body": wrap_interview_email(
            title="We missed you in the meeting room",
            inner_html="""<p>Hi <strong>{{candidate_name}}</strong>,</p>
  <p>Your booked <strong>{{role}}</strong> online interview at <strong>{{company_name}}</strong> has passed and we did not see you join.</p>
  <p>Please pick a new time using your booking link:</p>
  """ + cta_button(href="{{booking_url}}", label="Book again") + """
  <p style="font-size:13px;color:#6b6560;">If you still want to interview, join the online meeting room at your new booked time.</p>""",
        ),
    },
    "interview_missed_call_followup": {
        "title": "Interview missed call follow-up",
        "subject": "We tried to reach you — {{role}} at {{company_name}}",
        "body": wrap_interview_email(
            title="We tried to call you",
            inner_html="""<p>Hi <strong>{{candidate_name}}</strong>,</p>
  <p>We tried to reach you for a brief phone screening for the <strong>{{role}}</strong> role at <strong>{{company_name}}</strong>, but we could not connect.</p>
  <p>{{followup_message}}</p>
  """ + cta_button(href="{{booking_url}}", label="Book a call-back slot") + """
  <p style="font-size:13px;color:#6b6560;">If the button does not work, copy this link:<br />
  <a href="{{booking_url}}" style="color:#1a2d5c;word-break:break-all;">{{booking_url}}</a></p>
  <p style="font-size:13px;color:#6b6560;">This message was sent from careers@voxbulk.com — please check your Spam or Junk folder if you cannot find it.</p>""",
        ),
    },
    "interview_thank_you": {
        "title": "Interview thank-you",
        "subject": "Thank you for your interview — {{role}} at {{company_name}}",
        "body": wrap_interview_email(
            title="Thank you for your interview",
            inner_html="""<p>Hi <strong>{{candidate_name}}</strong>,</p>
  <p>Thank you for completing your <strong>{{role}}</strong> interview with <strong>{{company_name}}</strong>.</p>
  <p>We appreciate the time you took to speak with us. The hiring team will now review your interview and will be in touch regarding the next steps.</p>
  <p style="font-size:13px;color:#6b6560;">No further action is needed from you right now.</p>
  <p style="font-size:13px;color:#6b6560;">This message was sent from careers@voxbulk.com — please check your Spam or Junk folder if you cannot find it.</p>""",
        ),
    },
    "interview_session_reschedule": {
        "title": "Interview session — reschedule",
        "subject": "Pick a new interview time — {{role}} at {{company_name}}",
        "body": wrap_interview_email(
            title="Let's find a better time",
            inner_html="""<p>Hi <strong>{{candidate_name}}</strong>,</p>
  <p>Thanks for letting us know that now was not a good time for your <strong>{{role}}</strong> interview with <strong>{{company_name}}</strong>.</p>
  <p>Your previous slot has been released. Please pick a new time using the button below:</p>
  """
            + cta_button(href="{{reschedule_url}}", label="Choose a new time")
            + """
  <p style="font-size:13px;color:#6b6560;">If the button does not work, copy this link:<br />
  <a href="{{reschedule_url}}" style="color:#1a2d5c;word-break:break-all;">{{reschedule_url}}</a></p>
  <p style="font-size:13px;color:#6b6560;">This message was sent from careers@voxbulk.com — please check your Spam or Junk folder if you cannot find it.</p>""",
        ),
    },
    "interview_session_opted_out": {
        "title": "Interview session — opted out / closed",
        "subject": "Interview closed — {{role}} at {{company_name}}",
        "body": wrap_interview_email(
            title="Interview closed",
            inner_html="""<p>Hi <strong>{{candidate_name}}</strong>,</p>
  <p>Your <strong>{{role}}</strong> interview with <strong>{{company_name}}</strong> has been closed{{closure_reason_html}}.</p>
  <p style="font-size:14px;color:#3d3832;">{{closure_message}}</p>
  <p style="font-size:13px;color:#6b6560;">You will not receive further interview calls or booking emails for this role unless the employer contacts you separately.</p>
  <p style="font-size:13px;color:#6b6560;">This message was sent from careers@voxbulk.com — please check your Spam or Junk folder if you cannot find it.</p>""",
        ),
    },
    "billing_cancellation_requested": {
        "title": "Subscription cancellation requested",
        "subject": "Cancellation scheduled — {{organisation_name}}",
        "body": wrap_brand_email(
            title="Cancellation scheduled",
            inner_html="""<p>Hi,</p>
  <p>We received your request to cancel the VoxBulk subscription for <strong>{{organisation_name}}</strong>.</p>
  <p>Your plan stays active until <strong>{{effective_date}}</strong>. Renewals stop after that date.</p>
  <p>Estimated unused subscription value (remaining billing period only): <strong>{{estimated_refund}}</strong>.</p>
  <p>Refund preference: {{refund_preference}}.</p>
  <p style="font-size:13px;color:#6b6560;">{{timing_note}}</p>
  """ + cta_button(href="{{billing_url}}", label="View billing") + """
  <p style="font-size:13px;color:#6b6560;">You can keep your subscription before the end date from your billing page if you change your mind.</p>""",
            footer="Sent by VOXBULK Billing · billing@voxbulk.com",
        ),
    },
    "billing_cancellation_reversed": {
        "title": "Cancellation reversed",
        "subject": "Your subscription will continue — {{organisation_name}}",
        "body": wrap_brand_email(
            title="Subscription continued",
            inner_html="""<p>Hi,</p>
  <p>Your scheduled cancellation for <strong>{{organisation_name}}</strong> has been removed.</p>
  <p>Your subscription will renew as normal. No refund action was taken.</p>
  """ + cta_button(href="{{billing_url}}", label="View billing") + "",
            footer="Sent by VOXBULK Billing · billing@voxbulk.com",
        ),
    },
    "billing_plan_change_scheduled": {
        "title": "Plan change scheduled",
        "subject": "Plan change scheduled — {{organisation_name}}",
        "body": wrap_brand_email(
            title="Plan change scheduled",
            inner_html="""<p>Hi,</p>
  <p>We received your request to change the VoxBulk plan for <strong>{{organisation_name}}</strong>.</p>
  <p>Current plan: <strong>{{current_plan_name}}</strong><br/>
  New plan (from next billing period): <strong>{{pending_plan_name}}</strong></p>
  <p>Your current plan stays active until <strong>{{effective_date}}</strong>. The new plan and pricing apply from your next renewal date.</p>
  """ + cta_button(href="{{packages_url}}", label="View packages") + """
  <p style="font-size:13px;color:#6b6560;">You can change your plan again from Account → Packages before the effective date.</p>
  """ + cta_button(href="{{billing_url}}", label="View billing") + "",
            footer="Sent by VOXBULK Billing · billing@voxbulk.com",
        ),
    },
    "billing_wallet_credit_issued": {
        "title": "Wallet credit issued",
        "subject": "Wallet credit {{amount}} — {{organisation_name}}",
        "body": wrap_brand_email(
            title="Wallet credit issued",
            inner_html="""<p>Hi,</p>
  <p>We have added <strong>{{amount}}</strong> to your VoxBulk wallet for <strong>{{organisation_name}}</strong>.</p>
  <p>Your new wallet balance is <strong>{{wallet_balance}}</strong>.</p>
  <p style="font-size:13px;color:#6b6560;">{{timing_note}}</p>
  """ + cta_button(href="{{billing_url}}", label="View billing") + "",
            footer="Sent by VOXBULK Billing · billing@voxbulk.com",
        ),
    },
    "billing_bank_refund_approved": {
        "title": "Bank refund approved",
        "subject": "Refund approved — {{amount}} to {{payment_method}}",
        "body": wrap_brand_email(
            title="Refund approved",
            inner_html="""<p>Hi,</p>
  <p>We approved a refund of <strong>{{amount}}</strong> for <strong>{{organisation_name}}</strong>.</p>
  <p>Payment method: {{payment_method}}<br />Reference: {{payment_reference}}</p>
  <p style="font-size:13px;color:#6b6560;">{{processing_note}} {{reflection_note}}</p>
  """ + cta_button(href="{{billing_url}}", label="View billing") + "",
            footer="Sent by VOXBULK Billing · billing@voxbulk.com",
        ),
    },
    "billing_refund_request_rejected": {
        "title": "Refund request update",
        "subject": "Refund request update — {{organisation_name}}",
        "body": wrap_brand_email(
            title="Refund request update",
            inner_html="""<p>Hi,</p>
  <p>We reviewed your refund request for <strong>{{organisation_name}}</strong> (estimated unused value {{amount}}).</p>
  <p>Status: <strong>Not approved</strong>.</p>
  <p style="font-size:13px;color:#6b6560;">{{admin_notes}}</p>
  """ + cta_button(href="{{billing_url}}", label="View billing") + "",
            footer="Sent by VOXBULK Billing · billing@voxbulk.com",
        ),
    },
    "billing_subscription_ended": {
        "title": "Subscription ended",
        "subject": "Your {{product_name}} subscription has ended — {{organisation_name}}",
        "body": wrap_brand_email(
            title="Subscription ended",
            inner_html="""<p>Hi,</p>
  <p>Your <strong>{{product_name}}</strong> subscription for <strong>{{organisation_name}}</strong> has ended.</p>
  <p>To launch new campaigns again, choose a plan on Packages &amp; pricing.</p>
  """ + cta_button(href="{{packages_url}}", label="View packages") + """
  <p style="font-size:13px;color:#6b6560;">You can also review past invoices from your billing page.</p>
  """ + cta_button(href="{{billing_url}}", label="View billing") + "",
            footer="Sent by VOXBULK Billing · billing@voxbulk.com",
        ),
    },
    "billing_renewal_reminder": {
        "title": "Subscription renewal reminder",
        "subject": "{{product_name}} renews in {{days_remaining}} day(s) — {{organisation_name}}",
        "body": wrap_brand_email(
            title="Renewal reminder",
            inner_html="""<p>Hi,</p>
  <p>Your <strong>{{product_name}}</strong> subscription for <strong>{{organisation_name}}</strong> renews on <strong>{{renewal_date}}</strong> ({{days_remaining}} day(s) from now).</p>
  <p>No action is needed if your Direct Debit is active — we'll charge your saved payment method automatically.</p>
  """ + cta_button(href="{{billing_url}}", label="View billing") + """
  <p style="font-size:13px;color:#6b6560;">Manage your plan or payment details from Account → Packages.</p>
  """ + cta_button(href="{{packages_url}}", label="View packages") + "",
            footer="Sent by VOXBULK Billing · billing@voxbulk.com",
        ),
    },
    "billing_pending_invoice_reminder": {
        "title": "Pending invoice reminder",
        "subject": "Payment reminder — invoice {{invoice_number}} — {{organisation_name}}",
        "body": wrap_brand_email(
            title="Payment reminder",
            inner_html="""<p>Hi,</p>
  <p>This is a reminder that invoice <strong>{{invoice_number}}</strong> for <strong>{{organisation_name}}</strong> is still outstanding ({{days_outstanding}} day(s) since issue).</p>
  <p><strong>Amount:</strong> {{amount_display}}<br/>
  <strong>Description:</strong> {{invoice_description}}</p>
  <p>If you pay by Direct Debit, collection may still be in progress. Otherwise please complete payment from your billing page.</p>
  """ + cta_button(href="{{billing_url}}", label="View billing") + "",
            footer="Sent by VOXBULK Billing · billing@voxbulk.com",
        ),
    },
    "billing_payment_action_required": {
        "title": "Payment action required",
        "subject": "Action required — update payment for {{organisation_name}}",
        "body": wrap_brand_email(
            title="Payment action required",
            inner_html="""<p>Hi,</p>
  <p>We couldn't collect payment for <strong>{{organisation_name}}</strong> ({{product_name}}).</p>
  <p><strong>Reason:</strong> {{failure_reason}}</p>
  <p>Please update your Direct Debit mandate or resolve the outstanding balance to avoid service interruption.</p>
  """ + cta_button(href="{{billing_url}}", label="Update payment") + """
  <p style="font-size:13px;color:#6b6560;">Need help? Reply to this email or contact support@voxbulk.com.</p>
  """,
            footer="Sent by VOXBULK Billing · billing@voxbulk.com",
        ),
    },
    "survey_ai_followup_promo": {
        "title": "Survey AI follow-up promo code",
        "subject": "Your thank-you code from {{organisation_name}}",
        "body": wrap_brand_email(
            title="Thank you for your feedback",
            inner_html="""<p>Hi <strong>{{customer_name}}</strong>,</p>
  <p>Thank you for speaking with us about your experience with <strong>{{organisation_name}}</strong>.</p>
  <p>As a gesture of appreciation, here is your promo code:</p>
  <p style="font-size:22px;letter-spacing:0.06em;font-family:ui-monospace,Menlo,Consolas,monospace;"><strong>{{promo_code}}</strong></p>
  <p>{{promo_description}}</p>
  <p style="font-size:13px;color:#6b6560;">Questions? Contact <a href="mailto:{{support_email}}" style="color:#1a2d5c;">{{support_email}}</a>.</p>""",
            footer="Sent by VOXBULK · survey.codes@voxbulk.com",
        ),
    },
    "sales_payout_invoice_received": {
        "title": "Payout invoice received",
        "subject": "We received your payout invoice {{invoice_number}}",
        "body": wrap_brand_email(
            title="Payout invoice received",
            inner_html="""<p>Hi <strong>{{name}}</strong>,</p>
  <p>We have received your commission payout invoice for <strong>{{company_name}}</strong>.</p>
  <p><strong>Invoice:</strong> {{invoice_number}}<br />
  <strong>Amount:</strong> {{amount}} {{currency}}<br />
  <strong>Submitted:</strong> {{submitted_at}}<br />
  <strong>Payout method:</strong> {{payout_method_summary}}</p>
  <p>Our team will review it and confirm once payment is approved.</p>""",
            footer="Sent by VOXBULK · finance@voxbulk.com",
            badge="Sales payout",
        ),
    },
    "sales_payout_invoice_paid": {
        "title": "Payout invoice paid",
        "subject": "Payout paid — {{invoice_number}} ({{amount}})",
        "body": wrap_brand_email(
            title="Payout invoice paid",
            inner_html="""<p>Hi <strong>{{name}}</strong>,</p>
  <p>Your commission payout invoice has been approved and marked as paid.</p>
  <p><strong>Invoice:</strong> {{invoice_number}}<br />
  <strong>Amount:</strong> {{amount}} {{currency}}<br />
  <strong>Paid:</strong> {{paid_at}}<br />
  <strong>Payout method:</strong> {{payout_method_summary}}</p>
  <p>Thank you for partnering with VOXBULK.</p>""",
            footer="Sent by VOXBULK · finance@voxbulk.com",
            badge="Sales payout",
        ),
    },
    "sales_hub_invoice_sent": {
        "title": "Sales hub invoice sent",
        "subject": "Invoice {{invoice_number}} from Voxbulk ({{total}})",
        "body": wrap_brand_email(
            title="Your invoice",
            inner_html="""<p>Hi <strong>{{customer_name}}</strong>,</p>
  <p>Please find invoice <strong>{{invoice_number}}</strong> attached.</p>
  <p><strong>Total:</strong> {{total}} {{currency}}<br />
  <strong>Due:</strong> {{due_at}}</p>
  <p>Questions? Reply to this email or contact sales@voxbulk.com.</p>""",
            footer="Sent by VOXBULK · sales@voxbulk.com",
            badge="Sales",
        ),
    },
    "sales_hub_invoice_reminder": {
        "title": "Sales hub invoice reminder",
        "subject": "Reminder: invoice {{invoice_number}} ({{total}})",
        "body": wrap_brand_email(
            title="Invoice reminder",
            inner_html="""<p>Hi <strong>{{customer_name}}</strong>,</p>
  <p>This is a friendly reminder that invoice <strong>{{invoice_number}}</strong> is still open.</p>
  <p><strong>Total:</strong> {{total}} {{currency}}<br />
  <strong>Due:</strong> {{due_at}}</p>
  <p>The PDF is attached. Please get in touch if you need help.</p>""",
            footer="Sent by VOXBULK · sales@voxbulk.com",
            badge="Sales",
        ),
    },
    "expo_visitor_catalogue": {
        "title": "Expo catalogue / price list",
        "subject": "Your files from {{company_name}}",
        "body": wrap_brand_email(
            title="Your catalogue & price list",
            inner_html="""<p>Hi <strong>{{first_name}}</strong>,</p>
  <p>Thank you for visiting <strong>{{company_name}}</strong> at the exhibition (<strong>{{booth_name}}</strong>).</p>
  <p>Here are the files you requested:</p>
  {{asset_links}}
  {{offer_block}}
  <p style="margin-top:20px;padding:14px 16px;background:#f7f5f2;border-radius:10px;">
    <strong>Contact this stand</strong><br />
    Email: <a href="mailto:{{contact_email}}">{{contact_email}}</a><br />
    {{contact_phone_line}}
    {{company_website_line}}
  </p>
  <p style="font-size:13px;color:#6b6560;">If a link does not open, reply to this email and we will resend.</p>""",
            footer="Sent via VOXBULK Expo · expo@voxbulk.com",
            badge="Expo",
        ),
    },
    "expo_exhibitor_lead_digest": {
        "title": "Expo hot lead notify",
        "subject": "Hot Expo lead — {{lead_name}} asked for catalogue / prices",
        "body": wrap_brand_email(
            title="New Expo hot lead",
            inner_html="""<p>Hi,</p>
  <p>A visitor at <strong>{{booth_name}}</strong> requested your catalogue or price list.</p>
  <p><strong>Name:</strong> {{lead_name}}<br />
  <strong>Company:</strong> {{company}}<br />
  <strong>Mobile:</strong> {{mobile}}<br />
  <strong>Email:</strong> {{email}}<br />
  <strong>Interest:</strong> {{interest}}<br />
  <strong>Timeline:</strong> {{timeline}}<br />
  <strong>Catalogue requested:</strong> {{catalogue_requested}}<br />
  <strong>Price list requested:</strong> {{price_list_requested}}<br />
  <strong>Offer interested:</strong> {{offer_interested}}<br />
  <strong>Files sent:</strong> {{asset_list}}<br />
  <strong>Opened:</strong> {{opened_summary}}</p>
  """ + cta_button(href="{{leads_url}}", label="Open Expo leads") + "",
            footer="Sent via VOXBULK Expo · expo@voxbulk.com",
            badge="Expo lead",
        ),
    },
    "expo_visitor_day_summary": {
        "title": "Expo visitor day / end summary",
        "subject": "Your Expo day at {{exhibition_name}} — {{stands_visited}} stands",
        "body": wrap_brand_email(
            title="{{summary_heading}}",
            inner_html="""<p>Hi <strong>{{first_name}}</strong>,</p>
  <p>{{summary_intro}}</p>
  {{kpi_html}}
  <p style="margin-top:24px;font-weight:600;">Stands you visited</p>
  {{stands_html}}
  <p style="font-size:13px;color:#6b6560;margin-top:20px;">Save the contact emails below to follow up after the show.</p>""",
            footer="Sent via VOXBULK Expo · expo@voxbulk.com",
            badge="Expo summary",
        ),
    },
    "smart_card_lead_notify": {
        "title": "Smart Card QR lead notify",
        "subject": "New Smart Card QR lead — {{lead_name}} ({{lead_score}})",
        "body": wrap_brand_email(
            title="New Smart Card QR lead",
            inner_html="""<p>Hi <strong>{{rep_name}}</strong>,</p>
  <p>{{ai_summary}}</p>
  <p><strong>Name:</strong> {{lead_name}}<br />
  <strong>Company:</strong> {{company}}<br />
  <strong>Mobile:</strong> {{mobile}}<br />
  <strong>Email:</strong> {{email}}<br />
  <strong>Interest:</strong> {{interest}}<br />
  <strong>Timeline:</strong> {{timeline}}<br />
  <strong>Score:</strong> {{lead_score}}</p>
  <p><strong>Suggested follow-up:</strong><br />{{suggested_follow_up}}</p>
  """
            + cta_button(href="{{leads_url}}", label="Open leads")
            + "",
            footer="Sent via VOXBULK Smart Card QR · smartqr@voxbulk.com",
            badge="Smart Card QR",
        ),
    },
    "smart_card_rep_invite": {
        "title": "Smart Card QR representative invite",
        "subject": "You're invited to Smart Card QR — {{org_name}}",
        "body": wrap_brand_email(
            title="Join Smart Card QR",
            inner_html="""<p>Hi <strong>{{rep_name}}</strong>,</p>
  <p><strong>{{org_name}}</strong> invited you to view your Smart Card QR leads.</p>
  <p>Create your account to see only your own leads and assigned products.</p>
  """
            + cta_button(href="{{signup_url}}", label="Accept invite")
            + "",
            footer="Sent via VOXBULK Smart Card QR · smartqr@voxbulk.com",
            badge="Smart Card QR",
        ),
    },
    "smart_card_renewal_reminder_30d": {
        "title": "Smart Card QR renewal — 30 days",
        "subject": "Smart Card QR renews in 1 month — {{org_name}}",
        "body": wrap_brand_email(
            title="Renewal reminder (1 month)",
            inner_html="""<p>Hi,</p>
  <p>Your Smart Card QR package for <strong>{{org_name}}</strong> ends on <strong>{{period_end}}</strong> ({{seats}} seats).</p>
  """
            + cta_button(href="{{renew_url}}", label="Renew package")
            + "",
            footer="Sent via VOXBULK Smart Card QR · smartqr@voxbulk.com",
            badge="Smart Card QR",
        ),
    },
    "smart_card_renewal_reminder_14d": {
        "title": "Smart Card QR renewal — 14 days",
        "subject": "Smart Card QR renews in 2 weeks — {{org_name}}",
        "body": wrap_brand_email(
            title="Renewal reminder (2 weeks)",
            inner_html="""<p>Hi,</p>
  <p>Your Smart Card QR package for <strong>{{org_name}}</strong> ends on <strong>{{period_end}}</strong>.</p>
  """
            + cta_button(href="{{renew_url}}", label="Renew package")
            + "",
            footer="Sent via VOXBULK Smart Card QR · smartqr@voxbulk.com",
            badge="Smart Card QR",
        ),
    },
    "smart_card_renewal_reminder_7d": {
        "title": "Smart Card QR renewal — 7 days",
        "subject": "Smart Card QR renews in 1 week — {{org_name}}",
        "body": wrap_brand_email(
            title="Renewal reminder (1 week)",
            inner_html="""<p>Hi,</p>
  <p>Your Smart Card QR package for <strong>{{org_name}}</strong> ends on <strong>{{period_end}}</strong>.</p>
  """
            + cta_button(href="{{renew_url}}", label="Renew package")
            + "",
            footer="Sent via VOXBULK Smart Card QR · smartqr@voxbulk.com",
            badge="Smart Card QR",
        ),
    },
    "smart_card_renewal_reminder_1d": {
        "title": "Smart Card QR renewal — 1 day",
        "subject": "Smart Card QR renews tomorrow — {{org_name}}",
        "body": wrap_brand_email(
            title="Renewal reminder (1 day)",
            inner_html="""<p>Hi,</p>
  <p>Your Smart Card QR package for <strong>{{org_name}}</strong> ends tomorrow (<strong>{{period_end}}</strong>).</p>
  """
            + cta_button(href="{{renew_url}}", label="Renew now")
            + "",
            footer="Sent via VOXBULK Smart Card QR · smartqr@voxbulk.com",
            badge="Smart Card QR",
        ),
    },
    "smart_card_expired": {
        "title": "Smart Card QR expired",
        "subject": "Smart Card QR expired — renew to go live again",
        "body": wrap_brand_email(
            title="We're sorry — your package expired",
            inner_html="""<p>Hi,</p>
  <p>The Smart Card QR package for <strong>{{org_name}}</strong> has expired. Scans are paused until you renew.</p>
  """
            + cta_button(href="{{renew_url}}", label="Renew package")
            + "",
            footer="Sent via VOXBULK Smart Card QR · smartqr@voxbulk.com",
            badge="Smart Card QR",
        ),
    },
}
