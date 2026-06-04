"""Backfill survey_type_id on templates and dedupe mistaken template links."""

from alembic import op
import sqlalchemy as sa

revision = "0089_wa_survey_template_scope"
down_revision = "0088_wa_survey_step_role"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    # Backfill owner survey type from voxbulk_survey_{slug}_* template names.
    conn.execute(
        sa.text(
            """
            UPDATE telnyx_whatsapp_templates t
            INNER JOIN survey_types st ON LOWER(t.name) REGEXP CONCAT('^voxbulk_survey_', st.slug, '(_|$)')
            SET t.survey_type_id = st.id
            WHERE t.survey_type_id IS NULL
            """
        )
    )
    # Remove join rows where template slug does not match the linked survey type slug.
    conn.execute(
        sa.text(
            """
            DELETE stt FROM survey_type_templates stt
            INNER JOIN survey_types st ON st.id = stt.survey_type_id
            INNER JOIN telnyx_whatsapp_templates t ON t.id = stt.template_id
            WHERE t.survey_type_id IS NOT NULL
              AND t.survey_type_id <> stt.survey_type_id
            """
        )
    )
    conn.execute(
        sa.text(
            """
            DELETE stt FROM survey_type_templates stt
            INNER JOIN survey_types st ON st.id = stt.survey_type_id
            INNER JOIN telnyx_whatsapp_templates t ON t.id = stt.template_id
            WHERE t.survey_type_id IS NULL
              AND LOWER(t.name) NOT REGEXP CONCAT('^voxbulk_survey_', st.slug, '(_|$)')
              AND LOWER(t.name) NOT REGEXP CONCAT('^voxbulk_survey_', st.slug, '_(standard|anonymous)$')
            """
        )
    )


def downgrade() -> None:
    pass
