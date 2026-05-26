"""Interview recipient ATS score columns.

Revision ID: 0072_interview_ats_score
Revises: 0071_merge_scheduling_career_heads
"""

from alembic import op
import sqlalchemy as sa

revision = "0072_interview_ats_score"
down_revision = "0071_merge_scheduling_career_heads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("service_order_recipients", sa.Column("ats_score", sa.Integer(), nullable=True))
    op.add_column("service_order_recipients", sa.Column("ats_status", sa.String(32), nullable=True))
    op.add_column("service_order_recipients", sa.Column("ats_hash", sa.String(64), nullable=True))
    op.add_column("service_order_recipients", sa.Column("ats_error", sa.String(512), nullable=True))


def downgrade() -> None:
    op.drop_column("service_order_recipients", "ats_error")
    op.drop_column("service_order_recipients", "ats_hash")
    op.drop_column("service_order_recipients", "ats_status")
    op.drop_column("service_order_recipients", "ats_score")
