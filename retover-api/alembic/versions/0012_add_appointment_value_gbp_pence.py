"""add appointments.value_gbp_pence

Revision ID: 0012_add_appointment_value_gbp_pence
Revises: 0011_add_provider_configs
Create Date: 2026-05-05
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0012_add_appointment_value_gbp_pence"
down_revision = "0011_add_provider_configs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("appointments", sa.Column("value_gbp_pence", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("appointments", "value_gbp_pence")

