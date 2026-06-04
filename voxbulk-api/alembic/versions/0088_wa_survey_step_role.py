"""Add step_role to WhatsApp survey templates for step bank builder."""

from alembic import op
import sqlalchemy as sa

revision = "0088_wa_survey_step_role"
down_revision = "0087_survey_type_templates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("telnyx_whatsapp_templates", sa.Column("step_role", sa.String(32), nullable=True))
    op.create_index("ix_telnyx_wa_tpl_step_role", "telnyx_whatsapp_templates", ["step_role"])


def downgrade() -> None:
    op.drop_index("ix_telnyx_wa_tpl_step_role", table_name="telnyx_whatsapp_templates")
    op.drop_column("telnyx_whatsapp_templates", "step_role")
