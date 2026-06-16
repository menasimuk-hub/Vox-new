"""Menu intelligence — structured tags, allergens, recipe metadata."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0014_abuu_menu_intelligence"
down_revision = "0013_abuu_session_context_mediumtext"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("abuu_menu_items", sa.Column("subcategory", sa.String(length=64), nullable=True))
    op.add_column("abuu_menu_items", sa.Column("short_description_en", sa.Text(), nullable=True))
    op.add_column("abuu_menu_items", sa.Column("short_description_ar", sa.Text(), nullable=True))
    op.add_column("abuu_menu_items", sa.Column("offer_type", sa.String(length=32), nullable=True))
    op.add_column("abuu_menu_items", sa.Column("spice_level", sa.String(length=16), nullable=True))
    op.add_column(
        "abuu_menu_items",
        sa.Column("classification_status", sa.String(length=16), nullable=False, server_default="unclassified"),
    )
    op.add_column("abuu_menu_items", sa.Column("ingredients_json", sa.Text(), nullable=True))
    op.add_column("abuu_menu_items", sa.Column("allergen_tags_json", sa.Text(), nullable=True))
    op.add_column("abuu_menu_items", sa.Column("dietary_tags_json", sa.Text(), nullable=True))
    op.add_column("abuu_menu_items", sa.Column("recipe_tags_json", sa.Text(), nullable=True))
    op.add_column("abuu_menu_items", sa.Column("protein_tags_json", sa.Text(), nullable=True))
    op.add_column("abuu_menu_items", sa.Column("cuisine_tags_json", sa.Text(), nullable=True))
    op.add_column("abuu_menu_items", sa.Column("drink_tags_json", sa.Text(), nullable=True))
    op.add_column("abuu_menu_items", sa.Column("upsell_tags_json", sa.Text(), nullable=True))
    op.add_column("abuu_menu_items", sa.Column("metadata_json", sa.Text(), nullable=True))
    op.add_column("abuu_menu_categories", sa.Column("category_kind", sa.String(length=32), nullable=True))
    op.add_column("abuu_orders", sa.Column("allergy_note", sa.Text(), nullable=True))
    op.add_column("abuu_customers", sa.Column("dietary_json", sa.Text(), nullable=True))
    op.add_column("abuu_customers", sa.Column("allergens_json", sa.Text(), nullable=True))
    op.create_index("ix_abuu_menu_items_classification", "abuu_menu_items", ["classification_status"])


def downgrade() -> None:
    op.drop_index("ix_abuu_menu_items_classification", table_name="abuu_menu_items")
    op.drop_column("abuu_customers", "allergens_json")
    op.drop_column("abuu_customers", "dietary_json")
    op.drop_column("abuu_orders", "allergy_note")
    op.drop_column("abuu_menu_categories", "category_kind")
    for col in (
        "metadata_json",
        "upsell_tags_json",
        "drink_tags_json",
        "cuisine_tags_json",
        "protein_tags_json",
        "recipe_tags_json",
        "dietary_tags_json",
        "allergen_tags_json",
        "ingredients_json",
        "classification_status",
        "spice_level",
        "offer_type",
        "short_description_ar",
        "short_description_en",
        "subcategory",
    ):
        op.drop_column("abuu_menu_items", col)
