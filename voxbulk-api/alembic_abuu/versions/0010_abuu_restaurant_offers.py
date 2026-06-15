"""Abuu restaurant promo offers table."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0010_abuu_restaurant_offers"
down_revision = "0009_abuu_agent_kb_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "abuu_restaurant_offers",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("restaurant_id", sa.String(length=36), nullable=False),
        sa.Column("title_en", sa.String(length=255), nullable=False),
        sa.Column("title_ar", sa.String(length=255), nullable=False),
        sa.Column("description_en", sa.Text(), nullable=True),
        sa.Column("description_ar", sa.Text(), nullable=True),
        sa.Column("offer_price_agorot", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("original_price_agorot", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("items_json", sa.Text(), nullable=True),
        sa.Column("tags_json", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["restaurant_id"], ["abuu_restaurants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_abuu_restaurant_offers_restaurant_id", "abuu_restaurant_offers", ["restaurant_id"])

    from app.abuu.services.seed_service import AbuuSeedService
    from app.core.abuu_database import get_abuu_sessionmaker

    with get_abuu_sessionmaker()() as db:
        AbuuSeedService.seed_offers_if_empty(db)
        db.commit()


def downgrade() -> None:
    op.drop_index("ix_abuu_restaurant_offers_restaurant_id", table_name="abuu_restaurant_offers")
    op.drop_table("abuu_restaurant_offers")
