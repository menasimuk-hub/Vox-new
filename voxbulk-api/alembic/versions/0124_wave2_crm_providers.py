"""Alembic migration: Wave 2 CRM columns + provider_configs seed."""

from __future__ import annotations

import json
from datetime import datetime

import sqlalchemy as sa
from alembic import op

revision = "0124_wave2_crm_providers"
down_revision = "0123_provider_config_visible_to_orgs"
branch_labels = None
depends_on = None

_WAVE2_PROVIDERS = ("pipedrive", "zoho_crm", "zoho_bookings")


def _encrypt_stub() -> str:
    try:
        from app.core.encryption import get_encryptor

        return get_encryptor().encrypt_str(json.dumps({}, ensure_ascii=False, separators=(",", ":")))
    except Exception:
        return json.dumps({}, ensure_ascii=False, separators=(",", ":"))


def upgrade() -> None:
    op.add_column("organisations", sa.Column("pipedrive_config_json", sa.Text(), nullable=True))
    op.add_column("organisations", sa.Column("zoho_crm_config_json", sa.Text(), nullable=True))

    bind = op.get_bind()
    cipher = _encrypt_stub()
    now = datetime.utcnow()
    for provider in _WAVE2_PROVIDERS:
        existing = bind.execute(
            sa.text(
                "SELECT id FROM provider_configs WHERE scope='platform' AND provider=:provider LIMIT 1"
            ),
            {"provider": provider},
        ).fetchone()
        if existing is not None:
            continue
        bind.execute(
            sa.text(
                "INSERT INTO provider_configs (scope, org_id, provider, is_enabled, visible_to_orgs, "
                "encrypted_json, created_at, updated_at) VALUES (:scope, NULL, :provider, :is_enabled, "
                ":visible_to_orgs, :encrypted_json, :created_at, :updated_at)"
            ),
            {
                "scope": "platform",
                "provider": provider,
                "is_enabled": False,
                "visible_to_orgs": False,
                "encrypted_json": cipher,
                "created_at": now,
                "updated_at": now,
            },
        )


def downgrade() -> None:
    bind = op.get_bind()
    for provider in _WAVE2_PROVIDERS:
        bind.execute(
            sa.text("DELETE FROM provider_configs WHERE scope='platform' AND provider=:provider"),
            {"provider": provider},
        )
    op.drop_column("organisations", "zoho_crm_config_json")
    op.drop_column("organisations", "pipedrive_config_json")
