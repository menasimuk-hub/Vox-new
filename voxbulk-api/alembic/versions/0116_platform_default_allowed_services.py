"""Platform default allowed dashboard services.

Revision ID: 0116_platform_default_allowed_services
Revises: 0115_customer_feedback_foundation
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0116_platform_default_allowed_services"
down_revision = "0115_customer_feedback_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "platform_services_settings",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("default_allowed_services_json", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.execute(
        sa.text(
            "INSERT INTO platform_services_settings (id, default_allowed_services_json, updated_at) "
            "VALUES ('default', '{\"interview\": true, \"survey\": true, \"customer_feedback\": false, "
            "\"recovery\": false, \"follow_up\": false}', CURRENT_TIMESTAMP)"
        )
    )


def downgrade() -> None:
    op.drop_table("platform_services_settings")
