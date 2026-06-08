"""Add wa_survey_extra_pence; keep whatsapp_survey_fee_pence column name in DB."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0106_wa_survey_pricing_fields"
down_revision = "0105_survey_campaign_ids"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    cols = {c["name"] for c in insp.get_columns("pricing_global_settings")}
    if "wa_survey_extra_pence" not in cols:
        op.add_column(
            "pricing_global_settings",
            sa.Column("wa_survey_extra_pence", sa.Integer(), nullable=False, server_default="49"),
        )

    org_cols = {c["name"] for c in insp.get_columns("org_custom_pricing")}
    if "wa_survey_extra_pence" not in org_cols:
        op.add_column(
            "org_custom_pricing",
            sa.Column("wa_survey_extra_pence", sa.Integer(), nullable=True),
        )


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    cols = {c["name"] for c in insp.get_columns("pricing_global_settings")}
    if "wa_survey_extra_pence" in cols:
        op.drop_column("pricing_global_settings", "wa_survey_extra_pence")

    org_cols = {c["name"] for c in insp.get_columns("org_custom_pricing")}
    if "wa_survey_extra_pence" in org_cols:
        op.drop_column("org_custom_pricing", "wa_survey_extra_pence")
