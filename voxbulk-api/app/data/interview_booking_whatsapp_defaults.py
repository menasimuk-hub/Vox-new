"""Fallback WhatsApp booking preview — mirrors approved Telnyx templates."""

from __future__ import annotations

INTERVIEW_BOOKING_TEMPLATE_NAME = "voxbulk_interview_book"
INTERVIEW_EMAIL_SENT_TEMPLATE_NAME = "interview_email_sent"
INTERVIEW_CONFIRMATION_TEMPLATE_NAME = "voxbulk_interview_confirm"
INTERVIEW_CANCEL_TEMPLATE_NAME = "voxbulk_interview_cancel"
INTERVIEW_JOB_CLOSED_TEMPLATE_NAME = "voxbulk_interview_job_closed"

# Candidate self-cancel: {{1}} name, {{2}} role, {{3}} company, {{4}} date, {{5}} time
INTERVIEW_BOOKING_CANCEL_BODY = (
    "Hi {{1}} 👋\n\n"
    "Your *{{2}}* interview at *{{3}}* on {{4}} at {{5}} has been cancelled ❌\n\n"
    "You will not receive any further messages about this role.\n\n"
    "Thank you."
)

# Employer closed the campaign: {{1}} name, {{2}} role, {{3}} company
INTERVIEW_JOB_CLOSED_BODY = (
    "Hi {{1}} 👋\n\n"
    "The *{{2}}* role at *{{3}}* is no longer available — this interview campaign has ended 🛑\n\n"
    "You will not receive any further messages about this job.\n\n"
    "Thank you for your interest."
)

# Launch notice (no booking link on WA): {{1}} name, {{2}} role, {{3}} company
INTERVIEW_EMAIL_SENT_BODY = """Dear {{1}} 👋

We have sent you an email from 📧 careers@voxbulk.com regarding your interview for the position of {{2}} at {{3}}

Please check your Spam / Junk folder in case it landed there 📁

Once you receive it, kindly book your interview slot as mentioned in the email 📅

We look forward to hearing from you! 🤝"""

# Legacy booking invite with URL button (deprecated at launch)
INTERVIEW_BOOKING_BODY = """Hi {{1}} 👋

You've been shortlisted for the *{{2}}* role at *{{3}}* ✨

Tap *Book My Interview* below to choose a time that works for you 🗓️

— VOXBULK"""

# Confirmation: {{1}} name, {{2}} job title, {{3}} date, {{4}} time
INTERVIEW_BOOKING_CONFIRMATION_BODY = (
    "👋Hi {{1}}, your *{{2}}* interview is 📆booked for {{3}} at {{4}} ✅\n\n"
    "Use the buttons below if you need to change or cancel."
)
INTERVIEW_BOOKING_INVITE_BUTTONS: list[dict[str, str]] = [
    {"label": "📅 Book My Interview", "type": "url"},
    {"label": "🔄 Reschedule", "type": "quick_reply"},
    {"label": "❌ Cancel", "type": "quick_reply"},
]

INTERVIEW_BOOKING_CONFIRMATION_BUTTONS: list[dict[str, str]] = [
    {"label": "🔄 Reschedule", "type": "quick_reply"},
    {"label": "❌ Cancel", "type": "quick_reply"},
]

# Legacy alias — booking invite shows all three actions in preview
INTERVIEW_BOOKING_PREVIEW_BUTTONS: list[dict[str, str]] = list(INTERVIEW_BOOKING_INVITE_BUTTONS)
