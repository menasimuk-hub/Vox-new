"""Alembic migration: store Breezy HR API token + company per organisation."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0178_breezy_hr_config"
down_revision = "0177_integration_release_testers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "organisations",
        sa.Column("breezy_hr_config_json", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("organisations", "breezy_hr_config_json")
