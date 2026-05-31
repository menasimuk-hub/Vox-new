"""Fallback WhatsApp booking preview — mirrors approved Telnyx templates."""

from __future__ import annotations

INTERVIEW_BOOKING_TEMPLATE_NAME = "voxbulk_interview_book"
INTERVIEW_EMAIL_SENT_TEMPLATE_NAME = "interview_email_sent"
INTERVIEW_CONFIRMATION_TEMPLATE_NAME = "voxbulk_interview_confirm"

# Launch notice (no booking link on WA): {{1}} name, {{2}} role, {{3}} company, {{4}} company
INTERVIEW_EMAIL_SENT_BODY = """Dear {{1}} 👋

We have sent you an email from 📧 careers@voxbulk.com regarding your interview for the position of {{2}} at {{3}}

Please check your Spam / Junk folder in case it landed there 📁

Once you receive it, kindly book your interview slot as mentioned in the email 📅

We look forward to hearing from you! 🤝

{{4}} 🏢"""

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
