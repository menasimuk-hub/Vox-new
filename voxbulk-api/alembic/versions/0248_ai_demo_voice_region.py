"""0248 — AI demo request voice region override (admin pick on send).

Revision ID: 0248_ai_demo_voice_region
Revises: 0247_ai_demo_region_agents
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0248_ai_demo_voice_region"
down_revision = "0247_ai_demo_region_agents"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if table not in insp.get_table_names():
        return False
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    if not _has_column("demo_requests", "voice_region"):
        op.add_column(
            "demo_requests",
            sa.Column("voice_region", sa.String(length=10), nullable=True),
        )


def downgrade() -> None:
    if _has_column("demo_requests", "voice_region"):
        op.drop_column("demo_requests", "voice_region")
