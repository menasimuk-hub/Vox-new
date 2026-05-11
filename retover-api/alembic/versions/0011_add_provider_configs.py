"""add provider_configs for admin settings

Revision ID: 0011_add_provider_configs
Revises: 0010_add_whatsapp_external_message_id
Create Date: 2026-05-05
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0011_add_provider_configs"
down_revision = "0010_add_whatsapp_external_message_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "provider_configs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("scope", sa.String(length=20), nullable=False),
        sa.Column("org_id", sa.String(length=36), sa.ForeignKey("organisations.id"), nullable=True),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column("encrypted_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("scope", "org_id", "provider", name="uq_provider_config_scope_org_provider"),
    )
    op.create_index("ix_provider_configs_scope", "provider_configs", ["scope"], unique=False)
    op.create_index("ix_provider_configs_org_id", "provider_configs", ["org_id"], unique=False)
    op.create_index("ix_provider_configs_provider", "provider_configs", ["provider"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_provider_configs_provider", table_name="provider_configs")
    op.drop_index("ix_provider_configs_org_id", table_name="provider_configs")
    op.drop_index("ix_provider_configs_scope", table_name="provider_configs")
    op.drop_table("provider_configs")

