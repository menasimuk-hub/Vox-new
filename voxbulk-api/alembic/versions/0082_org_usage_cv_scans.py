"""Add cv_scans usage columns to org_usage_periods.

Revision ID: 0082_org_usage_cv_scans
Revises: 0081_org_hubspot_config
"""

from alembic import op
import sqlalchemy as sa

revision = "0082_org_usage_cv_scans"
down_revision = "0081_org_hubspot_config"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c["name"] for c in insp.get_columns("org_usage_periods")}
    if "cv_scans_included" not in cols:
        op.add_column(
            "org_usage_periods",
            sa.Column("cv_scans_included", sa.Integer(), nullable=False, server_default="0"),
        )
    if "cv_scans_used" not in cols:
        op.add_column(
            "org_usage_periods",
            sa.Column("cv_scans_used", sa.Integer(), nullable=False, server_default="0"),
        )


def downgrade() -> None:
    op.drop_column("org_usage_periods", "cv_scans_used")
    op.drop_column("org_usage_periods", "cv_scans_included")
