"""Admin-hidden flag on WA templates — never auto-re-enable after admin disable."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0152_admin_hidden_from_survey"
down_revision = "0151_wa_template_sync_from_meta"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "telnyx_whatsapp_templates",
        sa.Column("admin_hidden_from_survey", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "feedback_wa_templates",
        sa.Column("admin_hidden_from_survey", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    # Topics already hidden should stay admin-locked.
    op.execute(
        sa.text(
            "UPDATE telnyx_whatsapp_templates SET admin_hidden_from_survey = 1 "
            "WHERE active_for_survey = 0"
        )
    )
    op.execute(
        sa.text(
            "UPDATE feedback_wa_templates SET admin_hidden_from_survey = 1 "
            "WHERE is_active = 0"
        )
    )


def downgrade() -> None:
    op.drop_column("feedback_wa_templates", "admin_hidden_from_survey")
    op.drop_column("telnyx_whatsapp_templates", "admin_hidden_from_survey")
