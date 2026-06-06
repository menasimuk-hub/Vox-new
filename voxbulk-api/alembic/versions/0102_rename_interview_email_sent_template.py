"""Rename interview_email_sent Telnyx template to voxbulk_interview_email_sent."""

from alembic import op
import sqlalchemy as sa

revision = "0102_rename_interview_email_sent_template"
down_revision = "0101_wa_interview_platform_templates"
branch_labels = None
depends_on = None

OLD_NAME = "interview_email_sent"
NEW_NAME = "voxbulk_interview_email_sent"


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "UPDATE telnyx_whatsapp_templates "
            "SET name = :new_name, updated_at = CURRENT_TIMESTAMP "
            "WHERE LOWER(name) = :old_name "
            "AND (sales_template_key = 'interview_email_sent' OR sales_template_key IS NULL)"
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
            "AND sales_template_key = 'interview_email_sent'"
        ),
        {"old_name": OLD_NAME, "new_name": NEW_NAME.lower()},
    )
