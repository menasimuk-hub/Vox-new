"""Expo categories, products, reps, max_categories.

Revision ID: 0192_expo_categories_reps
Revises: 0191_expo_signup_company_trial
Create Date: 2026-07-26
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0192_expo_categories_reps"
down_revision = "0191_expo_signup_company_trial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("expo_packages", sa.Column("max_categories", sa.Integer(), nullable=True))
    op.execute("UPDATE expo_packages SET max_categories = 1 WHERE tier = 'day1' OR duration_days = 1")
    op.execute("UPDATE expo_packages SET max_categories = 3 WHERE tier = 'day3' OR duration_days = 3")
    op.execute(
        "UPDATE expo_packages SET max_categories = NULL WHERE tier = 'day7' OR duration_days >= 7"
    )

    op.add_column("expo_booths", sa.Column("representative_contacts_json", sa.Text(), nullable=True))
    op.add_column("expo_booths", sa.Column("company_website", sa.String(length=512), nullable=True))
    op.add_column("expo_booths", sa.Column("notify_mobile", sa.String(length=64), nullable=True))

    op.create_table(
        "expo_booth_categories",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("booth_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("accent_color", sa.String(length=32), nullable=False, server_default="#E8F0FE"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["booth_id"], ["expo_booths.id"]),
        sa.ForeignKeyConstraint(["org_id"], ["organisations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_expo_booth_categories_org_id", "expo_booth_categories", ["org_id"])
    op.create_index("ix_expo_booth_categories_booth_id", "expo_booth_categories", ["booth_id"])

    op.create_table(
        "expo_booth_products",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("booth_id", sa.String(length=36), nullable=False),
        sa.Column("category_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("short_description", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["booth_id"], ["expo_booths.id"]),
        sa.ForeignKeyConstraint(["category_id"], ["expo_booth_categories.id"]),
        sa.ForeignKeyConstraint(["org_id"], ["organisations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_expo_booth_products_org_id", "expo_booth_products", ["org_id"])
    op.create_index("ix_expo_booth_products_booth_id", "expo_booth_products", ["booth_id"])
    op.create_index("ix_expo_booth_products_category_id", "expo_booth_products", ["category_id"])

    op.add_column(
        "expo_booth_assets",
        sa.Column("product_id", sa.String(length=36), nullable=True),
    )
    op.create_foreign_key(
        "fk_expo_booth_assets_product_id",
        "expo_booth_assets",
        "expo_booth_products",
        ["product_id"],
        ["id"],
    )
    op.create_index("ix_expo_booth_assets_product_id", "expo_booth_assets", ["product_id"])


def downgrade() -> None:
    op.drop_index("ix_expo_booth_assets_product_id", table_name="expo_booth_assets")
    op.drop_constraint("fk_expo_booth_assets_product_id", "expo_booth_assets", type_="foreignkey")
    op.drop_column("expo_booth_assets", "product_id")

    op.drop_index("ix_expo_booth_products_category_id", table_name="expo_booth_products")
    op.drop_index("ix_expo_booth_products_booth_id", table_name="expo_booth_products")
    op.drop_index("ix_expo_booth_products_org_id", table_name="expo_booth_products")
    op.drop_table("expo_booth_products")

    op.drop_index("ix_expo_booth_categories_booth_id", table_name="expo_booth_categories")
    op.drop_index("ix_expo_booth_categories_org_id", table_name="expo_booth_categories")
    op.drop_table("expo_booth_categories")

    op.drop_column("expo_booths", "notify_mobile")
    op.drop_column("expo_booths", "company_website")
    op.drop_column("expo_booths", "representative_contacts_json")
    op.drop_column("expo_packages", "max_categories")
