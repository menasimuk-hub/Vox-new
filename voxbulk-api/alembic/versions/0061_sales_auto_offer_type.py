"""Lead sales auto-offer type and service credit defaults.

Revision ID: 0061_sales_auto_offer_type
Revises: 0060_sales_offer_template_refresh
"""

from alembic import op
import sqlalchemy as sa

revision = "0061_sales_auto_offer_type"
down_revision = "0060_sales_offer_template_refresh"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return any(c["name"] == column for c in insp.get_columns(table))


def upgrade() -> None:
    if not _has_column("lead_sales_settings", "sales_auto_offer_type"):
        op.add_column(
            "lead_sales_settings",
            sa.Column("sales_auto_offer_type", sa.String(length=32), nullable=False, server_default="dental_trial"),
        )
    if not _has_column("lead_sales_settings", "sales_auto_survey_contacts"):
        op.add_column(
            "lead_sales_settings",
            sa.Column("sales_auto_survey_contacts", sa.Integer(), nullable=False, server_default="3"),
        )
    if not _has_column("lead_sales_settings", "sales_auto_interview_contacts"):
        op.add_column(
            "lead_sales_settings",
            sa.Column("sales_auto_interview_contacts", sa.Integer(), nullable=False, server_default="3"),
        )


def downgrade() -> None:
    if _has_column("lead_sales_settings", "sales_auto_interview_contacts"):
        op.drop_column("lead_sales_settings", "sales_auto_interview_contacts")
    if _has_column("lead_sales_settings", "sales_auto_survey_contacts"):
        op.drop_column("lead_sales_settings", "sales_auto_survey_contacts")
    if _has_column("lead_sales_settings", "sales_auto_offer_type"):
        op.drop_column("lead_sales_settings", "sales_auto_offer_type")
