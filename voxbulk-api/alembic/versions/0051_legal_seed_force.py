"""force seed legal page HTML from bundled defaults

Revision ID: 0051_legal_seed_force
Revises: 0050_legal_page_defaults
"""

from __future__ import annotations

import json
from pathlib import Path

import sqlalchemy as sa
from alembic import op

revision = "0051_legal_seed_force"
down_revision = "0050_legal_page_defaults"
branch_labels = None
depends_on = None

_DATA_PATH = Path(__file__).resolve().parents[1] / "app" / "data" / "legal_default_bodies.json"


def upgrade() -> None:
    if not _DATA_PATH.exists():
        return
    bodies = json.loads(_DATA_PATH.read_text(encoding="utf-8"))
    conn = op.get_bind()
    for slug, body in bodies.items():
        if not body:
            continue
        conn.execute(
            sa.text(
                """
                UPDATE legal_pages
                SET body = :body,
                    public_path = '/legal-policies',
                    is_published = TRUE,
                    updated_at = CURRENT_TIMESTAMP
                WHERE slug = :slug AND (body IS NULL OR TRIM(body) = '')
                """
            ),
            {"slug": slug, "body": body},
        )


def downgrade() -> None:
    pass
