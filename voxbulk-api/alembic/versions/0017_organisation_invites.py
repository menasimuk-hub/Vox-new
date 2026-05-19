"""organisation invites for admin-driven signup

Revision ID: 0017_organisation_invites
Revises: 0016_org_suspended_profile_notes
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0017_organisation_invites"
down_revision = "0016_org_suspended_profile_notes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "organisation_invites",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("org_id", sa.String(length=36), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("role", sa.String(length=50), nullable=True),
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("consumed_at", sa.DateTime(), nullable=True),
    )
    op.create_unique_constraint("uq_organisation_invites_token", "organisation_invites", ["token"])
    op.create_index("ix_organisation_invites_email", "organisation_invites", ["email"], unique=False)
    op.create_index("ix_organisation_invites_org_id", "organisation_invites", ["org_id"], unique=False)
    op.create_index("ix_organisation_invites_token", "organisation_invites", ["token"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_organisation_invites_token", table_name="organisation_invites")
    op.drop_index("ix_organisation_invites_org_id", table_name="organisation_invites")
    op.drop_index("ix_organisation_invites_email", table_name="organisation_invites")
    op.drop_constraint("uq_organisation_invites_token", "organisation_invites", type_="unique")
    op.drop_table("organisation_invites")
