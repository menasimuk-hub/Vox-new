"""Interview CV intake fields on service_order_recipients.

Revision ID: 0068_interview_cv_intake
Revises: 0067_voice_agent_extensions
"""

from alembic import op
import sqlalchemy as sa

revision = "0068_interview_cv_intake"
down_revision = "0067_voice_agent_extensions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("service_order_recipients", sa.Column("cv_quality", sa.String(32), nullable=True))
    op.add_column("service_order_recipients", sa.Column("cv_filename", sa.String(255), nullable=True))
    op.add_column("service_order_recipients", sa.Column("cv_text", sa.Text(), nullable=True))
    op.add_column("service_order_recipients", sa.Column("cv_parsed_json", sa.Text(), nullable=True))
    op.add_column("service_order_recipients", sa.Column("intake_errors_json", sa.Text(), nullable=True))
    op.add_column("service_order_recipients", sa.Column("intake_source", sa.String(32), nullable=True))
    op.alter_column("service_order_recipients", "phone", existing_type=sa.String(64), nullable=True)


def downgrade() -> None:
    op.alter_column("service_order_recipients", "phone", existing_type=sa.String(64), nullable=False)
    op.drop_column("service_order_recipients", "intake_source")
    op.drop_column("service_order_recipients", "intake_errors_json")
    op.drop_column("service_order_recipients", "cv_parsed_json")
    op.drop_column("service_order_recipients", "cv_text")
    op.drop_column("service_order_recipients", "cv_filename")
    op.drop_column("service_order_recipients", "cv_quality")
