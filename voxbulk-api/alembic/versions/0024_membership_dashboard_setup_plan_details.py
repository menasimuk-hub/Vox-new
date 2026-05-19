"""membership dashboard setup + plan marketing fields

Revision ID: 0024_membership_dashboard_setup_plan_details
Revises: 0023_repair_organisations_schema_drift
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0024_membership_dashboard_setup_plan_details"
down_revision = "0023_repair_organisations_schema_drift"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "organisation_memberships",
        sa.Column("dashboard_setup_completed_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "organisation_memberships",
        sa.Column("dashboard_setup_profile_json", sa.Text(), nullable=True),
    )
    op.add_column("plans", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("plans", sa.Column("features_json", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("plans", "features_json")
    op.drop_column("plans", "description")
    op.drop_column("organisation_memberships", "dashboard_setup_profile_json")
    op.drop_column("organisation_memberships", "dashboard_setup_completed_at")
