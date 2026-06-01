"""Add organisation HubSpot integration config.

Revision ID: 0081_org_hubspot_config
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0081_org_hubspot_config"
down_revision = "0080_org_logo"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c["name"] for c in insp.get_columns("organisations")}
    if "hubspot_config_json" not in cols:
        op.add_column("organisations", sa.Column("hubspot_config_json", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("organisations", "hubspot_config_json")
