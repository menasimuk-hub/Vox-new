"""0153 — connection profiles tables + whatsapp_logs FK + seed from platform integrations."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0153_connection_profiles"
down_revision = "0152_admin_hidden_from_survey"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "connection_profiles",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("channel", sa.String(length=16), nullable=False),
        sa.Column("provider", sa.String(length=16), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("telnyx_api_key_encrypted", sa.Text(), nullable=True),
        sa.Column("telnyx_messaging_profile_id", sa.String(length=64), nullable=True),
        sa.Column("telnyx_number", sa.String(length=32), nullable=True),
        sa.Column("telnyx_connection_id", sa.String(length=64), nullable=True),
        sa.Column("telnyx_outbound_voice_profile_id", sa.String(length=128), nullable=True),
        sa.Column("meta_waba_id", sa.String(length=64), nullable=True),
        sa.Column("meta_phone_number_id", sa.String(length=64), nullable=True),
        sa.Column("meta_business_id", sa.String(length=64), nullable=True),
        sa.Column("meta_access_token_encrypted", sa.Text(), nullable=True),
        sa.Column("meta_app_secret_encrypted", sa.Text(), nullable=True),
        sa.Column("meta_webhook_verify_token_encrypted", sa.Text(), nullable=True),
        sa.Column("meta_whatsapp_from", sa.String(length=32), nullable=True),
        sa.Column("calling_number", sa.String(length=32), nullable=True),
        sa.Column("regions_json", sa.Text(), nullable=True),
        sa.Column("label", sa.String(length=128), nullable=True),
        sa.Column("last_test_at", sa.DateTime(), nullable=True),
        sa.Column("last_test_status", sa.String(length=32), nullable=True),
        sa.Column("last_test_detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_connection_profiles_channel", "connection_profiles", ["channel"])
    op.create_index("ix_connection_profiles_provider", "connection_profiles", ["provider"])
    op.create_index("ix_connection_profiles_is_default", "connection_profiles", ["is_default"])
    op.create_index("ix_connection_profiles_is_active", "connection_profiles", ["is_active"])
    op.create_index("ix_connection_profiles_telnyx_number", "connection_profiles", ["telnyx_number"])
    op.create_index("ix_connection_profiles_calling_number", "connection_profiles", ["calling_number"])

    op.create_table(
        "connection_profile_orgs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("profile_id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["organisations.id"]),
        sa.ForeignKeyConstraint(["profile_id"], ["connection_profiles.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("profile_id", "org_id", name="uq_connection_profile_org"),
    )
    op.create_index("ix_connection_profile_orgs_profile_id", "connection_profile_orgs", ["profile_id"])
    op.create_index("ix_connection_profile_orgs_org_id", "connection_profile_orgs", ["org_id"])

    op.create_table(
        "connection_profile_services",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("profile_id", sa.String(length=36), nullable=False),
        sa.Column("service_code", sa.String(length=32), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["profile_id"], ["connection_profiles.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("profile_id", "service_code", name="uq_connection_profile_service"),
    )
    op.create_index("ix_connection_profile_services_profile_id", "connection_profile_services", ["profile_id"])
    op.create_index("ix_connection_profile_services_service_code", "connection_profile_services", ["service_code"])

    op.add_column(
        "whatsapp_logs",
        sa.Column("connection_profile_id", sa.String(length=36), nullable=True),
    )
    op.create_foreign_key(
        "fk_whatsapp_logs_connection_profile_id",
        "whatsapp_logs",
        "connection_profiles",
        ["connection_profile_id"],
        ["id"],
    )
    op.create_index("ix_whatsapp_logs_connection_profile_id", "whatsapp_logs", ["connection_profile_id"])

    bind = op.get_bind()
    from sqlalchemy.orm import sessionmaker

    from app.services.connection.connection_profile_seed_service import ConnectionProfileSeedService

    db = sessionmaker(bind=bind)()
    try:
        ConnectionProfileSeedService.ensure_seeded(db)
    finally:
        db.close()


def downgrade() -> None:
    op.drop_index("ix_whatsapp_logs_connection_profile_id", table_name="whatsapp_logs")
    op.drop_constraint("fk_whatsapp_logs_connection_profile_id", "whatsapp_logs", type_="foreignkey")
    op.drop_column("whatsapp_logs", "connection_profile_id")
    op.drop_table("connection_profile_services")
    op.drop_table("connection_profile_orgs")
    op.drop_table("connection_profiles")
