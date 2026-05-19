"""add Twilio provider fields to recovery_jobs and call_logs

Revision ID: 0008_twilio_provider_fields
Revises: 0007_webhook_external_id_uniqueness_and_job_timestamps
Create Date: 2026-05-05
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0008_twilio_provider_fields"
down_revision = "0007_webhook_external_id_uniqueness_and_job_timestamps"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("recovery_jobs", sa.Column("provider", sa.String(length=30), nullable=False, server_default="twilio"))
    op.add_column("recovery_jobs", sa.Column("provider_ref", sa.String(length=100), nullable=True))
    op.add_column("recovery_jobs", sa.Column("provider_status", sa.String(length=50), nullable=True))
    op.create_index("ix_recovery_jobs_provider_ref", "recovery_jobs", ["provider_ref"], unique=False)
    op.alter_column("recovery_jobs", "provider", server_default=None)

    op.add_column("call_logs", sa.Column("external_call_id", sa.String(length=100), nullable=True))
    op.create_index("ix_call_logs_external_call_id", "call_logs", ["external_call_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_call_logs_external_call_id", table_name="call_logs")
    op.drop_column("call_logs", "external_call_id")

    op.drop_index("ix_recovery_jobs_provider_ref", table_name="recovery_jobs")
    op.drop_column("recovery_jobs", "provider_status")
    op.drop_column("recovery_jobs", "provider_ref")
    op.drop_column("recovery_jobs", "provider")

