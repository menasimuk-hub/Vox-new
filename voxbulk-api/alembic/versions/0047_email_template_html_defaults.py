"""seed system email templates with HTML bodies and titles

Revision ID: 0047_email_template_html_defaults
Revises: 0046_messaging_templates
"""

from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from alembic import op

revision = "0047_email_template_html_defaults"
down_revision = "0046_messaging_templates"
branch_labels = None
depends_on = None

NOW = datetime.utcnow()

SYSTEM_DEFAULTS = {
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
        "title": "New invoice",
        "subject": "New invoice",
        "body": "<p>Hello,</p><p>New invoice <strong>#{{invoice_id}}</strong> — amount <strong>{{amount_gbp_pence}}</strong> pence ({{currency}}), status {{invoice_status}}.</p>",
    },
    "payment_failed": {
        "title": "Cancel / failed payment",
        "subject": "Payment issue",
        "body": "<p>Payment issue for <strong>{{user_email}}</strong>.</p><p>Amount due: <strong>{{amount}}</strong> · Invoice <strong>{{invoice_number}}</strong>.</p>",
    },
    "general_notification": {
        "title": "General activity",
        "subject": "Notification",
        "body": "<p>Hello {{user_name}},</p><p>{{message}}</p><p style=\"font-size:12px;color:#64748b;\">Sent by VOXBULK notifications.</p>",
    },
}


def upgrade() -> None:
    bind = op.get_bind()
    for key, data in SYSTEM_DEFAULTS.items():
        bind.execute(
            sa.text(
                """
                UPDATE email_templates
                SET title = :title, subject = :subject, body = :body, updated_at = :updated_at
                WHERE template_key = :key
                """
            ),
            {"key": key, "title": data["title"], "subject": data["subject"], "body": data["body"], "updated_at": NOW},
        )


def downgrade() -> None:
    pass
