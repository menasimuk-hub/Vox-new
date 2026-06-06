"""Rename interview booking confirmation WhatsApp template to interview_confirm_book."""

from alembic import op
import sqlalchemy as sa

revision = "0103_rename_interview_confirm_template"
down_revision = "0102_rename_interview_email_sent_template"
branch_labels = None
depends_on = None

OLD_NAME = "voxbulk_interview_confirm"
NEW_NAME = "interview_confirm_book"


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "UPDATE telnyx_whatsapp_templates "
            "SET name = :new_name, updated_at = CURRENT_TIMESTAMP "
            "WHERE LOWER(name) = :old_name "
            "AND (sales_template_key = 'interview_booking_confirm' OR sales_template_key IS NULL)"
        ),
        {"old_name": OLD_NAME.lower(), "new_name": NEW_NAME},
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "UPDATE telnyx_whatsapp_templates "
            "SET name = :old_name, updated_at = CURRENT_TIMESTAMP "
            "WHERE LOWER(name) = :new_name "
            "AND sales_template_key = 'interview_booking_confirm'"
        ),
        {"old_name": OLD_NAME, "new_name": NEW_NAME.lower()},
    )
