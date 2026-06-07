"""Survey WhatsApp voice note transcription jobs."""

from alembic import op
import sqlalchemy as sa

revision = "0104_survey_voice_note_jobs"
down_revision = "0103_rename_interview_confirm_template"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "survey_voice_note_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("order_id", sa.String(length=36), nullable=False),
        sa.Column("recipient_id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=True),
        sa.Column("whatsapp_log_id", sa.Integer(), nullable=True),
        sa.Column("answer_context", sa.String(length=32), nullable=False, server_default="normal"),
        sa.Column("step_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("answer_index", sa.Integer(), nullable=True),
        sa.Column("inbound_message_id", sa.String(length=128), nullable=False),
        sa.Column("provider_media_id", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("audio_file_path", sa.Text(), nullable=True),
        sa.Column("audio_original_filename", sa.String(length=255), nullable=True),
        sa.Column("audio_mime_type", sa.String(length=128), nullable=True),
        sa.Column("audio_file_size", sa.Integer(), nullable=True),
        sa.Column("media_url", sa.Text(), nullable=True),
        sa.Column("answer_text", sa.Text(), nullable=True),
        sa.Column("answer_source", sa.String(length=32), nullable=False, server_default="voice_note"),
        sa.Column("detected_language", sa.String(length=32), nullable=True),
        sa.Column("transcription_status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("transcription_error", sa.Text(), nullable=True),
        sa.Column("transcription_model", sa.String(length=128), nullable=True),
        sa.Column("transcription_duration_ms", sa.Integer(), nullable=True),
        sa.Column("transcription_job_id", sa.String(length=64), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("transcribed_at", sa.DateTime(), nullable=True),
        sa.Column("audio_deleted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["org_id"], ["organisations.id"]),
        sa.ForeignKeyConstraint(["order_id"], ["service_orders.id"]),
        sa.ForeignKeyConstraint(["recipient_id"], ["service_order_recipients.id"]),
        sa.ForeignKeyConstraint(["session_id"], ["survey_sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("inbound_message_id", "provider_media_id", name="uq_survey_voice_note_inbound_media"),
    )
    op.create_index("ix_survey_voice_note_jobs_org_id", "survey_voice_note_jobs", ["org_id"])
    op.create_index("ix_survey_voice_note_jobs_order_id", "survey_voice_note_jobs", ["order_id"])
    op.create_index("ix_survey_voice_note_jobs_recipient_id", "survey_voice_note_jobs", ["recipient_id"])
    op.create_index("ix_survey_voice_note_jobs_transcription_status", "survey_voice_note_jobs", ["transcription_status"])


def downgrade() -> None:
    op.drop_table("survey_voice_note_jobs")
