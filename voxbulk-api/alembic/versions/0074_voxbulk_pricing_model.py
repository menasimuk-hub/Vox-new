"""VoxBulk pricing model — plans, FX, connection fee, top-ups, custom org pricing, wallet."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0074_voxbulk_pricing_model"
down_revision = "0073_org_enabled_services"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return any(c["name"] == column for c in insp.get_columns(table))


def _has_table(table: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return table in insp.get_table_names()


def upgrade() -> None:
    if not _has_column("plans", "cv_scans_included"):
        op.add_column("plans", sa.Column("cv_scans_included", sa.Integer(), nullable=False, server_default="0"))
    if not _has_column("plans", "is_featured"):
        op.add_column("plans", sa.Column("is_featured", sa.Boolean(), nullable=False, server_default=sa.false()))
    if not _has_column("plans", "is_enterprise"):
        op.add_column("plans", sa.Column("is_enterprise", sa.Boolean(), nullable=False, server_default=sa.false()))

    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("plans") as batch:
            batch.alter_column("price_gbp_pence", existing_type=sa.Integer(), nullable=True)
    else:
        op.alter_column("plans", "price_gbp_pence", existing_type=sa.Integer(), nullable=True)

    if not _has_column("organisations", "wallet_balance_pence"):
        op.add_column("organisations", sa.Column("wallet_balance_pence", sa.Integer(), nullable=False, server_default="0"))

    if not _has_table("pricing_global_settings"):
        op.create_table(
            "pricing_global_settings",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("fx_aud_multiplier", sa.Float(), nullable=False, server_default="1.95"),
            sa.Column("fx_cad_multiplier", sa.Float(), nullable=False, server_default="1.71"),
            sa.Column("fx_usd_multiplier", sa.Float(), nullable=False, server_default="1.26"),
            sa.Column("connection_fee_pence", sa.Integer(), nullable=False, server_default="200"),
            sa.Column(
                "connection_fee_label",
                sa.String(255),
                nullable=False,
                server_default="AI Interview — connection fee",
            ),
            sa.Column("connection_fee_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("interview_per_min_pence", sa.Integer(), nullable=False, server_default="35"),
            sa.Column("whatsapp_survey_fee_pence", sa.Integer(), nullable=False, server_default="150"),
            sa.Column("ats_cv_scan_fee_pence", sa.Integer(), nullable=False, server_default="75"),
            sa.Column("estimator_default_duration_min", sa.Integer(), nullable=False, server_default="12"),
            sa.Column("estimator_default_interview_count", sa.Integer(), nullable=False, server_default="100"),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )

    if not _has_table("topup_tiers"):
        op.create_table(
            "topup_tiers",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("credit_gbp_pence", sa.Integer(), nullable=False),
            sa.Column("bonus_credit_pence", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="100"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )

    if not _has_table("org_custom_pricing"):
        op.create_table(
            "org_custom_pricing",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("org_id", sa.String(36), sa.ForeignKey("organisations.id"), nullable=False),
            sa.Column("label", sa.String(255), nullable=False),
            sa.Column("monthly_price_gbp_pence", sa.Integer(), nullable=True),
            sa.Column("per_min_pence", sa.Integer(), nullable=True),
            sa.Column("connection_fee_pence", sa.Integer(), nullable=True),
            sa.Column("minutes_included", sa.Integer(), nullable=True),
            sa.Column("whatsapp_included", sa.Integer(), nullable=True),
            sa.Column("cv_scans_included", sa.Integer(), nullable=True),
            sa.Column("interview_per_min_pence", sa.Integer(), nullable=True),
            sa.Column("whatsapp_survey_fee_pence", sa.Integer(), nullable=True),
            sa.Column("ats_cv_scan_fee_pence", sa.Integer(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_org_custom_pricing_org_id", "org_custom_pricing", ["org_id"])

    bind = op.get_bind()
    existing = bind.execute(sa.text("SELECT id FROM pricing_global_settings WHERE id = 1")).fetchone()
    if existing is None:
        bind.execute(
            sa.text(
                """
                INSERT INTO pricing_global_settings (
                    id, fx_aud_multiplier, fx_cad_multiplier, fx_usd_multiplier,
                    connection_fee_pence, connection_fee_label, connection_fee_enabled,
                    interview_per_min_pence, whatsapp_survey_fee_pence, ats_cv_scan_fee_pence,
                    estimator_default_duration_min, estimator_default_interview_count, updated_at
                ) VALUES (
                    1, 1.95, 1.71, 1.26,
                    200, 'AI Interview — connection fee', 1,
                    35, 150, 75,
                    12, 100, CURRENT_TIMESTAMP
                )
                """
            )
        )


def downgrade() -> None:
    op.drop_index("ix_org_custom_pricing_org_id", table_name="org_custom_pricing")
    op.drop_table("org_custom_pricing")
    op.drop_table("topup_tiers")
    op.drop_table("pricing_global_settings")
    op.drop_column("organisations", "wallet_balance_pence")
    op.drop_column("plans", "is_enterprise")
    op.drop_column("plans", "is_featured")
    op.drop_column("plans", "cv_scans_included")
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("plans") as batch:
            batch.alter_column("price_gbp_pence", existing_type=sa.Integer(), nullable=False)
    else:
        op.alter_column("plans", "price_gbp_pence", existing_type=sa.Integer(), nullable=False)
