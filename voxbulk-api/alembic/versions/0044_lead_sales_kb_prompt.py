"""Lead sales KB and master system prompt on settings."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0044_lead_sales_kb_prompt"
down_revision = "0043_lead_sales_calling_hours"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("lead_sales_settings", sa.Column("system_prompt", sa.Text(), nullable=True))
    op.add_column("lead_sales_settings", sa.Column("kb_file_ids", sa.Text(), nullable=True))
    op.add_column("lead_sales_settings", sa.Column("kb_context", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("lead_sales_settings", "kb_context")
    op.drop_column("lead_sales_settings", "kb_file_ids")
    op.drop_column("lead_sales_settings", "system_prompt")
