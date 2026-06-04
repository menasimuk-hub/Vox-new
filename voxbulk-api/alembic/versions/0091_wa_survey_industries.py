"""Add industries dimension and industry_id FKs for WA Survey."""

from alembic import op
import sqlalchemy as sa

revision = "0091_wa_survey_industries"
down_revision = "0090_wa_template_privacy_mode"
branch_labels = None
depends_on = None

DEFAULT_INDUSTRIES = [
    ("healthcare", "Healthcare", 10),
    ("ecommerce", "E-commerce", 20),
    ("finance", "Finance", 30),
    ("hospitality", "Hospitality", 40),
    ("education", "Education", 50),
    ("saas", "SaaS / Technology", 60),
    ("general", "General / Other", 90),
]


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


def _seed_industries(conn) -> str | None:
    import uuid

    general_id = None
    for slug, name, sort_order in DEFAULT_INDUSTRIES:
        existing = conn.execute(
            sa.text("SELECT id FROM industries WHERE slug = :slug"),
            {"slug": slug},
        ).fetchone()
        if existing:
            if slug == "general":
                general_id = existing[0]
            continue
        iid = str(uuid.uuid4())
        conn.execute(
            sa.text(
                "INSERT INTO industries (id, slug, name, sort_order, is_active) "
                "VALUES (:id, :slug, :name, :sort_order, 1)"
            ),
            {"id": iid, "slug": slug, "name": name, "sort_order": sort_order},
        )
        if slug == "general":
            general_id = iid
    if general_id is None:
        row = conn.execute(sa.text("SELECT id FROM industries WHERE slug = 'general' LIMIT 1")).fetchone()
        general_id = row[0] if row else None
    return general_id


def _backfill_industry_id(conn, *, table: str, join_col: str) -> None:
    conn.execute(
        sa.text(
            f"""
            UPDATE {table}
            SET industry_id = (
                SELECT st.industry_id FROM survey_types st
                WHERE st.id = {table}.{join_col}
            )
            WHERE {join_col} IS NOT NULL AND industry_id IS NULL
            """
        )
    )


def upgrade() -> None:
    import uuid

    conn = op.get_bind()
    is_sqlite = conn.dialect.name == "sqlite"

    if not _table_exists(conn, "industries"):
        op.create_table(
            "industries",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("slug", sa.String(64), nullable=False),
            sa.Column("name", sa.String(128), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="100"),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        op.create_index("ix_industries_slug", "industries", ["slug"], unique=True)
    else:
        conn.execute(
            sa.text("CREATE UNIQUE INDEX IF NOT EXISTS ix_industries_slug ON industries (slug)")
        )

    general_id = _seed_industries(conn)

    if not _column_exists(conn, "survey_types", "industry_id"):
        op.add_column("survey_types", sa.Column("industry_id", sa.String(36), nullable=True))

    if general_id:
        conn.execute(
            sa.text("UPDATE survey_types SET industry_id = :gid WHERE industry_id IS NULL"),
            {"gid": general_id},
        )

    if is_sqlite:
        with op.batch_alter_table("survey_types") as batch_op:
            batch_op.alter_column("industry_id", existing_type=sa.String(36), nullable=False)
            try:
                batch_op.create_unique_constraint("uq_survey_types_industry_slug", ["industry_id", "slug"])
            except Exception:
                pass
    else:
        op.alter_column("survey_types", "industry_id", existing_type=sa.String(36), nullable=False)
        op.create_foreign_key(
            "fk_survey_types_industry_id",
            "survey_types",
            "industries",
            ["industry_id"],
            ["id"],
        )
        op.create_index("ix_survey_types_industry_id", "survey_types", ["industry_id"])
        try:
            op.drop_constraint("survey_types_slug_key", "survey_types", type_="unique")
        except Exception:
            try:
                op.drop_index("ix_survey_types_slug", table_name="survey_types")
            except Exception:
                pass
        op.create_unique_constraint("uq_survey_types_industry_slug", "survey_types", ["industry_id", "slug"])

    if not _column_exists(conn, "telnyx_whatsapp_templates", "industry_id"):
        if is_sqlite:
            with op.batch_alter_table("telnyx_whatsapp_templates") as batch_op:
                batch_op.add_column(sa.Column("industry_id", sa.String(36), nullable=True))
        else:
            op.add_column("telnyx_whatsapp_templates", sa.Column("industry_id", sa.String(36), nullable=True))
    _backfill_industry_id(conn, table="telnyx_whatsapp_templates", join_col="survey_type_id")
    if not is_sqlite:
        op.create_foreign_key(
            "fk_telnyx_wa_tpl_industry_id",
            "telnyx_whatsapp_templates",
            "industries",
            ["industry_id"],
            ["id"],
        )
        op.create_index("ix_telnyx_whatsapp_templates_industry_id", "telnyx_whatsapp_templates", ["industry_id"])

    if not _column_exists(conn, "survey_type_templates", "industry_id"):
        if is_sqlite:
            with op.batch_alter_table("survey_type_templates") as batch_op:
                batch_op.add_column(sa.Column("industry_id", sa.String(36), nullable=True))
        else:
            op.add_column("survey_type_templates", sa.Column("industry_id", sa.String(36), nullable=True))
    _backfill_industry_id(conn, table="survey_type_templates", join_col="survey_type_id")
    if is_sqlite:
        with op.batch_alter_table("survey_type_templates") as batch_op:
            batch_op.alter_column("industry_id", existing_type=sa.String(36), nullable=False)
    else:
        op.alter_column("survey_type_templates", "industry_id", existing_type=sa.String(36), nullable=False)
        op.create_foreign_key(
            "fk_survey_type_templates_industry_id",
            "survey_type_templates",
            "industries",
            ["industry_id"],
            ["id"],
        )
        op.create_index("ix_survey_type_templates_industry_id", "survey_type_templates", ["industry_id"])

    if not _column_exists(conn, "survey_template_packs", "industry_id"):
        if is_sqlite:
            with op.batch_alter_table("survey_template_packs") as batch_op:
                batch_op.add_column(sa.Column("industry_id", sa.String(36), nullable=True))
        else:
            op.add_column("survey_template_packs", sa.Column("industry_id", sa.String(36), nullable=True))
    _backfill_industry_id(conn, table="survey_template_packs", join_col="survey_type_id")
    if is_sqlite:
        with op.batch_alter_table("survey_template_packs") as batch_op:
            batch_op.alter_column("industry_id", existing_type=sa.String(36), nullable=False)
    else:
        op.alter_column("survey_template_packs", "industry_id", existing_type=sa.String(36), nullable=False)
        op.create_foreign_key(
            "fk_survey_template_packs_industry_id",
            "survey_template_packs",
            "industries",
            ["industry_id"],
            ["id"],
        )
        op.create_index("ix_survey_template_packs_industry_id", "survey_template_packs", ["industry_id"])


def downgrade() -> None:
    conn = op.get_bind()
    is_sqlite = conn.dialect.name == "sqlite"

    if not is_sqlite:
        op.drop_index("ix_survey_template_packs_industry_id", table_name="survey_template_packs")
        op.drop_constraint("fk_survey_template_packs_industry_id", "survey_template_packs", type_="foreignkey")
    if _column_exists(conn, "survey_template_packs", "industry_id"):
        if is_sqlite:
            with op.batch_alter_table("survey_template_packs") as batch_op:
                batch_op.drop_column("industry_id")
        else:
            op.drop_column("survey_template_packs", "industry_id")

    if not is_sqlite:
        op.drop_index("ix_survey_type_templates_industry_id", table_name="survey_type_templates")
        op.drop_constraint("fk_survey_type_templates_industry_id", "survey_type_templates", type_="foreignkey")
    if _column_exists(conn, "survey_type_templates", "industry_id"):
        if is_sqlite:
            with op.batch_alter_table("survey_type_templates") as batch_op:
                batch_op.drop_column("industry_id")
        else:
            op.drop_column("survey_type_templates", "industry_id")

    if not is_sqlite:
        op.drop_index("ix_telnyx_whatsapp_templates_industry_id", table_name="telnyx_whatsapp_templates")
        op.drop_constraint("fk_telnyx_wa_tpl_industry_id", "telnyx_whatsapp_templates", type_="foreignkey")
    if _column_exists(conn, "telnyx_whatsapp_templates", "industry_id"):
        if is_sqlite:
            with op.batch_alter_table("telnyx_whatsapp_templates") as batch_op:
                batch_op.drop_column("industry_id")
        else:
            op.drop_column("telnyx_whatsapp_templates", "industry_id")

    if is_sqlite:
        with op.batch_alter_table("survey_types") as batch_op:
            try:
                batch_op.drop_constraint("uq_survey_types_industry_slug", type_="unique")
            except Exception:
                pass
            batch_op.drop_column("industry_id")
    else:
        op.drop_constraint("uq_survey_types_industry_slug", "survey_types", type_="unique")
        op.create_unique_constraint("survey_types_slug_key", "survey_types", ["slug"])
        op.drop_index("ix_survey_types_industry_id", table_name="survey_types")
        op.drop_constraint("fk_survey_types_industry_id", "survey_types", type_="foreignkey")
        op.drop_column("survey_types", "industry_id")

    op.drop_index("ix_industries_slug", table_name="industries")
    op.drop_table("industries")
