"""faq system

Revision ID: 0027_faq_system
Revises: 0026_ticket_attachments_canned_replies
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0027_faq_system"
down_revision = "0026_ticket_attachments_canned_replies"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "faq_categories",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("slug", sa.String(length=180), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_faq_categories_name", "faq_categories", ["name"], unique=True)
    op.create_index("ix_faq_categories_slug", "faq_categories", ["slug"], unique=True)
    op.create_index("ix_faq_categories_sort_order", "faq_categories", ["sort_order"])

    op.create_table(
        "faq_items",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("category_id", sa.Integer(), sa.ForeignKey("faq_categories.id"), nullable=True),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("is_featured", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_faq_items_category_id", "faq_items", ["category_id"])
    op.create_index("ix_faq_items_is_featured", "faq_items", ["is_featured"])
    op.create_index("ix_faq_items_is_published", "faq_items", ["is_published"])
    op.create_index("ix_faq_items_sort_order", "faq_items", ["sort_order"])


def downgrade() -> None:
    op.drop_index("ix_faq_items_sort_order", table_name="faq_items")
    op.drop_index("ix_faq_items_is_published", table_name="faq_items")
    op.drop_index("ix_faq_items_is_featured", table_name="faq_items")
    op.drop_index("ix_faq_items_category_id", table_name="faq_items")
    op.drop_table("faq_items")
    op.drop_index("ix_faq_categories_sort_order", table_name="faq_categories")
    op.drop_index("ix_faq_categories_slug", table_name="faq_categories")
    op.drop_index("ix_faq_categories_name", table_name="faq_categories")
    op.drop_table("faq_categories")

