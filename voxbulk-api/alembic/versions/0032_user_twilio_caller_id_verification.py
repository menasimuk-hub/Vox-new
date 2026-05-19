"""user twilio caller id verification

Revision ID: 0032_user_twilio_caller_id_verification
Revises: 0031_twilio_sandbox_fields
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0032_user_twilio_caller_id_verification"
down_revision = "0031_twilio_sandbox_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    user_cols = {c["name"] for c in inspector.get_columns("users")}
    recovery_cols = {c["name"] for c in inspector.get_columns("recovery_jobs")}
    indexes = {i["name"] for i in inspector.get_indexes("users")} | {i["name"] for i in inspector.get_indexes("recovery_jobs")}

    def add_user_col(name: str, column: sa.Column) -> None:
        if name not in user_cols:
            op.add_column("users", column)

    add_user_col("phone_number", sa.Column("phone_number", sa.String(length=50), nullable=True))
    add_user_col("phone_e164", sa.Column("phone_e164", sa.String(length=32), nullable=True))
    add_user_col("phone_verification_status", sa.Column("phone_verification_status", sa.String(length=30), nullable=False, server_default="unverified"))
    add_user_col("twilio_outgoing_caller_id_sid", sa.Column("twilio_outgoing_caller_id_sid", sa.String(length=100), nullable=True))
    add_user_col("twilio_phone_verification_sid", sa.Column("twilio_phone_verification_sid", sa.String(length=100), nullable=True))
    add_user_col("phone_verification_requested_at", sa.Column("phone_verification_requested_at", sa.DateTime(), nullable=True))
    add_user_col("phone_verification_completed_at", sa.Column("phone_verification_completed_at", sa.DateTime(), nullable=True))
    add_user_col("phone_verification_last_error", sa.Column("phone_verification_last_error", sa.String(length=500), nullable=True))
    if "ix_users_phone_e164" not in indexes:
        op.create_index("ix_users_phone_e164", "users", ["phone_e164"])
    if "ix_users_twilio_outgoing_caller_id_sid" not in indexes:
        op.create_index("ix_users_twilio_outgoing_caller_id_sid", "users", ["twilio_outgoing_caller_id_sid"])
    if "ix_users_twilio_phone_verification_sid" not in indexes:
        op.create_index("ix_users_twilio_phone_verification_sid", "users", ["twilio_phone_verification_sid"])

    if "requested_by_user_id" not in recovery_cols:
        # Add without inline FK so SQLite can alter the table safely.
        op.add_column("recovery_jobs", sa.Column("requested_by_user_id", sa.String(length=36), nullable=True))
    if "ix_recovery_jobs_requested_by_user_id" not in indexes:
        op.create_index("ix_recovery_jobs_requested_by_user_id", "recovery_jobs", ["requested_by_user_id"])


def downgrade() -> None:
    op.drop_index("ix_recovery_jobs_requested_by_user_id", table_name="recovery_jobs")
    op.drop_column("recovery_jobs", "requested_by_user_id")
    op.drop_index("ix_users_twilio_phone_verification_sid", table_name="users")
    op.drop_index("ix_users_twilio_outgoing_caller_id_sid", table_name="users")
    op.drop_index("ix_users_phone_e164", table_name="users")
    op.drop_column("users", "phone_verification_last_error")
    op.drop_column("users", "phone_verification_completed_at")
    op.drop_column("users", "phone_verification_requested_at")
    op.drop_column("users", "twilio_phone_verification_sid")
    op.drop_column("users", "twilio_outgoing_caller_id_sid")
    op.drop_column("users", "phone_verification_status")
    op.drop_column("users", "phone_e164")
    op.drop_column("users", "phone_number")
