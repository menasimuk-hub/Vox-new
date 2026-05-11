"""notifications

Revision ID: 0028_notifications
Revises: 0027_faq_system
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0028_notifications"
down_revision = "0027_faq_system"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("organisation_id", sa.String(length=36), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("type", sa.String(length=60), nullable=False),
        sa.Column("title", sa.String(length=180), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(length=30), nullable=False, server_default="info"),
        sa.Column("ticket_id", sa.Integer(), sa.ForeignKey("support_tickets.id"), nullable=True),
        sa.Column("action_url", sa.String(length=255), nullable=True),
        sa.Column("dedupe_key", sa.String(length=255), nullable=False),
        sa.Column("read_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("dedupe_key", name="uq_notifications_dedupe_key"),
    )
    op.create_index("ix_notifications_organisation_id", "notifications", ["organisation_id"])
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])
    op.create_index("ix_notifications_type", "notifications", ["type"])
    op.create_index("ix_notifications_ticket_id", "notifications", ["ticket_id"])
    op.create_index("ix_notifications_read_at", "notifications", ["read_at"])
    op.create_index("ix_notifications_created_at", "notifications", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_notifications_created_at", table_name="notifications")
    op.drop_index("ix_notifications_read_at", table_name="notifications")
    op.drop_index("ix_notifications_ticket_id", table_name="notifications")
    op.drop_index("ix_notifications_type", table_name="notifications")
    op.drop_index("ix_notifications_user_id", table_name="notifications")
    op.drop_index("ix_notifications_organisation_id", table_name="notifications")
    op.drop_table("notifications")
