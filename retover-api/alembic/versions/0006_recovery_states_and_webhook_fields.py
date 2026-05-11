"""add appointment recovery state fields + webhook event fields

Revision ID: 0006_recovery_states_and_webhook_fields
Revises: 0005_add_webhook_events_and_recovery_jobs
Create Date: 2026-05-05
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0006_recovery_states_and_webhook_fields"
down_revision = "0005_add_webhook_events_and_recovery_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "appointments",
        sa.Column("recovery_state", sa.String(length=30), nullable=False, server_default="pending"),
    )
    op.add_column("appointments", sa.Column("recovery_last_error", sa.String(length=500), nullable=True))
    op.add_column("appointments", sa.Column("recovery_updated_at", sa.DateTime(), nullable=True))
    op.create_index("ix_appointments_recovery_state", "appointments", ["recovery_state"], unique=False)
    op.alter_column("appointments", "recovery_state", server_default=None)

    op.add_column("webhook_events", sa.Column("external_event_id", sa.String(length=128), nullable=True))
    op.add_column(
        "webhook_events",
        sa.Column("signature_valid", sa.Boolean(), nullable=False, server_default=sa.text("1")),
    )
    op.create_index("ix_webhook_events_external_event_id", "webhook_events", ["external_event_id"], unique=False)
    op.alter_column("webhook_events", "signature_valid", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_webhook_events_external_event_id", table_name="webhook_events")
    op.drop_column("webhook_events", "signature_valid")
    op.drop_column("webhook_events", "external_event_id")

    op.drop_index("ix_appointments_recovery_state", table_name="appointments")
    op.drop_column("appointments", "recovery_updated_at")
    op.drop_column("appointments", "recovery_last_error")
    op.drop_column("appointments", "recovery_state")

