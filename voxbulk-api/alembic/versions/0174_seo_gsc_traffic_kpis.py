"""0174 — GSC traffic KPI fields for SEO Control overview.

Revision ID: 0174_seo_gsc_traffic_kpis
Revises: 0173_service_orders_org_service_idx
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0174_seo_gsc_traffic_kpis"
down_revision = "0173_service_orders_org_service_idx"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("site_seo_settings", sa.Column("gsc_clicks", sa.String(32), nullable=True))
    op.add_column("site_seo_settings", sa.Column("gsc_clicks_prev", sa.String(32), nullable=True))
    op.add_column("site_seo_settings", sa.Column("gsc_impressions", sa.String(32), nullable=True))
    op.add_column("site_seo_settings", sa.Column("gsc_impressions_prev", sa.String(32), nullable=True))
    op.add_column("site_seo_settings", sa.Column("gsc_metrics_refreshed_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("site_seo_settings", "gsc_metrics_refreshed_at")
    op.drop_column("site_seo_settings", "gsc_impressions_prev")
    op.drop_column("site_seo_settings", "gsc_impressions")
    op.drop_column("site_seo_settings", "gsc_clicks_prev")
    op.drop_column("site_seo_settings", "gsc_clicks")
