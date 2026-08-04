"""Org catalogue library persistence + Smart Card colour/freeze metadata.

MySQL note: FK to organisations.id must match that column's charset/collation
(error 3780 otherwise). Idempotent for partial failed runs.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0225_catalogue_library_persist"
down_revision = "0224_voxbox_message_mediumtext"
branch_labels = None
depends_on = None


def _has_table(table: str) -> bool:
    bind = op.get_bind()
    return table in sa.inspect(bind).get_table_names()


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if table not in insp.get_table_names():
        return False
    return column in {c["name"] for c in insp.get_columns(table)}


def _column_collation(table: str, column: str) -> str | None:
    bind = op.get_bind()
    try:
        return bind.execute(
            sa.text(
                "SELECT COLLATION_NAME FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE() "
                "AND TABLE_NAME = :table AND COLUMN_NAME = :column "
                "LIMIT 1"
            ),
            {"table": table, "column": column},
        ).scalar()
    except Exception:
        return None


def _id_type(collation: str | None) -> sa.String:
    return sa.String(36, collation=collation) if collation else sa.String(36)


def _table_kwargs(collation: str | None) -> dict:
    if not collation:
        return {}
    return {"mysql_charset": "utf8mb4", "mysql_collate": collation}


def upgrade() -> None:
    if _has_table("smart_card_categories"):
        if not _has_column("smart_card_categories", "accent_color"):
            op.add_column(
                "smart_card_categories",
                sa.Column("accent_color", sa.String(length=32), nullable=False, server_default="sky"),
            )
        if not _has_column("smart_card_categories", "is_frozen"):
            op.add_column(
                "smart_card_categories",
                sa.Column("is_frozen", sa.Boolean(), nullable=False, server_default=sa.text("0")),
            )
    if _has_table("smart_card_products") and not _has_column("smart_card_products", "is_frozen"):
        op.add_column(
            "smart_card_products",
            sa.Column("is_frozen", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        )
    if _has_table("smart_card_assets"):
        if not _has_column("smart_card_assets", "original_filename"):
            op.add_column(
                "smart_card_assets",
                sa.Column("original_filename", sa.String(length=255), nullable=True),
            )
        if not _has_column("smart_card_assets", "file_size_bytes"):
            op.add_column(
                "smart_card_assets",
                sa.Column("file_size_bytes", sa.Integer(), nullable=True),
            )

    # Match organisations.id so MySQL accepts FKs (error 3780).
    org_collation = _column_collation("organisations", "id")
    id_col = _id_type(org_collation)
    table_kwargs = _table_kwargs(org_collation)

    if not _has_table("expo_library_categories"):
        op.create_table(
            "expo_library_categories",
            sa.Column("id", id_col, nullable=False),
            sa.Column("org_id", id_col, nullable=False),
            sa.Column("name", sa.String(length=128), nullable=False),
            sa.Column("accent_color", sa.String(length=32), nullable=False, server_default="sky"),
            sa.Column("is_frozen", sa.Boolean(), nullable=False, server_default=sa.text("0")),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="100"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["org_id"], ["organisations.id"], name="fk_expo_library_categories_org_id"),
            sa.PrimaryKeyConstraint("id"),
            **table_kwargs,
        )
        op.create_index("ix_expo_library_categories_org_id", "expo_library_categories", ["org_id"])

    # Child tables must match parent category id collation too.
    cat_collation = _column_collation("expo_library_categories", "id") or org_collation
    cat_id = _id_type(cat_collation)
    child_kwargs = _table_kwargs(cat_collation)

    if not _has_table("expo_library_products"):
        op.create_table(
            "expo_library_products",
            sa.Column("id", cat_id, nullable=False),
            sa.Column("org_id", cat_id, nullable=False),
            sa.Column("category_id", cat_id, nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("short_description", sa.Text(), nullable=True),
            sa.Column("is_frozen", sa.Boolean(), nullable=False, server_default=sa.text("0")),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="100"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(
                ["category_id"], ["expo_library_categories.id"], name="fk_expo_library_products_category_id"
            ),
            sa.ForeignKeyConstraint(["org_id"], ["organisations.id"], name="fk_expo_library_products_org_id"),
            sa.PrimaryKeyConstraint("id"),
            **child_kwargs,
        )
        op.create_index("ix_expo_library_products_org_id", "expo_library_products", ["org_id"])
        op.create_index("ix_expo_library_products_category_id", "expo_library_products", ["category_id"])

    prod_collation = _column_collation("expo_library_products", "id") or cat_collation
    prod_id = _id_type(prod_collation)
    asset_kwargs = _table_kwargs(prod_collation)

    if not _has_table("expo_library_assets"):
        op.create_table(
            "expo_library_assets",
            sa.Column("id", prod_id, nullable=False),
            sa.Column("org_id", prod_id, nullable=False),
            sa.Column("product_id", prod_id, nullable=True),
            sa.Column("category_id", prod_id, nullable=True),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("kind", sa.String(length=16), nullable=False, server_default="pdf"),
            sa.Column("purpose", sa.String(length=32), nullable=False, server_default="catalogue"),
            sa.Column("storage_path", sa.Text(), nullable=True),
            sa.Column("external_url", sa.Text(), nullable=True),
            sa.Column("original_filename", sa.String(length=255), nullable=True),
            sa.Column("file_size_bytes", sa.Integer(), nullable=True),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="100"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(
                ["category_id"], ["expo_library_categories.id"], name="fk_expo_library_assets_category_id"
            ),
            sa.ForeignKeyConstraint(["org_id"], ["organisations.id"], name="fk_expo_library_assets_org_id"),
            sa.ForeignKeyConstraint(
                ["product_id"], ["expo_library_products.id"], name="fk_expo_library_assets_product_id"
            ),
            sa.PrimaryKeyConstraint("id"),
            **asset_kwargs,
        )
        op.create_index("ix_expo_library_assets_org_id", "expo_library_assets", ["org_id"])
        op.create_index("ix_expo_library_assets_product_id", "expo_library_assets", ["product_id"])
        op.create_index("ix_expo_library_assets_category_id", "expo_library_assets", ["category_id"])


def downgrade() -> None:
    if _has_table("expo_library_assets"):
        op.drop_table("expo_library_assets")
    if _has_table("expo_library_products"):
        op.drop_table("expo_library_products")
    if _has_table("expo_library_categories"):
        op.drop_table("expo_library_categories")
    if _has_column("smart_card_assets", "file_size_bytes"):
        op.drop_column("smart_card_assets", "file_size_bytes")
    if _has_column("smart_card_assets", "original_filename"):
        op.drop_column("smart_card_assets", "original_filename")
    if _has_column("smart_card_products", "is_frozen"):
        op.drop_column("smart_card_products", "is_frozen")
    if _has_column("smart_card_categories", "is_frozen"):
        op.drop_column("smart_card_categories", "is_frozen")
    if _has_column("smart_card_categories", "accent_color"):
        op.drop_column("smart_card_categories", "accent_color")
