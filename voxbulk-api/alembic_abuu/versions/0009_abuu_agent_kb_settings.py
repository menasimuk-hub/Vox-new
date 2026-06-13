"""Abuu agent KB and restaurant policy settings."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0009_abuu_agent_kb_settings"
down_revision = "0008_abuu_voice_personalization"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "abuu_agent_settings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("business_name_en", sa.String(length=255), nullable=True),
        sa.Column("business_name_ar", sa.String(length=255), nullable=True),
        sa.Column("opening_hours_json", sa.Text(), nullable=True),
        sa.Column("delivery_hours_json", sa.Text(), nullable=True),
        sa.Column("default_delivery_radius_km", sa.Float(), nullable=True),
        sa.Column("default_prep_minutes", sa.Integer(), nullable=True),
        sa.Column("default_min_order_agorot", sa.Integer(), nullable=True),
        sa.Column("default_delivery_fee_agorot", sa.Integer(), nullable=True),
        sa.Column("payment_methods_json", sa.Text(), nullable=True),
        sa.Column("refund_policy_en", sa.Text(), nullable=True),
        sa.Column("refund_policy_ar", sa.Text(), nullable=True),
        sa.Column("cancellation_policy_en", sa.Text(), nullable=True),
        sa.Column("cancellation_policy_ar", sa.Text(), nullable=True),
        sa.Column("allergen_disclaimer_en", sa.Text(), nullable=True),
        sa.Column("allergen_disclaimer_ar", sa.Text(), nullable=True),
        sa.Column("escalation_rules_en", sa.Text(), nullable=True),
        sa.Column("escalation_rules_ar", sa.Text(), nullable=True),
        sa.Column("greeting_template_en", sa.Text(), nullable=True),
        sa.Column("greeting_template_ar", sa.Text(), nullable=True),
        sa.Column("holiday_closures_json", sa.Text(), nullable=True),
        sa.Column("skills_config_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "abuu_restaurant_settings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("restaurant_id", sa.String(length=36), nullable=False),
        sa.Column("notes_en", sa.Text(), nullable=True),
        sa.Column("notes_ar", sa.Text(), nullable=True),
        sa.Column("opening_hours_json", sa.Text(), nullable=True),
        sa.Column("delivery_hours_json", sa.Text(), nullable=True),
        sa.Column("delivery_radius_km", sa.Float(), nullable=True),
        sa.Column("prep_minutes", sa.Integer(), nullable=True),
        sa.Column("min_order_agorot", sa.Integer(), nullable=True),
        sa.Column("delivery_fee_agorot", sa.Integer(), nullable=True),
        sa.Column("payment_methods_json", sa.Text(), nullable=True),
        sa.Column("refund_policy_en", sa.Text(), nullable=True),
        sa.Column("refund_policy_ar", sa.Text(), nullable=True),
        sa.Column("cancellation_policy_en", sa.Text(), nullable=True),
        sa.Column("cancellation_policy_ar", sa.Text(), nullable=True),
        sa.Column("allergen_disclaimer_en", sa.Text(), nullable=True),
        sa.Column("allergen_disclaimer_ar", sa.Text(), nullable=True),
        sa.Column("escalation_rules_en", sa.Text(), nullable=True),
        sa.Column("escalation_rules_ar", sa.Text(), nullable=True),
        sa.Column("greeting_template_en", sa.Text(), nullable=True),
        sa.Column("greeting_template_ar", sa.Text(), nullable=True),
        sa.Column("holiday_closures_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["restaurant_id"], ["abuu_restaurants.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("restaurant_id", name="uq_abuu_restaurant_settings_restaurant"),
    )
    op.create_index("ix_abuu_restaurant_settings_restaurant_id", "abuu_restaurant_settings", ["restaurant_id"])

    from app.abuu.services.agent_settings_seed import seed_agent_settings
    from app.core.abuu_database import get_abuu_sessionmaker

    with get_abuu_sessionmaker()() as db:
        seed_agent_settings(db)
        db.commit()


def downgrade() -> None:
    op.drop_index("ix_abuu_restaurant_settings_restaurant_id", table_name="abuu_restaurant_settings")
    op.drop_table("abuu_restaurant_settings")
    op.drop_table("abuu_agent_settings")
