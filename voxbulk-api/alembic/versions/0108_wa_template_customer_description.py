"""Add customer_description for wizard display on WA survey templates."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0108_wa_template_customer_description"
down_revision = "0107_survey_voice_note_question_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "telnyx_whatsapp_templates",
        sa.Column("customer_description", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("telnyx_whatsapp_templates", "customer_description")
