"""Career mailbox settings, interview reference IDs, CV file storage keys.

Revision ID: 0069_career_mailbox_reference
Revises: 0068_interview_cv_intake
"""

from alembic import op
import sqlalchemy as sa

revision = "0069_career_mailbox_reference"
down_revision = "0068_interview_cv_intake"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("service_orders", sa.Column("reference_id", sa.String(32), nullable=True))
    op.create_index("ix_service_orders_reference_id", "service_orders", ["reference_id"], unique=True)

    op.add_column("service_order_recipients", sa.Column("cv_storage_key", sa.String(512), nullable=True))

    op.create_table(
        "career_mailbox_settings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("mailbox_email", sa.String(320), nullable=False, server_default="careers@voxbulk.com"),
        sa.Column("imap_host", sa.String(255), nullable=True),
        sa.Column("imap_port", sa.Integer(), nullable=False, server_default="993"),
        sa.Column("imap_use_ssl", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("imap_username", sa.String(255), nullable=True),
        sa.Column("password_encrypted", sa.Text(), nullable=True),
        sa.Column("sync_interval_minutes", sa.Integer(), nullable=False, server_default="15"),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_sync_at", sa.DateTime(), nullable=True),
        sa.Column("last_sync_ok", sa.Boolean(), nullable=True),
        sa.Column("last_sync_message", sa.String(512), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("career_mailbox_settings")
    op.drop_column("service_order_recipients", "cv_storage_key")
    op.drop_index("ix_service_orders_reference_id", table_name="service_orders")
    op.drop_column("service_orders", "reference_id")
