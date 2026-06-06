"""UK compliance fields on email templates + org compliance backfill."""

from alembic import op
import sqlalchemy as sa

revision = "0100_email_template_compliance_fields"
down_revision = "0099_industry_deletion_tombstones"
branch_labels = None
depends_on = None

DEFAULT_PRIVACY_URL = "https://www.voxbulk.com/privacy"
DEFAULT_CONTACT_EMAIL = "Data.Pro@voxbulk.com"
DEFAULT_LAWFUL_BASIS = "legitimate_interests"


def _column_exists(conn, table: str, column: str) -> bool:
    if conn.dialect.name == "sqlite":
        rows = conn.execute(sa.text(f"PRAGMA table_info({table})")).fetchall()
        return any(str(r[1]) == column for r in rows)
    return (
        conn.execute(
            sa.text(
                "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t AND COLUMN_NAME = :c"
            ),
            {"t": table, "c": column},
        ).fetchone()
        is not None
    )


def _table_exists(conn, name: str) -> bool:
    if conn.dialect.name == "sqlite":
        return (
            conn.execute(
                sa.text("SELECT name FROM sqlite_master WHERE type='table' AND name=:n"),
                {"n": name},
            ).fetchone()
            is not None
        )
    return (
        conn.execute(
            sa.text(
                "SELECT TABLE_NAME FROM information_schema.TABLES "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :n"
            ),
            {"n": name},
        ).fetchone()
        is not None
    )


def upgrade() -> None:
    conn = op.get_bind()
    for name, col_type in (
        ("lawful_basis", sa.String(32)),
        ("privacy_notice_url", sa.String(512)),
        ("contact_email", sa.String(255)),
    ):
        if not _column_exists(conn, "email_templates", name):
            op.add_column("email_templates", sa.Column(name, col_type, nullable=True))

    conn.execute(
        sa.text(
            "UPDATE email_templates SET "
            "lawful_basis = COALESCE(lawful_basis, :basis), "
            "privacy_notice_url = COALESCE(privacy_notice_url, :url), "
            "contact_email = COALESCE(contact_email, :email)"
        ),
        {"basis": DEFAULT_LAWFUL_BASIS, "url": DEFAULT_PRIVACY_URL, "email": DEFAULT_CONTACT_EMAIL},
    )

    if _table_exists(conn, "organisations") and _table_exists(conn, "organisation_compliance_configs"):
        if conn.dialect.name == "sqlite":
            conn.execute(
                sa.text(
                    """
                    INSERT INTO organisation_compliance_configs (
                        id, org_id, outbound_call_windows_json, whatsapp_windows_json,
                        weekend_allowed, contact_preference_rules_json,
                        privacy_notice_url, contact_email, opt_out_enabled,
                        lawful_basis_default, special_category_data_present_default,
                        collect_minimal_data_default,
                        retention_days_messages, retention_days_responses,
                        retention_days_recordings, retention_days_transcripts,
                        created_at, updated_at
                    )
                    SELECT
                        lower(hex(randomblob(4)) || '-' || hex(randomblob(2)) || '-4' || substr(hex(randomblob(2)),2) || '-'
                            || substr('89ab', abs(random()) % 4 + 1, 1) || substr(hex(randomblob(2)),2) || '-'
                            || hex(randomblob(6))),
                        o.id,
                        '{"weekdays": {"start": "09:00", "end": "18:00"}}',
                        '{"weekdays": {"start": "09:00", "end": "18:00"}}',
                        0,
                        '{"respect_do_not_contact": true, "prefer_existing_customer_channel": true}',
                        :url,
                        :email,
                        1,
                        :basis,
                        0,
                        1,
                        365,
                        730,
                        90,
                        365,
                        CURRENT_TIMESTAMP,
                        CURRENT_TIMESTAMP
                    FROM organisations o
                    WHERE NOT EXISTS (
                        SELECT 1 FROM organisation_compliance_configs c WHERE c.org_id = o.id
                    )
                    """
                ),
                {"url": DEFAULT_PRIVACY_URL, "email": DEFAULT_CONTACT_EMAIL, "basis": DEFAULT_LAWFUL_BASIS},
            )
        else:
            conn.execute(
                sa.text(
                    """
                    INSERT INTO organisation_compliance_configs (
                        id, org_id, outbound_call_windows_json, whatsapp_windows_json,
                        weekend_allowed, contact_preference_rules_json,
                        privacy_notice_url, contact_email, opt_out_enabled,
                        lawful_basis_default, special_category_data_present_default,
                        collect_minimal_data_default,
                        retention_days_messages, retention_days_responses,
                        retention_days_recordings, retention_days_transcripts,
                        created_at, updated_at
                    )
                    SELECT
                        UUID(),
                        o.id,
                        '{"weekdays": {"start": "09:00", "end": "18:00"}}',
                        '{"weekdays": {"start": "09:00", "end": "18:00"}}',
                        FALSE,
                        '{"respect_do_not_contact": true, "prefer_existing_customer_channel": true}',
                        :url,
                        :email,
                        TRUE,
                        :basis,
                        FALSE,
                        TRUE,
                        365,
                        730,
                        90,
                        365,
                        UTC_TIMESTAMP(),
                        UTC_TIMESTAMP()
                    FROM organisations o
                    LEFT JOIN organisation_compliance_configs c ON c.org_id = o.id
                    WHERE c.id IS NULL
                    """
                ),
                {"url": DEFAULT_PRIVACY_URL, "email": DEFAULT_CONTACT_EMAIL, "basis": DEFAULT_LAWFUL_BASIS},
            )

        conn.execute(
            sa.text(
                "UPDATE organisation_compliance_configs SET "
                "privacy_notice_url = COALESCE(privacy_notice_url, :url), "
                "contact_email = COALESCE(contact_email, :email), "
                "lawful_basis_default = COALESCE(lawful_basis_default, :basis), "
                "opt_out_enabled = COALESCE(opt_out_enabled, TRUE), "
                "collect_minimal_data_default = COALESCE(collect_minimal_data_default, TRUE), "
                "retention_days_messages = COALESCE(retention_days_messages, 365), "
                "retention_days_responses = COALESCE(retention_days_responses, 730), "
                "retention_days_recordings = COALESCE(retention_days_recordings, 90), "
                "retention_days_transcripts = COALESCE(retention_days_transcripts, 365)"
            ),
            {"url": DEFAULT_PRIVACY_URL, "email": DEFAULT_CONTACT_EMAIL, "basis": DEFAULT_LAWFUL_BASIS},
        )


def downgrade() -> None:
    conn = op.get_bind()
    for name in ("contact_email", "privacy_notice_url", "lawful_basis"):
        if _column_exists(conn, "email_templates", name):
            op.drop_column("email_templates", name)
