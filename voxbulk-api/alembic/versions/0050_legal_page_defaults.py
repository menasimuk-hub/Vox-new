"""seed legal page default HTML bodies

Revision ID: 0050_legal_page_defaults
Revises: 0049_legal_pages
"""

from __future__ import annotations

import json
from pathlib import Path

import sqlalchemy as sa
from alembic import op

revision = "0050_legal_page_defaults"
down_revision = "0049_legal_pages"
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
                    updated_at = CURRENT_TIMESTAMP
                WHERE slug = :slug AND (body IS NULL OR body = '')
                """
            ),
            {"slug": slug, "body": body},
        )
    conn.execute(
        sa.text("UPDATE legal_pages SET public_path = '/legal-policies' WHERE public_path <> '/legal-policies'")
    )


def downgrade() -> None:
    paths = {
        "terms": "/terms",
        "privacy": "/privacy",
        "cookies": "/cookies",
        "gdpr": "/gdpr",
        "legal": "/legal",
    }
    conn = op.get_bind()
    for slug, path in paths.items():
        conn.execute(
            sa.text("UPDATE legal_pages SET public_path = :path WHERE slug = :slug"),
            {"slug": slug, "path": path},
        )
