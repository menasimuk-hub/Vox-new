"""feedback_ai_follow_up_jobs for Customer Feedback AI voice callbacks."""

revision = "0160_feedback_ai_follow_up_jobs"
down_revision = "0159_custom_org_feedback_plan"
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade() -> None:
    op.create_table(
        "feedback_ai_follow_up_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("org_id", sa.String(36), sa.ForeignKey("organisations.id"), nullable=False, index=True),
        sa.Column("location_id", sa.String(36), sa.ForeignKey("feedback_locations.id"), nullable=False, index=True),
        sa.Column("session_id", sa.String(36), sa.ForeignKey("feedback_sessions.id"), nullable=False, unique=True, index=True),
        sa.Column("visitor_phone", sa.String(64), nullable=False),
        sa.Column("business_context", sa.Text(), nullable=True),
        sa.Column("promo_enabled", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("promo_code", sa.String(64), nullable=True),
        sa.Column("promo_description", sa.Text(), nullable=True),
        sa.Column("scheduled_at", sa.DateTime(), nullable=False, index=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="scheduled"),
        sa.Column("call_id", sa.String(128), nullable=True),
        sa.Column("outcome_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("feedback_ai_follow_up_jobs")
