"""ticket attachments and canned replies

Revision ID: 0026_ticket_attachments_canned_replies
Revises: 0025_support_ticket_system
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0026_ticket_attachments_canned_replies"
down_revision = "0025_support_ticket_system"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "support_ticket_attachments",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("ticket_id", sa.Integer(), sa.ForeignKey("support_tickets.id"), nullable=False),
        sa.Column("message_id", sa.Integer(), sa.ForeignKey("support_ticket_messages.id"), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=120), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_support_ticket_attachments_ticket_id", "support_ticket_attachments", ["ticket_id"])
    op.create_index("ix_support_ticket_attachments_message_id", "support_ticket_attachments", ["message_id"])

    op.create_table(
        "support_canned_reply_categories",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_support_canned_reply_categories_name", "support_canned_reply_categories", ["name"], unique=True)

    op.create_table(
        "support_canned_replies",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("category_id", sa.Integer(), sa.ForeignKey("support_canned_reply_categories.id"), nullable=True),
        sa.Column("title", sa.String(length=180), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_support_canned_replies_category_id", "support_canned_replies", ["category_id"])
    op.create_index("ix_support_canned_replies_title", "support_canned_replies", ["title"])


def downgrade() -> None:
    op.drop_index("ix_support_canned_replies_title", table_name="support_canned_replies")
    op.drop_index("ix_support_canned_replies_category_id", table_name="support_canned_replies")
    op.drop_table("support_canned_replies")
    op.drop_index("ix_support_canned_reply_categories_name", table_name="support_canned_reply_categories")
    op.drop_table("support_canned_reply_categories")
    op.drop_index("ix_support_ticket_attachments_message_id", table_name="support_ticket_attachments")
    op.drop_index("ix_support_ticket_attachments_ticket_id", table_name="support_ticket_attachments")
    op.drop_table("support_ticket_attachments")

