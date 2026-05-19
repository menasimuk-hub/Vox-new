"""add webhook_events and recovery_jobs

Revision ID: 0005_add_webhook_events_and_recovery_jobs
Revises: 0004_add_user_is_superuser
Create Date: 2026-05-05
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0005_add_webhook_events_and_recovery_jobs"
down_revision = "0004_add_user_is_superuser"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "webhook_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("dedupe_key", sa.String(length=128), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.String(length=500), nullable=True),
        sa.Column("raw_body", sa.Text(), nullable=False),
        sa.Column("received_at", sa.DateTime(), nullable=False),
        sa.Column("processed_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("provider", "dedupe_key", name="uq_webhook_provider_dedupe"),
    )
    op.create_index("ix_webhook_events_provider", "webhook_events", ["provider"], unique=False)
    op.create_index("ix_webhook_events_org_id", "webhook_events", ["org_id"], unique=False)

    op.create_table(
        "recovery_jobs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("org_id", sa.String(length=36), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("appointment_id", sa.String(length=36), sa.ForeignKey("appointments.id"), nullable=False),
        sa.Column("idempotency_key", sa.String(length=100), nullable=False),
        sa.Column("state", sa.String(length=30), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("org_id", "idempotency_key", name="uq_recovery_org_idempotency"),
    )
    op.create_index("ix_recovery_jobs_org_id", "recovery_jobs", ["org_id"], unique=False)
    op.create_index("ix_recovery_jobs_appointment_id", "recovery_jobs", ["appointment_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_recovery_jobs_appointment_id", table_name="recovery_jobs")
    op.drop_index("ix_recovery_jobs_org_id", table_name="recovery_jobs")
    op.drop_table("recovery_jobs")

    op.drop_index("ix_webhook_events_org_id", table_name="webhook_events")
    op.drop_index("ix_webhook_events_provider", table_name="webhook_events")
    op.drop_table("webhook_events")

