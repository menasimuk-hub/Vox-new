"""Store Celery task id on recovery jobs for org-bound status polling.

Revision ID: 0210_recovery_job_celery_task_id
Revises: 0209_org_overage_consent
Create Date: 2026-07-29
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0210_recovery_job_celery_task_id"
down_revision = "0209_org_overage_consent"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    cols = sa.inspect(bind).get_columns(table)
    return any(c["name"] == column for c in cols)


def _has_index(name: str) -> bool:
    bind = op.get_bind()
    indexes = sa.inspect(bind).get_indexes("recovery_jobs")
    return any(i.get("name") == name for i in indexes)


def upgrade() -> None:
    if not _has_column("recovery_jobs", "celery_task_id"):
        op.add_column("recovery_jobs", sa.Column("celery_task_id", sa.String(length=64), nullable=True))
    if not _has_index("ix_recovery_jobs_celery_task_id"):
        op.create_index("ix_recovery_jobs_celery_task_id", "recovery_jobs", ["celery_task_id"])


def downgrade() -> None:
    if _has_index("ix_recovery_jobs_celery_task_id"):
        op.drop_index("ix_recovery_jobs_celery_task_id", table_name="recovery_jobs")
    if _has_column("recovery_jobs", "celery_task_id"):
        op.drop_column("recovery_jobs", "celery_task_id")
