"""0164 — platform-wide OFCOM contact time settings.

Revision ID: 0164_platform_contact_time
Revises: 0163_survey_codes_mailbox
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0164_platform_contact_time"
down_revision = "0163_survey_codes_mailbox"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "platform_contact_time_settings",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("calling_days", sa.String(length=32), nullable=False, server_default="1,2,3,4,5"),
        sa.Column("calling_start", sa.String(length=8), nullable=False, server_default="08:00"),
        sa.Column("calling_end", sa.String(length=8), nullable=False, server_default="21:00"),
        sa.Column(
            "calling_fallback_tz",
            sa.String(length=64),
            nullable=False,
            server_default="Europe/London",
        ),
        sa.Column("wa_days", sa.String(length=32), nullable=False, server_default="1,2,3,4,5,6"),
        sa.Column("wa_start", sa.String(length=8), nullable=False, server_default="09:00"),
        sa.Column("wa_end", sa.String(length=8), nullable=False, server_default="20:00"),
        sa.Column(
            "wa_fallback_tz",
            sa.String(length=64),
            nullable=False,
            server_default="Europe/London",
        ),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.execute(
        sa.text(
            """
            INSERT INTO platform_contact_time_settings (
                id, calling_days, calling_start, calling_end, calling_fallback_tz,
                wa_days, wa_start, wa_end, wa_fallback_tz, updated_at
            ) VALUES (
                'default', '1,2,3,4,5', '08:00', '21:00', 'Europe/London',
                '1,2,3,4,5,6', '09:00', '20:00', 'Europe/London', CURRENT_TIMESTAMP
            )
            """
        )
    )


def downgrade() -> None:
    op.drop_table("platform_contact_time_settings")
