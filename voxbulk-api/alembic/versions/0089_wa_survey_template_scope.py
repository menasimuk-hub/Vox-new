"""Backfill survey_type_id on templates and dedupe mistaken template links."""

from alembic import op
import sqlalchemy as sa

revision = "0089_wa_survey_template_scope"
down_revision = "0088_wa_survey_step_role"
branch_labels = None
depends_on = None


def _upgrade_sqlite(conn) -> None:
    rows = conn.execute(sa.text("SELECT id, slug FROM survey_types")).fetchall()
    for st_id, slug in rows:
        slug_l = str(slug or "").strip().lower()
        if not slug_l:
            continue
        prefix = f"voxbulk_survey_{slug_l}_%"
        conn.execute(
            sa.text(
                """
                UPDATE telnyx_whatsapp_templates
                SET survey_type_id = :st_id
                WHERE survey_type_id IS NULL AND LOWER(name) LIKE :prefix
                """
            ),
            {"st_id": st_id, "prefix": prefix},
        )
    conn.execute(
        sa.text(
            """
            DELETE FROM survey_type_templates
            WHERE rowid IN (
                SELECT stt.rowid FROM survey_type_templates stt
                INNER JOIN survey_types st ON st.id = stt.survey_type_id
                INNER JOIN telnyx_whatsapp_templates t ON t.id = stt.template_id
                WHERE t.survey_type_id IS NOT NULL AND t.survey_type_id <> stt.survey_type_id
            )
            """
        )
    )
    for st_id, slug in rows:
        slug_l = str(slug or "").strip().lower()
        if not slug_l:
            continue
        prefix = f"voxbulk_survey_{slug_l}_%"
        legacy_std = f"voxbulk_survey_{slug_l}_standard"
        legacy_anon = f"voxbulk_survey_{slug_l}_anonymous"
        conn.execute(
            sa.text(
                """
                DELETE FROM survey_type_templates
                WHERE rowid IN (
                    SELECT stt.rowid FROM survey_type_templates stt
                    INNER JOIN survey_types st ON st.id = stt.survey_type_id
                    INNER JOIN telnyx_whatsapp_templates t ON t.id = stt.template_id
                    WHERE stt.survey_type_id = :st_id
                      AND t.survey_type_id IS NULL
                      AND LOWER(t.name) NOT LIKE :prefix
                      AND LOWER(t.name) NOT IN (:legacy_std, :legacy_anon)
                )
                """
            ),
            {
                "st_id": st_id,
                "prefix": prefix,
                "legacy_std": legacy_std,
                "legacy_anon": legacy_anon,
            },
        )


def _upgrade_mysql(conn) -> None:
    conn.execute(
        sa.text(
            """
            UPDATE telnyx_whatsapp_templates t
            INNER JOIN survey_types st ON LOWER(t.name) REGEXP CONCAT('^voxbulk_survey_', st.slug, '(_|$)')
            SET t.survey_type_id = st.id
            WHERE t.survey_type_id IS NULL
            """
        )
    )
    conn.execute(
        sa.text(
            """
            DELETE stt FROM survey_type_templates stt
            INNER JOIN survey_types st ON st.id = stt.survey_type_id
            INNER JOIN telnyx_whatsapp_templates t ON t.id = stt.template_id
            WHERE t.survey_type_id IS NOT NULL
              AND t.survey_type_id <> stt.survey_type_id
            """
        )
    )
    conn.execute(
        sa.text(
            """
            DELETE stt FROM survey_type_templates stt
            INNER JOIN survey_types st ON st.id = stt.survey_type_id
            INNER JOIN telnyx_whatsapp_templates t ON t.id = stt.template_id
            WHERE t.survey_type_id IS NULL
              AND LOWER(t.name) NOT REGEXP CONCAT('^voxbulk_survey_', st.slug, '(_|$)')
              AND LOWER(t.name) NOT REGEXP CONCAT('^voxbulk_survey_', st.slug, '_(standard|anonymous)$')
            """
        )
    )


def upgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name == "sqlite":
        _upgrade_sqlite(conn)
    else:
        _upgrade_mysql(conn)


def downgrade() -> None:
    pass
