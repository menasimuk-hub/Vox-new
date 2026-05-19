"""add appointments.treatment_label

Revision ID: 0013_add_appointment_treatment_label
Revises: 0012_add_appointment_value_gbp_pence
Create Date: 2026-05-05
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0013_add_appointment_treatment_label"
down_revision = "0012_add_appointment_value_gbp_pence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("appointments", sa.Column("treatment_label", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("appointments", "treatment_label")

