"""Add provider_configs.visible_to_orgs flag for admin soft-launch toggle.

`is_enabled` continues to mean "platform credentials configured & wired";
`visible_to_orgs` is the new "show this provider on dashboards" flag so admins can
finish setup privately before any organisation sees the integration.

Backfill: every row that is currently enabled stays visible so behaviour is
unchanged on upgrade. Microsoft Calendar gets a disabled+hidden stub row so the
new admin sub-page has something to edit.
"""

from __future__ import annotations

import json
from datetime import datetime

import sqlalchemy as sa
from alembic import op

revision = "0123_provider_config_visible_to_orgs"
down_revision = "0122_feedback_results_insights"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "provider_configs",
        sa.Column("visible_to_orgs", sa.Boolean(), nullable=False, server_default=sa.text("0")),
    )

    op.execute(
        sa.text(
            "UPDATE provider_configs SET visible_to_orgs = is_enabled "
            "WHERE provider IN ('calendly', 'cal_com', 'google_calendar', 'hubspot')"
        )
    )

    bind = op.get_bind()
    existing = bind.execute(
        sa.text("SELECT id FROM provider_configs WHERE scope='platform' AND provider='microsoft_calendar' LIMIT 1")
    ).fetchone()
    if existing is None:
        try:
            from app.core.encryption import get_encryptor

            cipher = get_encryptor().encrypt_str(json.dumps({}, ensure_ascii=False, separators=(",", ":")))
        except Exception:
            cipher = json.dumps({}, ensure_ascii=False, separators=(",", ":"))
        now = datetime.utcnow()
        bind.execute(
            sa.text(
                "INSERT INTO provider_configs (scope, org_id, provider, is_enabled, visible_to_orgs, encrypted_json, "
                "created_at, updated_at) VALUES (:scope, NULL, :provider, :is_enabled, :visible_to_orgs, "
                ":encrypted_json, :created_at, :updated_at)"
            ),
            {
                "scope": "platform",
                "provider": "microsoft_calendar",
                "is_enabled": False,
                "visible_to_orgs": False,
                "encrypted_json": cipher,
                "created_at": now,
                "updated_at": now,
            },
        )


def downgrade() -> None:
    op.drop_column("provider_configs", "visible_to_orgs")
