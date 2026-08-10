"""WhatsApp notice when a demo invite email is sent (no magic link on WA)."""

from __future__ import annotations

# Meta/Telnyx template name when approved; plain fallback uses DEMO_EMAIL_SENT_BODY.
DEMO_EMAIL_SENT_TEMPLATE_NAME = "voxbulk_demo_email_sent"

# {{1}} name, {{2}} company, {{3}} from email
DEMO_EMAIL_SENT_BODY = """Dear {{1}} 👋

We have sent you an email with your VoxBulk AI demo link for *{{2}}* from 📧 {{3}}

Please check your Spam / Junk folder in case it landed there 📁

Open the email and tap Start AI demo when you are ready. The link is valid for 7 days and works once.

If the connection fails, use Resend demo link in the same email — we will continue where you left off.

We look forward to showing you VoxBulk! 🤝"""
