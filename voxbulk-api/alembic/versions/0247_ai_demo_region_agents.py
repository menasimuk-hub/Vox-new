"""0247 — AI demo per-region Telnyx agent map.

Revision ID: 0247_ai_demo_region_agents
Revises: 0246_user_email_preferences
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0247_ai_demo_region_agents"
down_revision = "0246_user_email_preferences"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if table not in insp.get_table_names():
        return False
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    if not _has_column("demo_platform_settings", "agent_by_region_json"):
        op.add_column(
            "demo_platform_settings",
            sa.Column("agent_by_region_json", sa.Text(), nullable=True),
        )


def downgrade() -> None:
    if _has_column("demo_platform_settings", "agent_by_region_json"):
        op.drop_column("demo_platform_settings", "agent_by_region_json")
