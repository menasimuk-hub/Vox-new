"""Support content linked_service + seed keys for product-aware defaults.

Revision ID: 0231_support_content_product_keys
Revises: 0230_platform_product_visibility
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0231_support_content_product_keys"
down_revision = "0230_platform_product_visibility"
branch_labels = None
depends_on = None


def _table_exists(name: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return name in insp.get_table_names()


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if table not in insp.get_table_names():
        return False
    return any(c["name"] == column for c in insp.get_columns(table))


def _add_col(table: str, column: sa.Column) -> None:
    if _table_exists(table) and not _column_exists(table, column.name):
        op.add_column(table, column)


def upgrade() -> None:
    _add_col(
        "support_canned_reply_categories",
        sa.Column("slug", sa.String(length=120), nullable=True),
    )
    _add_col(
        "support_canned_reply_categories",
        sa.Column("linked_service", sa.String(length=64), nullable=True),
    )
    _add_col(
        "support_canned_replies",
        sa.Column("seed_key", sa.String(length=120), nullable=True),
    )
    _add_col(
        "support_canned_replies",
        sa.Column("linked_service", sa.String(length=64), nullable=True),
    )
    _add_col(
        "support_kb_categories",
        sa.Column("slug", sa.String(length=120), nullable=True),
    )
    _add_col(
        "support_kb_categories",
        sa.Column("linked_service", sa.String(length=64), nullable=True),
    )
    _add_col(
        "support_kb_articles",
        sa.Column("linked_service", sa.String(length=64), nullable=True),
    )
    _add_col(
        "support_help_links",
        sa.Column("seed_key", sa.String(length=120), nullable=True),
    )
    _add_col(
        "support_help_links",
        sa.Column("linked_service", sa.String(length=64), nullable=True),
    )

    # Indexes / uniqueness for stable seed keys (nullable — only seeded rows set them).
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing_ix = {ix["name"] for ix in insp.get_indexes("support_canned_replies")} if _table_exists("support_canned_replies") else set()
    if "uq_support_canned_replies_seed_key" not in existing_ix and _column_exists("support_canned_replies", "seed_key"):
        op.create_index(
            "uq_support_canned_replies_seed_key",
            "support_canned_replies",
            ["seed_key"],
            unique=True,
        )
    existing_ix_hl = {ix["name"] for ix in insp.get_indexes("support_help_links")} if _table_exists("support_help_links") else set()
    if "uq_support_help_links_seed_key" not in existing_ix_hl and _column_exists("support_help_links", "seed_key"):
        op.create_index(
            "uq_support_help_links_seed_key",
            "support_help_links",
            ["seed_key"],
            unique=True,
        )
    for table, cols in (
        ("support_canned_reply_categories", ["slug", "linked_service"]),
        ("support_canned_replies", ["linked_service"]),
        ("support_kb_categories", ["slug", "linked_service"]),
        ("support_kb_articles", ["linked_service"]),
        ("support_help_links", ["linked_service"]),
    ):
        if not _table_exists(table):
            continue
        ix_names = {ix["name"] for ix in insp.get_indexes(table)}
        for col in cols:
            if not _column_exists(table, col):
                continue
            ix_name = f"ix_{table}_{col}"
            if ix_name not in ix_names:
                op.create_index(ix_name, table, [col])


def downgrade() -> None:
    for table, ix in (
        ("support_help_links", "uq_support_help_links_seed_key"),
        ("support_canned_replies", "uq_support_canned_replies_seed_key"),
    ):
        if _table_exists(table):
            try:
                op.drop_index(ix, table_name=table)
            except Exception:
                pass
    for table, cols in (
        ("support_help_links", ["seed_key", "linked_service"]),
        ("support_kb_articles", ["linked_service"]),
        ("support_kb_categories", ["slug", "linked_service"]),
        ("support_canned_replies", ["seed_key", "linked_service"]),
        ("support_canned_reply_categories", ["slug", "linked_service"]),
    ):
        if not _table_exists(table):
            continue
        for col in cols:
            if _column_exists(table, col):
                op.drop_column(table, col)
