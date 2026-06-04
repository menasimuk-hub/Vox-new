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


def upgrade() -> None:
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

    import uuid

    conn = op.get_bind()
    general_id = None
    for slug, name, sort_order in DEFAULT_INDUSTRIES:
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

    op.add_column("survey_types", sa.Column("industry_id", sa.String(36), nullable=True))
    if general_id:
        conn.execute(
            sa.text("UPDATE survey_types SET industry_id = :gid WHERE industry_id IS NULL"),
            {"gid": general_id},
        )
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

    op.add_column("telnyx_whatsapp_templates", sa.Column("industry_id", sa.String(36), nullable=True))
    conn.execute(
        sa.text(
            """
            UPDATE telnyx_whatsapp_templates t
            INNER JOIN survey_types st ON st.id = t.survey_type_id
            SET t.industry_id = st.industry_id
            WHERE t.survey_type_id IS NOT NULL AND t.industry_id IS NULL
            """
        )
    )
    op.create_foreign_key(
        "fk_telnyx_wa_tpl_industry_id",
        "telnyx_whatsapp_templates",
        "industries",
        ["industry_id"],
        ["id"],
    )
    op.create_index("ix_telnyx_whatsapp_templates_industry_id", "telnyx_whatsapp_templates", ["industry_id"])

    op.add_column("survey_type_templates", sa.Column("industry_id", sa.String(36), nullable=True))
    conn.execute(
        sa.text(
            """
            UPDATE survey_type_templates m
            INNER JOIN survey_types st ON st.id = m.survey_type_id
            SET m.industry_id = st.industry_id
            WHERE m.industry_id IS NULL
            """
        )
    )
    op.alter_column("survey_type_templates", "industry_id", existing_type=sa.String(36), nullable=False)
    op.create_foreign_key(
        "fk_survey_type_templates_industry_id",
        "survey_type_templates",
        "industries",
        ["industry_id"],
        ["id"],
    )
    op.create_index("ix_survey_type_templates_industry_id", "survey_type_templates", ["industry_id"])

    op.add_column("survey_template_packs", sa.Column("industry_id", sa.String(36), nullable=True))
    conn.execute(
        sa.text(
            """
            UPDATE survey_template_packs p
            INNER JOIN survey_types st ON st.id = p.survey_type_id
            SET p.industry_id = st.industry_id
            WHERE p.industry_id IS NULL
            """
        )
    )
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
    op.drop_index("ix_survey_template_packs_industry_id", table_name="survey_template_packs")
    op.drop_constraint("fk_survey_template_packs_industry_id", "survey_template_packs", type_="foreignkey")
    op.drop_column("survey_template_packs", "industry_id")

    op.drop_index("ix_survey_type_templates_industry_id", table_name="survey_type_templates")
    op.drop_constraint("fk_survey_type_templates_industry_id", "survey_type_templates", type_="foreignkey")
    op.drop_column("survey_type_templates", "industry_id")

    op.drop_index("ix_telnyx_whatsapp_templates_industry_id", table_name="telnyx_whatsapp_templates")
    op.drop_constraint("fk_telnyx_wa_tpl_industry_id", "telnyx_whatsapp_templates", type_="foreignkey")
    op.drop_column("telnyx_whatsapp_templates", "industry_id")

    op.drop_constraint("uq_survey_types_industry_slug", "survey_types", type_="unique")
    op.create_unique_constraint("survey_types_slug_key", "survey_types", ["slug"])
    op.drop_index("ix_survey_types_industry_id", table_name="survey_types")
    op.drop_constraint("fk_survey_types_industry_id", "survey_types", type_="foreignkey")
    op.drop_column("survey_types", "industry_id")

    op.drop_index("ix_industries_slug", table_name="industries")
    op.drop_table("industries")
