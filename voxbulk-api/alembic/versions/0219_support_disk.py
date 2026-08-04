"""0219 — Support Disk: channel, FAQ surface, KB, help links, SLA settings.

Revision ID: 0219_support_disk
Revises: 0218_sales_hub_functional
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0219_support_disk"
down_revision = "0218_sales_hub_functional"
branch_labels = None
depends_on = None


def _tables() -> set[str]:
    bind = op.get_bind()
    return set(sa.inspect(bind).get_table_names())


def _columns(table: str) -> set[str]:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if table not in insp.get_table_names():
        return set()
    return {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    tables = _tables()

    if "support_tickets" in tables:
        cols = _columns("support_tickets")
        if "channel" not in cols:
            op.add_column(
                "support_tickets",
                sa.Column("channel", sa.String(length=30), nullable=False, server_default="web"),
            )
            try:
                op.create_index("ix_support_tickets_channel", "support_tickets", ["channel"])
            except Exception:
                pass

    if "faq_categories" in tables:
        cols = _columns("faq_categories")
        if "surface" not in cols:
            op.add_column(
                "faq_categories",
                sa.Column("surface", sa.String(length=20), nullable=False, server_default="frontend"),
            )
            try:
                op.create_index("ix_faq_categories_surface", "faq_categories", ["surface"])
            except Exception:
                pass
        # Allow same name/slug on different surfaces.
        for uq in ("name", "slug"):
            try:
                op.drop_constraint(f"faq_categories_{uq}_key", "faq_categories", type_="unique")
            except Exception:
                pass
            try:
                op.drop_index(f"ix_faq_categories_{uq}", table_name="faq_categories")
            except Exception:
                pass

    if "faq_items" in tables:
        cols = _columns("faq_items")
        if "surface" not in cols:
            op.add_column(
                "faq_items",
                sa.Column("surface", sa.String(length=20), nullable=False, server_default="frontend"),
            )
            try:
                op.create_index("ix_faq_items_surface", "faq_items", ["surface"])
            except Exception:
                pass

    if "support_kb_categories" not in tables:
        op.create_table(
            "support_kb_categories",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("kind", sa.String(length=20), nullable=False, server_default="article"),
            sa.Column("name", sa.String(length=160), nullable=False),
            sa.Column("description", sa.Text(), nullable=False, server_default=""),
            sa.Column("colour", sa.String(length=40), nullable=False, server_default="#3b82f6"),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_support_kb_categories_kind", "support_kb_categories", ["kind"])
        op.create_index("ix_support_kb_categories_name", "support_kb_categories", ["name"])

    if "support_kb_articles" not in tables:
        op.create_table(
            "support_kb_articles",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("category_id", sa.Integer(), sa.ForeignKey("support_kb_categories.id"), nullable=True),
            sa.Column("kind", sa.String(length=20), nullable=False, server_default="article"),
            sa.Column("title", sa.String(length=300), nullable=False),
            sa.Column("slug", sa.String(length=200), nullable=False),
            sa.Column("body", sa.Text(), nullable=False, server_default=""),
            sa.Column("state", sa.String(length=20), nullable=False, server_default="draft"),
            sa.Column("views", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("author", sa.String(length=120), nullable=False, server_default=""),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("slug", name="uq_support_kb_articles_slug"),
        )
        op.create_index("ix_support_kb_articles_slug", "support_kb_articles", ["slug"])
        op.create_index("ix_support_kb_articles_state", "support_kb_articles", ["state"])
        op.create_index("ix_support_kb_articles_kind", "support_kb_articles", ["kind"])

    if "support_help_links" not in tables:
        op.create_table(
            "support_help_links",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("title", sa.String(length=200), nullable=False),
            sa.Column("url", sa.String(length=500), nullable=False),
            sa.Column("category", sa.String(length=120), nullable=False, server_default=""),
            sa.Column("description", sa.Text(), nullable=False, server_default=""),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )

    if "support_sla_settings" not in tables:
        op.create_table(
            "support_sla_settings",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("first_response_hours", sa.Integer(), nullable=False, server_default="4"),
            sa.Column("resolve_hours", sa.Integer(), nullable=False, server_default="48"),
            sa.Column("waiting_hours", sa.Integer(), nullable=False, server_default="24"),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )


def downgrade() -> None:
    tables = _tables()
    for table in (
        "support_sla_settings",
        "support_help_links",
        "support_kb_articles",
        "support_kb_categories",
    ):
        if table in tables:
            op.drop_table(table)
    if "faq_items" in tables and "surface" in _columns("faq_items"):
        op.drop_column("faq_items", "surface")
    if "faq_categories" in tables and "surface" in _columns("faq_categories"):
        op.drop_column("faq_categories", "surface")
    if "support_tickets" in tables and "channel" in _columns("support_tickets"):
        op.drop_column("support_tickets", "channel")
