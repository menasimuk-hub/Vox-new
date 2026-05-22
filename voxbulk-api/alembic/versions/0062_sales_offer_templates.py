"""Sales offer templates + AI template mapping on lead sales settings.

Revision ID: 0062_sales_offer_templates
Revises: 0061_sales_auto_offer_type
"""

from __future__ import annotations

import uuid
from datetime import datetime

from alembic import op
import sqlalchemy as sa

revision = "0062_sales_offer_templates"
down_revision = "0061_sales_auto_offer_type"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    bind = op.get_bind()
    return name in sa.inspect(bind).get_table_names()


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    return any(c["name"] == column for c in sa.inspect(bind).get_columns(table))


def upgrade() -> None:
    if not _has_table("sales_offer_templates"):
        op.create_table(
            "sales_offer_templates",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("name", sa.String(length=128), nullable=False),
            sa.Column("offer_type", sa.String(length=32), nullable=False, server_default="dental_trial"),
            sa.Column("plan_code", sa.String(length=64), nullable=True),
            sa.Column("trial_days", sa.Integer(), nullable=False, server_default="15"),
            sa.Column("survey_contacts_included", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("interview_contacts_included", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("free_call_credits", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("expires_in_days", sa.Integer(), nullable=False, server_default="30"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="100"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )

    for col, default in (
        ("sales_template_subscription_id", None),
        ("sales_template_survey_id", None),
        ("sales_template_interview_id", None),
    ):
        if not _has_column("lead_sales_settings", col):
            op.add_column("lead_sales_settings", sa.Column(col, sa.String(length=36), nullable=True))

    bind = op.get_bind()
    if _has_table("sales_offer_templates"):
        count = bind.execute(sa.text("SELECT COUNT(*) FROM sales_offer_templates")).scalar() or 0
        if int(count) == 0:
            now = datetime.utcnow()
            rows = [
                ("subscription", "Subscription sale 1", "dental_trial", "dental_1", 15, 0, 0, 10),
                ("survey", "Survey sale 1", "survey_credits", None, 0, 3, 0, 20),
                ("interview", "Interview sale 1", "interview_credits", None, 0, 0, 3, 30),
            ]
            for sort_order, (key, name, offer_type, plan, trial, survey, interview, order) in enumerate(rows, start=1):
                tid = str(uuid.uuid4())
                bind.execute(
                    sa.text(
                        """
                        INSERT INTO sales_offer_templates
                        (id, name, offer_type, plan_code, trial_days, survey_contacts_included,
                         interview_contacts_included, free_call_credits, expires_in_days, is_active, sort_order, created_at, updated_at)
                        VALUES
                        (:id, :name, :offer_type, :plan_code, :trial_days, :survey, :interview, 0, 30, 1, :sort_order, :now, :now)
                        """
                    ),
                    {
                        "id": tid,
                        "name": name,
                        "offer_type": offer_type,
                        "plan_code": plan,
                        "trial_days": trial,
                        "survey": survey,
                        "interview": interview,
                        "sort_order": order,
                        "now": now,
                    },
                )
                setting_col = {
                    "subscription": "sales_template_subscription_id",
                    "survey": "sales_template_survey_id",
                    "interview": "sales_template_interview_id",
                }[key]
                if _has_column("lead_sales_settings", setting_col):
                    bind.execute(
                        sa.text(f"UPDATE lead_sales_settings SET {setting_col} = :tid WHERE id = 'default'"),
                        {"tid": tid},
                    )


def downgrade() -> None:
    for col in ("sales_template_interview_id", "sales_template_survey_id", "sales_template_subscription_id"):
        if _has_column("lead_sales_settings", col):
            op.drop_column("lead_sales_settings", col)
    if _has_table("sales_offer_templates"):
        op.drop_table("sales_offer_templates")
