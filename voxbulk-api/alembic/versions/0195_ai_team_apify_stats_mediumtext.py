"""Widen ai_team_apify_runs.stats_json for builtin scrape contacts.

Revision ID: 0195_ai_team_apify_stats_mediumtext
Revises: 0194_ai_team_apify_smtp
Create Date: 2026-07-26
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "0195_ai_team_apify_stats_mediumtext"
down_revision = "0194_ai_team_apify_smtp"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "mysql":
        return
    op.alter_column(
        "ai_team_apify_runs",
        "stats_json",
        existing_type=mysql.TEXT(),
        type_=mysql.MEDIUMTEXT(),
        existing_nullable=True,
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "mysql":
        return
    op.alter_column(
        "ai_team_apify_runs",
        "stats_json",
        existing_type=mysql.MEDIUMTEXT(),
        type_=mysql.TEXT(),
        existing_nullable=True,
    )
