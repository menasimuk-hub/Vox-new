"""add Dentally external ids

Revision ID: 0009_add_dentally_external_ids
Revises: 0008_twilio_provider_fields
Create Date: 2026-05-05
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0009_add_dentally_external_ids"
down_revision = "0008_twilio_provider_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("branches", sa.Column("dentally_id", sa.String(length=100), nullable=True))
    op.create_index("ix_branches_dentally_id", "branches", ["dentally_id"], unique=False)

    op.add_column("patients", sa.Column("dentally_id", sa.String(length=100), nullable=True))
    op.create_index("ix_patients_dentally_id", "patients", ["dentally_id"], unique=False)

    op.add_column("appointments", sa.Column("dentally_id", sa.String(length=100), nullable=True))
    op.create_index("ix_appointments_dentally_id", "appointments", ["dentally_id"], unique=False)

    # Tenant-safe uniqueness where Dentally IDs exist
    op.create_unique_constraint("uq_branches_org_dentally_id", "branches", ["org_id", "dentally_id"])
    op.create_unique_constraint("uq_patients_org_dentally_id", "patients", ["org_id", "dentally_id"])
    op.create_unique_constraint("uq_appointments_org_dentally_id", "appointments", ["org_id", "dentally_id"])


def downgrade() -> None:
    op.drop_constraint("uq_appointments_org_dentally_id", "appointments", type_="unique")
    op.drop_constraint("uq_patients_org_dentally_id", "patients", type_="unique")
    op.drop_constraint("uq_branches_org_dentally_id", "branches", type_="unique")

    op.drop_index("ix_appointments_dentally_id", table_name="appointments")
    op.drop_column("appointments", "dentally_id")

    op.drop_index("ix_patients_dentally_id", table_name="patients")
    op.drop_column("patients", "dentally_id")

    op.drop_index("ix_branches_dentally_id", table_name="branches")
    op.drop_column("branches", "dentally_id")

