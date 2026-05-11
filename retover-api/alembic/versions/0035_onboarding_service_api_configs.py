"""onboarding service api configs

Revision ID: 0035_onboarding_service_api_configs
Revises: 0034_agent_definitions
"""

from __future__ import annotations

import uuid
from datetime import datetime

from alembic import op
import sqlalchemy as sa


revision = "0035_onboarding_service_api_configs"
down_revision = "0034_agent_definitions"
branch_labels = None
depends_on = None


CATEGORIES = [
    ("dental", "Dental clinic", "Dental clinics, hygiene, treatment follow-up and recall workflows."),
    ("aesthetics", "Aesthetics clinic", "Aesthetic, beauty, medspa and anti-aging clinics."),
    ("opticians", "Opticians / optometry", "Opticians, optometry and contact lens recall workflows."),
]

SERVICE_APIS = [
    ("dentally", "Dentally", "dental", "Dental practice management integration for appointments and patient context.", "active", True, True, "easy API", "Connect Dentally as the dental booking source of truth.", 10),
    ("carestack", "CareStack", "dental", "Dental practice management integration for larger dental groups.", "coming soon", False, False, "beta", "CareStack support is planned for dental groups.", 20),
    ("pabau", "Pabau", "aesthetics", "Aesthetics and medspa practice software integration.", "coming soon", False, True, "beta", "Pabau support will power aesthetics appointment recovery.", 10),
    ("cliniko", "Cliniko", "aesthetics", "Clinic booking software integration for appointments and client context.", "coming soon", False, False, "beta", "Cliniko support is planned for clinic appointment recovery.", 20),
    ("optix", "Optix", "opticians", "Optician practice management integration for appointments and recalls.", "coming soon", False, True, "beta", "Optix support will power optometry recall workflows.", 10),
    ("ocuco", "Ocuco", "opticians", "Optometry and optical retail software integration.", "coming soon", False, False, "beta", "Ocuco support is planned for opticians and optometry groups.", 20),
]


def _has_column(inspector: sa.Inspector, table: str, column: str) -> bool:
    return any(c["name"] == column for c in inspector.get_columns(table))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "supported_service_apis" not in tables:
        op.create_table(
            "supported_service_apis",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("slug", sa.String(length=80), nullable=False),
            sa.Column("display_name", sa.String(length=160), nullable=False),
            sa.Column("category_slug", sa.String(length=80), nullable=False),
            sa.Column("short_description", sa.Text(), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column("is_recommended", sa.Boolean(), nullable=False, server_default=sa.text("0")),
            sa.Column("api_difficulty", sa.String(length=40), nullable=True),
            sa.Column("docs_text", sa.Text(), nullable=True),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("100")),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["category_slug"], ["categories.slug"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("slug", name="uq_supported_service_apis_slug"),
        )
        op.create_index("ix_supported_service_apis_slug", "supported_service_apis", ["slug"])
        op.create_index("ix_supported_service_apis_category_slug", "supported_service_apis", ["category_slug"])
        op.create_index("ix_supported_service_apis_status", "supported_service_apis", ["status"])
        op.create_index("ix_supported_service_apis_is_active", "supported_service_apis", ["is_active"])

    columns = {c["name"] for c in inspector.get_columns("organisations")}
    if "onboarding_state" not in columns:
        op.add_column("organisations", sa.Column("onboarding_state", sa.String(length=40), nullable=False, server_default="account_created"))
        op.create_index("ix_organisations_onboarding_state", "organisations", ["onboarding_state"])
    if "onboarding_completed_at" not in columns:
        op.add_column("organisations", sa.Column("onboarding_completed_at", sa.DateTime(), nullable=True))
    if "onboarding_version" not in columns:
        op.add_column("organisations", sa.Column("onboarding_version", sa.String(length=40), nullable=True))
    if "booking_software_slug" not in columns:
        op.add_column("organisations", sa.Column("booking_software_slug", sa.String(length=80), nullable=True))
        op.create_index("ix_organisations_booking_software_slug", "organisations", ["booking_software_slug"])
        try:
            op.create_foreign_key(
                "fk_organisations_booking_software_slug_supported_service_apis",
                "organisations",
                "supported_service_apis",
                ["booking_software_slug"],
                ["slug"],
            )
        except Exception:
            pass

    if "organisation_ai_identities" not in tables:
        op.create_table(
            "organisation_ai_identities",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("org_id", sa.String(length=36), nullable=False),
            sa.Column("assistant_name", sa.String(length=120), nullable=False, server_default="VOXBULK Assistant"),
            sa.Column("organisation_name", sa.String(length=255), nullable=True),
            sa.Column("tone", sa.String(length=40), nullable=False, server_default="professional"),
            sa.Column("humor_level", sa.String(length=20), nullable=False, server_default="none"),
            sa.Column("languages_json", sa.Text(), nullable=False, server_default='["en-GB"]'),
            sa.Column("terminology_label", sa.String(length=40), nullable=False, server_default="patient"),
            sa.Column("disclose_ai", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["org_id"], ["organisations.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("org_id", name="uq_organisation_ai_identities_org"),
        )
        op.create_index("ix_organisation_ai_identities_org_id", "organisation_ai_identities", ["org_id"])

    if "organisation_compliance_configs" not in tables:
        op.create_table(
            "organisation_compliance_configs",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("org_id", sa.String(length=36), nullable=False),
            sa.Column("outbound_call_windows_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("whatsapp_windows_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("weekend_allowed", sa.Boolean(), nullable=False, server_default=sa.text("0")),
            sa.Column("ai_disclosure_wording", sa.Text(), nullable=True),
            sa.Column("opt_out_wording", sa.Text(), nullable=True),
            sa.Column("escalation_destination", sa.String(length=255), nullable=True),
            sa.Column("contact_preference_rules_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["org_id"], ["organisations.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("org_id", name="uq_organisation_compliance_configs_org"),
        )
        op.create_index("ix_organisation_compliance_configs_org_id", "organisation_compliance_configs", ["org_id"])

    if "organisation_service_catalog_items" not in tables:
        op.create_table(
            "organisation_service_catalog_items",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("org_id", sa.String(length=36), nullable=False),
            sa.Column("name", sa.String(length=160), nullable=False),
            sa.Column("category_slug", sa.String(length=80), nullable=False),
            sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("0")),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["category_slug"], ["categories.slug"]),
            sa.ForeignKeyConstraint(["org_id"], ["organisations.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("org_id", "name", name="uq_organisation_service_catalog_org_name"),
        )
        op.create_index("ix_organisation_service_catalog_items_org_id", "organisation_service_catalog_items", ["org_id"])
        op.create_index("ix_organisation_service_catalog_items_category_slug", "organisation_service_catalog_items", ["category_slug"])

    if "organisation_workflow_configs" not in tables:
        op.create_table(
            "organisation_workflow_configs",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("org_id", sa.String(length=36), nullable=False),
            sa.Column("workflow_key", sa.String(length=80), nullable=False),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column("channels_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("timing_rules_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("allowed_actions_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("forbidden_actions_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("escalation_rules_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("generated_profile_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("generated_prompt_preview", sa.Text(), nullable=True),
            sa.Column("workflow_summary_preview", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["org_id"], ["organisations.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("org_id", "workflow_key", name="uq_organisation_workflow_configs_org_workflow"),
        )
        op.create_index("ix_organisation_workflow_configs_org_id", "organisation_workflow_configs", ["org_id"])
        op.create_index("ix_organisation_workflow_configs_workflow_key", "organisation_workflow_configs", ["workflow_key"])

    now = datetime.utcnow()
    for slug, name, desc in CATEGORIES:
        exists = bind.execute(sa.text("select id from categories where slug = :slug"), {"slug": slug}).fetchone()
        if exists is None:
            bind.execute(
                sa.text("insert into categories (id, slug, name, description, created_at) values (:id, :slug, :name, :description, :created_at)"),
                {"id": str(uuid.uuid4()), "slug": slug, "name": name, "description": desc, "created_at": now},
            )

    for row in SERVICE_APIS:
        exists = bind.execute(sa.text("select id from supported_service_apis where slug = :slug"), {"slug": row[0]}).fetchone()
        if exists is None:
            bind.execute(
                sa.text(
                    """
                    insert into supported_service_apis
                    (id, slug, display_name, category_slug, short_description, status, is_active, is_recommended, api_difficulty, docs_text, sort_order, created_at, updated_at)
                    values
                    (:id, :slug, :display_name, :category_slug, :short_description, :status, :is_active, :is_recommended, :api_difficulty, :docs_text, :sort_order, :created_at, :updated_at)
                    """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "slug": row[0],
                    "display_name": row[1],
                    "category_slug": row[2],
                    "short_description": row[3],
                    "status": row[4],
                    "is_active": row[5],
                    "is_recommended": row[6],
                    "api_difficulty": row[7],
                    "docs_text": row[8],
                    "sort_order": row[9],
                    "created_at": now,
                    "updated_at": now,
                },
            )


def downgrade() -> None:
    op.drop_index("ix_organisation_workflow_configs_workflow_key", table_name="organisation_workflow_configs")
    op.drop_index("ix_organisation_workflow_configs_org_id", table_name="organisation_workflow_configs")
    op.drop_table("organisation_workflow_configs")
    op.drop_index("ix_organisation_service_catalog_items_category_slug", table_name="organisation_service_catalog_items")
    op.drop_index("ix_organisation_service_catalog_items_org_id", table_name="organisation_service_catalog_items")
    op.drop_table("organisation_service_catalog_items")
    op.drop_index("ix_organisation_compliance_configs_org_id", table_name="organisation_compliance_configs")
    op.drop_table("organisation_compliance_configs")
    op.drop_index("ix_organisation_ai_identities_org_id", table_name="organisation_ai_identities")
    op.drop_table("organisation_ai_identities")
    try:
        op.drop_constraint("fk_organisations_booking_software_slug_supported_service_apis", "organisations", type_="foreignkey")
    except Exception:
        pass
    op.drop_index("ix_organisations_booking_software_slug", table_name="organisations")
    op.drop_column("organisations", "booking_software_slug")
    op.drop_column("organisations", "onboarding_version")
    op.drop_column("organisations", "onboarding_completed_at")
    op.drop_index("ix_organisations_onboarding_state", table_name="organisations")
    op.drop_column("organisations", "onboarding_state")
    op.drop_index("ix_supported_service_apis_is_active", table_name="supported_service_apis")
    op.drop_index("ix_supported_service_apis_status", table_name="supported_service_apis")
    op.drop_index("ix_supported_service_apis_category_slug", table_name="supported_service_apis")
    op.drop_index("ix_supported_service_apis_slug", table_name="supported_service_apis")
    op.drop_table("supported_service_apis")

