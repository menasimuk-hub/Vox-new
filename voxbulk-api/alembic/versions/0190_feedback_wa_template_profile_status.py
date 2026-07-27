"""Per-profile CF WhatsApp template status ledger.

Revision ID: 0190_feedback_wa_template_profile_status
Revises: 0189_expo_asset_purpose_opened
Create Date: 2026-07-27
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0190_feedback_wa_template_profile_status"
down_revision = "0189_expo_asset_purpose_opened"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "feedback_wa_template_profile_status",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("feedback_template_id", sa.String(length=36), nullable=False),
        sa.Column("connection_profile_id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=16), nullable=True),
        sa.Column("profile_label", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("meta_template_name", sa.String(length=512), nullable=True),
        sa.Column("remote_record_id", sa.String(length=64), nullable=True),
        sa.Column("category", sa.String(length=32), nullable=True),
        sa.Column("last_push_error", sa.Text(), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(), nullable=True),
        sa.Column("last_pushed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["connection_profile_id"], ["connection_profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["feedback_template_id"], ["feedback_wa_templates.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "feedback_template_id",
            "connection_profile_id",
            name="uq_feedback_wa_tpl_profile_status",
        ),
    )
    op.create_index(
        "ix_feedback_wa_template_profile_status_feedback_template_id",
        "feedback_wa_template_profile_status",
        ["feedback_template_id"],
    )
    op.create_index(
        "ix_feedback_wa_template_profile_status_connection_profile_id",
        "feedback_wa_template_profile_status",
        ["connection_profile_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_feedback_wa_template_profile_status_connection_profile_id",
        table_name="feedback_wa_template_profile_status",
    )
    op.drop_index(
        "ix_feedback_wa_template_profile_status_feedback_template_id",
        table_name="feedback_wa_template_profile_status",
    )
    op.drop_table("feedback_wa_template_profile_status")
