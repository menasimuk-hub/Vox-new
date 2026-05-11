"""add organisation_memberships.role

Revision ID: 0014_add_membership_role
Revises: 0013_add_appointment_treatment_label
Create Date: 2026-05-05
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0014_add_membership_role"
down_revision = "0013_add_appointment_treatment_label"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("organisation_memberships", sa.Column("role", sa.String(length=50), nullable=True))
    op.create_index("ix_organisation_memberships_role", "organisation_memberships", ["role"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_organisation_memberships_role", table_name="organisation_memberships")
    op.drop_column("organisation_memberships", "role")

