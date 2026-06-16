"""Gaza Agent — WA snapshot cache + market agent registry."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0012_abuu_gaza_agent_snapshots"
down_revision = "0011_abuu_order_substitution"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "abuu_wa_snapshots",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("scope", sa.String(length=128), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("lang", sa.String(length=8), nullable=False),
        sa.Column("body_text", sa.Text(), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("scope", "kind", "lang", name="uq_abuu_wa_snapshots_scope_kind_lang"),
    )
    op.create_index("ix_abuu_wa_snapshots_scope", "abuu_wa_snapshots", ["scope"])

    op.create_table(
        "abuu_market_agents",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("country_code", sa.String(length=8), nullable=False),
        sa.Column("city_slug", sa.String(length=64), nullable=False),
        sa.Column("display_name_en", sa.String(length=255), nullable=False),
        sa.Column("display_name_ar", sa.String(length=255), nullable=False),
        sa.Column("dialect_prompt", sa.Text(), nullable=True),
        sa.Column("llm_provider", sa.String(length=32), nullable=False, server_default="deepseek"),
        sa.Column("llm_model", sa.String(length=128), nullable=False, server_default="deepseek-chat"),
        sa.Column("pilot_restaurant_ids_json", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )

    op.add_column("abuu_restaurants", sa.Column("country_code", sa.String(length=8), nullable=True))
    op.add_column("abuu_restaurants", sa.Column("city_slug", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("abuu_restaurants", "city_slug")
    op.drop_column("abuu_restaurants", "country_code")
    op.drop_table("abuu_market_agents")
    op.drop_index("ix_abuu_wa_snapshots_scope", table_name="abuu_wa_snapshots")
    op.drop_table("abuu_wa_snapshots")
