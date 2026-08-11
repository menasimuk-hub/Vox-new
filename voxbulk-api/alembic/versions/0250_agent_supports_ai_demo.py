"""Add supports_ai_demo / is_default_ai_demo; backfill AI Demo clones.

Revision ID: 0250_agent_supports_ai_demo
Revises: 0249_sales_consent_ops
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0250_agent_supports_ai_demo"
down_revision = "0249_sales_consent_ops"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return any(c["name"] == column for c in insp.get_columns(table))


def upgrade() -> None:
    if not _has_column("agent_definitions", "supports_ai_demo"):
        op.add_column(
            "agent_definitions",
            sa.Column("supports_ai_demo", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        )
    if not _has_column("agent_definitions", "is_default_ai_demo"):
        op.add_column(
            "agent_definitions",
            sa.Column("is_default_ai_demo", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        )

    conn = op.get_bind()
    # Existing dedicated demo clones (slug/name convention from duplicate_region_agents_for_demo)
    conn.execute(
        sa.text(
            """
            UPDATE agent_definitions
            SET supports_ai_demo = 1,
                supports_interview = 0,
                supports_survey = 0,
                is_default_interview = 0,
                is_default_survey = 0
            WHERE slug LIKE 'ai-demo-%'
               OR name LIKE 'AI Demo%'
            """
        )
    )


def downgrade() -> None:
    if _has_column("agent_definitions", "is_default_ai_demo"):
        op.drop_column("agent_definitions", "is_default_ai_demo")
    if _has_column("agent_definitions", "supports_ai_demo"):
        op.drop_column("agent_definitions", "supports_ai_demo")
