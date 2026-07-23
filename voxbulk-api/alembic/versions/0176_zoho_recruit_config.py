"""Alembic migration: store Zoho Recruit OAuth tokens per organisation."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0176_zoho_recruit_config"
down_revision = "0175_partner_marketplace"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "organisations",
        sa.Column("zoho_recruit_config_json", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("organisations", "zoho_recruit_config_json")
