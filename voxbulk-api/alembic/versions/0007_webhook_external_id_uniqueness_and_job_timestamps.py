"""webhook external id uniqueness + recovery job timestamps

Revision ID: 0007_webhook_external_id_uniqueness_and_job_timestamps
Revises: 0006_recovery_states_and_webhook_fields
Create Date: 2026-05-05
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0007_webhook_external_id_uniqueness_and_job_timestamps"
down_revision = "0006_recovery_states_and_webhook_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_webhook_provider_external_event_id",
        "webhook_events",
        ["provider", "external_event_id"],
    )

    op.add_column("recovery_jobs", sa.Column("started_at", sa.DateTime(), nullable=True))
    op.add_column("recovery_jobs", sa.Column("finished_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("recovery_jobs", "finished_at")
    op.drop_column("recovery_jobs", "started_at")
    op.drop_constraint("uq_webhook_provider_external_event_id", "webhook_events", type_="unique")

