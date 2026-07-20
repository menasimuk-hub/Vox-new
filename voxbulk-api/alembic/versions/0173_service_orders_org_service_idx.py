"""0173 — Composite index on service_orders (org_id, service_code) for home-summary.

Revision ID: 0173_service_orders_org_service_idx
Revises: 0172_seo_engine_connectors
"""

from __future__ import annotations

from alembic import op

revision = "0173_service_orders_org_service_idx"
down_revision = "0172_seo_engine_connectors"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_service_orders_org_service",
        "service_orders",
        ["org_id", "service_code"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_service_orders_org_service", table_name="service_orders")
