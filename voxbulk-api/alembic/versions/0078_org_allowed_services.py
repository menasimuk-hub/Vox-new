"""Add allowed_services_json for admin-granted dashboard modules.

Revision ID: 0078_org_allowed_services
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0078_org_allowed_services"
down_revision = "0077_campaign_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c["name"] for c in insp.get_columns("organisations")}
    if "allowed_services_json" not in cols:
        op.add_column("organisations", sa.Column("allowed_services_json", sa.Text(), nullable=True))
    op.execute(
        """
        UPDATE organisations
        SET allowed_services_json = enabled_services_json
        WHERE allowed_services_json IS NULL AND enabled_services_json IS NOT NULL
        """
    )


def downgrade() -> None:
    op.drop_column("organisations", "allowed_services_json")
