"""0163 — survey codes mailbox for AI follow-up promo emails.

Revision ID: 0163_survey_codes_mailbox
Revises: 0162_survey_ai_follow_up_jobs
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0163_survey_codes_mailbox"
down_revision = "0162_survey_ai_follow_up_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "survey_codes_mailbox_settings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "mailbox_email",
            sa.String(length=320),
            nullable=False,
            server_default="survey.codes@voxbulk.com",
        ),
        sa.Column(
            "from_name",
            sa.String(length=255),
            nullable=False,
            server_default="VOXBULK Survey Codes",
        ),
        sa.Column("smtp_username", sa.String(length=255), nullable=True),
        sa.Column("password_encrypted", sa.Text(), nullable=True),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("survey_codes_mailbox_settings")
