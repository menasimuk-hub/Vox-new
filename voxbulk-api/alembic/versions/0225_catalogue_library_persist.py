"""Org catalogue library persistence + Smart Card colour/freeze metadata."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0225_catalogue_library_persist"
down_revision = "0224_voxbox_message_mediumtext"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "smart_card_categories",
        sa.Column("accent_color", sa.String(length=32), nullable=False, server_default="sky"),
    )
    op.add_column(
        "smart_card_categories",
        sa.Column("is_frozen", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "smart_card_products",
        sa.Column("is_frozen", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("smart_card_assets", sa.Column("original_filename", sa.String(length=255), nullable=True))
    op.add_column("smart_card_assets", sa.Column("file_size_bytes", sa.Integer(), nullable=True))

    op.create_table(
        "expo_library_categories",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("accent_color", sa.String(length=32), nullable=False),
        sa.Column("is_frozen", sa.Boolean(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["organisations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_expo_library_categories_org_id", "expo_library_categories", ["org_id"])

    op.create_table(
        "expo_library_products",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("category_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("short_description", sa.Text(), nullable=True),
        sa.Column("is_frozen", sa.Boolean(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["category_id"], ["expo_library_categories.id"]),
        sa.ForeignKeyConstraint(["org_id"], ["organisations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_expo_library_products_org_id", "expo_library_products", ["org_id"])
    op.create_index("ix_expo_library_products_category_id", "expo_library_products", ["category_id"])

    op.create_table(
        "expo_library_assets",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("product_id", sa.String(length=36), nullable=True),
        sa.Column("category_id", sa.String(length=36), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("purpose", sa.String(length=32), nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=True),
        sa.Column("external_url", sa.Text(), nullable=True),
        sa.Column("original_filename", sa.String(length=255), nullable=True),
        sa.Column("file_size_bytes", sa.Integer(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["category_id"], ["expo_library_categories.id"]),
        sa.ForeignKeyConstraint(["org_id"], ["organisations.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["expo_library_products.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_expo_library_assets_org_id", "expo_library_assets", ["org_id"])
    op.create_index("ix_expo_library_assets_product_id", "expo_library_assets", ["product_id"])
    op.create_index("ix_expo_library_assets_category_id", "expo_library_assets", ["category_id"])


def downgrade() -> None:
    op.drop_table("expo_library_assets")
    op.drop_table("expo_library_products")
    op.drop_table("expo_library_categories")
    op.drop_column("smart_card_assets", "file_size_bytes")
    op.drop_column("smart_card_assets", "original_filename")
    op.drop_column("smart_card_products", "is_frozen")
    op.drop_column("smart_card_categories", "is_frozen")
    op.drop_column("smart_card_categories", "accent_color")
