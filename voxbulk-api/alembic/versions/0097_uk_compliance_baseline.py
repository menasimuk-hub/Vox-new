"""UK GDPR / PECR / DPA 2018 compliance baseline columns and audit table."""

from alembic import op
import sqlalchemy as sa

revision = "0097_uk_compliance_baseline"
down_revision = "0096_survey_types_slug_scope_fix"
branch_labels = None
depends_on = None


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
    cols = [
        ("privacy_notice_url", sa.String(512)),
        ("contact_email", sa.String(255)),
        ("dpo_email", sa.String(255)),
        ("opt_out_enabled", sa.Boolean()),
        ("lawful_basis_default", sa.String(32)),
        ("special_category_data_present_default", sa.Boolean()),
        ("article9_condition_default", sa.String(64)),
        ("privacy_intro_text_default", sa.Text()),
        ("collect_minimal_data_default", sa.Boolean()),
        ("retention_days_messages", sa.Integer()),
        ("retention_days_responses", sa.Integer()),
        ("retention_days_recordings", sa.Integer()),
        ("retention_days_transcripts", sa.Integer()),
    ]
    for name, col_type in cols:
        if not _column_exists(conn, "organisation_compliance_configs", name):
            op.add_column("organisation_compliance_configs", sa.Column(name, col_type, nullable=True))

    conn.execute(
        sa.text(
            "UPDATE organisation_compliance_configs SET "
            "privacy_notice_url = COALESCE(privacy_notice_url, 'https://www.voxbulk.com/privacy'), "
            "contact_email = COALESCE(contact_email, 'Data.Pro@voxbulk.com'), "
            "lawful_basis_default = COALESCE(lawful_basis_default, 'legitimate_interests'), "
            "opt_out_enabled = COALESCE(opt_out_enabled, 1), "
            "collect_minimal_data_default = COALESCE(collect_minimal_data_default, 1), "
            "retention_days_messages = COALESCE(retention_days_messages, 365), "
            "retention_days_responses = COALESCE(retention_days_responses, 730), "
            "retention_days_recordings = COALESCE(retention_days_recordings, 90), "
            "retention_days_transcripts = COALESCE(retention_days_transcripts, 365)"
        )
    )
    if conn.dialect.name == "sqlite":
        conn.execute(
            sa.text(
                "UPDATE organisation_compliance_configs SET opt_out_enabled = 1 "
                "WHERE opt_out_enabled IS NULL"
            )
        )
        conn.execute(
            sa.text(
                "UPDATE organisation_compliance_configs SET collect_minimal_data_default = 1 "
                "WHERE collect_minimal_data_default IS NULL"
            )
        )
        conn.execute(
            sa.text(
                "UPDATE organisation_compliance_configs SET special_category_data_present_default = 0 "
                "WHERE special_category_data_present_default IS NULL"
            )
        )
    else:
        op.execute(
            sa.text(
                "UPDATE organisation_compliance_configs SET opt_out_enabled = TRUE "
                "WHERE opt_out_enabled IS NULL"
            )
        )

    if not _table_exists(conn, "platform_compliance_audit_events"):
        # MySQL rejects DEFAULT on TEXT/BLOB (error 1101); app always sets detail_json on insert.
        detail_col = sa.Column("detail_json", sa.Text(), nullable=False)
        if conn.dialect.name == "sqlite":
            detail_col = sa.Column("detail_json", sa.Text(), nullable=False, server_default="{}")
        op.create_table(
            "platform_compliance_audit_events",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("event_type", sa.String(64), nullable=False),
            sa.Column("org_id", sa.String(36), sa.ForeignKey("organisations.id"), nullable=True),
            sa.Column("actor_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("order_id", sa.String(36), sa.ForeignKey("service_orders.id"), nullable=True),
            sa.Column("resource_type", sa.String(32), nullable=True),
            sa.Column("resource_id", sa.String(64), nullable=True),
            detail_col,
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        op.create_index("ix_pca_events_type", "platform_compliance_audit_events", ["event_type"])
        op.create_index("ix_pca_events_org", "platform_compliance_audit_events", ["org_id"])
        op.create_index("ix_pca_events_order", "platform_compliance_audit_events", ["order_id"])
        op.create_index("ix_pca_events_created", "platform_compliance_audit_events", ["created_at"])


def downgrade() -> None:
    conn = op.get_bind()
    if _table_exists(conn, "platform_compliance_audit_events"):
        op.drop_table("platform_compliance_audit_events")
    for name in (
        "retention_days_transcripts",
        "retention_days_recordings",
        "retention_days_responses",
        "retention_days_messages",
        "collect_minimal_data_default",
        "privacy_intro_text_default",
        "article9_condition_default",
        "special_category_data_present_default",
        "lawful_basis_default",
        "opt_out_enabled",
        "dpo_email",
        "contact_email",
        "privacy_notice_url",
    ):
        if _column_exists(conn, "organisation_compliance_configs", name):
            op.drop_column("organisation_compliance_configs", name)
