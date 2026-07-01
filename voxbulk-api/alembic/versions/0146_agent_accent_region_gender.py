"""agent accent_region and gender for interview voice picker

Revision ID: 0146_agent_accent_region_gender
Revises: 0145_sales_rep_promo_wallet
"""

from alembic import op
import sqlalchemy as sa

revision = "0146_agent_accent_region_gender"
down_revision = "0145_sales_rep_promo_wallet"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agent_definitions", sa.Column("accent_region", sa.String(length=8), nullable=True))
    op.add_column("agent_definitions", sa.Column("gender", sa.String(length=16), nullable=True))
    op.create_index("ix_agent_definitions_accent_region", "agent_definitions", ["accent_region"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_agent_definitions_accent_region", table_name="agent_definitions")
    op.drop_column("agent_definitions", "gender")
    op.drop_column("agent_definitions", "accent_region")
