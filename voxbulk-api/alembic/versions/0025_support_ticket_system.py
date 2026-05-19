"""support ticket system

Revision ID: 0025_support_ticket_system
Revises: 0024_membership_dashboard_setup_plan_details
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0025_support_ticket_system"
down_revision = "0024_membership_dashboard_setup_plan_details"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "support_tickets",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("public_ref", sa.String(length=32), nullable=True),
        sa.Column("organisation_id", sa.String(length=36), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("branch_id", sa.String(length=36), sa.ForeignKey("branches.id"), nullable=True),
        sa.Column("created_by_user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("category", sa.String(length=30), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="open"),
        sa.Column("priority", sa.String(length=30), nullable=True),
        sa.Column("assigned_admin_user_id", sa.String(length=36), sa.ForeignKey("admin_users.id"), nullable=True),
        sa.Column("customer_unread", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("admin_unread", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_message_at", sa.DateTime(), nullable=False),
        sa.Column("closed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("uq_support_tickets_public_ref", "support_tickets", ["public_ref"], unique=True)
    op.create_index("ix_support_tickets_organisation_id", "support_tickets", ["organisation_id"])
    op.create_index("ix_support_tickets_branch_id", "support_tickets", ["branch_id"])
    op.create_index("ix_support_tickets_created_by_user_id", "support_tickets", ["created_by_user_id"])
    op.create_index("ix_support_tickets_category", "support_tickets", ["category"])
    op.create_index("ix_support_tickets_status", "support_tickets", ["status"])
    op.create_index("ix_support_tickets_assigned_admin_user_id", "support_tickets", ["assigned_admin_user_id"])
    op.create_index("ix_support_tickets_last_message_at", "support_tickets", ["last_message_at"])

    op.create_table(
        "support_ticket_messages",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("ticket_id", sa.Integer(), sa.ForeignKey("support_tickets.id"), nullable=False),
        sa.Column("sender_type", sa.String(length=20), nullable=False),
        sa.Column("sender_user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("sender_admin_user_id", sa.String(length=36), sa.ForeignKey("admin_users.id"), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("is_internal_note", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_support_ticket_messages_ticket_id", "support_ticket_messages", ["ticket_id"])
    op.create_index("ix_support_ticket_messages_sender_user_id", "support_ticket_messages", ["sender_user_id"])
    op.create_index("ix_support_ticket_messages_sender_admin_user_id", "support_ticket_messages", ["sender_admin_user_id"])

    op.create_table(
        "support_ticket_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("ticket_id", sa.Integer(), sa.ForeignKey("support_tickets.id"), nullable=False),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("actor_type", sa.String(length=20), nullable=False, server_default="system"),
        sa.Column("actor_user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("actor_admin_user_id", sa.String(length=36), sa.ForeignKey("admin_users.id"), nullable=True),
        sa.Column("from_value", sa.String(length=255), nullable=True),
        sa.Column("to_value", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_support_ticket_events_ticket_id", "support_ticket_events", ["ticket_id"])


def downgrade() -> None:
    op.drop_index("ix_support_ticket_events_ticket_id", table_name="support_ticket_events")
    op.drop_table("support_ticket_events")
    op.drop_index("ix_support_ticket_messages_sender_admin_user_id", table_name="support_ticket_messages")
    op.drop_index("ix_support_ticket_messages_sender_user_id", table_name="support_ticket_messages")
    op.drop_index("ix_support_ticket_messages_ticket_id", table_name="support_ticket_messages")
    op.drop_table("support_ticket_messages")
    op.drop_index("ix_support_tickets_last_message_at", table_name="support_tickets")
    op.drop_index("ix_support_tickets_assigned_admin_user_id", table_name="support_tickets")
    op.drop_index("ix_support_tickets_status", table_name="support_tickets")
    op.drop_index("ix_support_tickets_category", table_name="support_tickets")
    op.drop_index("ix_support_tickets_created_by_user_id", table_name="support_tickets")
    op.drop_index("ix_support_tickets_branch_id", table_name="support_tickets")
    op.drop_index("ix_support_tickets_organisation_id", table_name="support_tickets")
    op.drop_index("uq_support_tickets_public_ref", table_name="support_tickets")
    op.drop_table("support_tickets")

