"""Organisation enabled dashboard services JSON.

Revision ID: 0073_org_enabled_services
Revises: 0072_interview_ats_score
"""

from alembic import op
import sqlalchemy as sa

revision = "0073_org_enabled_services"
down_revision = "0072_interview_ats_score"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "organisations",
        sa.Column("enabled_services_json", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("organisations", "enabled_services_json")
