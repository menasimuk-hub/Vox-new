"""Per-template sync_from_meta flag; drop global routing settings table."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0151_wa_template_sync_from_meta"
down_revision = "0150_wa_system_template_routing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "telnyx_whatsapp_templates",
        sa.Column("sync_from_meta", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "feedback_wa_templates",
        sa.Column("sync_from_meta", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.drop_table("wa_system_template_routing_settings")


def downgrade() -> None:
    op.create_table(
        "wa_system_template_routing_settings",
        sa.Column("product", sa.String(length=32), nullable=False),
        sa.Column("template_source", sa.String(length=32), nullable=False, server_default="local"),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("product"),
    )
    op.execute(
        sa.text(
            "INSERT INTO wa_system_template_routing_settings (product, template_source, updated_at) "
            "VALUES ('survey', 'local', CURRENT_TIMESTAMP), "
            "('feedback', 'local', CURRENT_TIMESTAMP)"
        )
    )
    op.drop_column("feedback_wa_templates", "sync_from_meta")
    op.drop_column("telnyx_whatsapp_templates", "sync_from_meta")
