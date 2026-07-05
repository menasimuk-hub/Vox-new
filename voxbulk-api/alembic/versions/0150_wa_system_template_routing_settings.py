"""Add wa_system_template_routing_settings for local vs Meta sync routing."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0150_wa_system_template_routing"
down_revision = "0149_feedback_industry_org_visibility"
branch_labels = None
depends_on = None


def upgrade() -> None:
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


def downgrade() -> None:
    op.drop_table("wa_system_template_routing_settings")
