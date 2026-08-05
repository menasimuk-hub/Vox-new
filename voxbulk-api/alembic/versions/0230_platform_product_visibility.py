"""Platform product visibility registry + FAQ linked_service.

Revision ID: 0230_platform_product_visibility
Revises: 0229_support_ticket_email_fingerprint

MySQL: TEXT columns must not use server_default (error 1101).
"""

from __future__ import annotations

import json
from datetime import datetime

import sqlalchemy as sa
from alembic import op

revision = "0230_platform_product_visibility"
down_revision = "0229_support_ticket_email_fingerprint"
branch_labels = None
depends_on = None

# Seed catalogue — all enabled so deploy does not hide existing public pages.
_DEFAULT_GROUPS = [
    {
        "key": "interview",
        "name": "Interview / Recruitment",
        "description": "AI recruitment automation and voice interviews.",
        "always_visible": False,
        "is_system": True,
        "sort_order": 10,
        "routes": ["/recruitment"],
        "faq_category_slugs": ["recruitment", "ai-calling"],
        "pricing_kinds": ["core"],
    },
    {
        "key": "survey",
        "name": "WhatsApp Surveys",
        "description": "WhatsApp survey product pages and related FAQ/pricing.",
        "always_visible": False,
        "is_system": True,
        "sort_order": 20,
        "routes": ["/surveys"],
        "faq_category_slugs": ["whatsapp-surveys"],
        "pricing_kinds": ["core"],
    },
    {
        "key": "customer_feedback",
        "name": "Customer Feedback",
        "description": "QR / WhatsApp customer feedback.",
        "always_visible": False,
        "is_system": True,
        "sort_order": 30,
        "routes": ["/feedback"],
        "faq_category_slugs": ["customer-feedback"],
        "pricing_kinds": ["feedback"],
    },
    {
        "key": "expo",
        "name": "VoxBulk Expo",
        "description": "Booth QR lead capture for exhibitions.",
        "always_visible": False,
        "is_system": True,
        "sort_order": 40,
        "routes": ["/expo"],
        "faq_category_slugs": ["expo"],
        "pricing_kinds": ["expo"],
    },
    {
        "key": "smart_card",
        "name": "Smart Card QR",
        "description": "Personal lead-capture QR per sales rep.",
        "always_visible": False,
        "is_system": True,
        "sort_order": 50,
        "routes": ["/smart-card"],
        "faq_category_slugs": [],
        "pricing_kinds": ["smart_card"],
    },
    {
        "key": "campaigns",
        "name": "Campaigns",
        "description": "Broadcast / campaign packs and related help content.",
        "always_visible": False,
        "is_system": True,
        "sort_order": 60,
        "routes": [],
        "faq_category_slugs": ["campaigns"],
        "pricing_kinds": ["campaign"],
    },
    {
        "key": "shared",
        "name": "Account, Billing & Support",
        "description": "Shared FAQ always visible on the public help centre.",
        "always_visible": True,
        "is_system": True,
        "sort_order": 100,
        "routes": [],
        "faq_category_slugs": [
            "getting-started",
            "billing",
            "security",
            "account",
            "troubleshooting",
            "integrations",
        ],
        "pricing_kinds": [],
    },
]

# FAQ category slug → product group key (for linked_service backfill).
_FAQ_SLUG_TO_SERVICE = {
    "recruitment": "interview",
    "ai-calling": "interview",
    "whatsapp-surveys": "survey",
    "customer-feedback": "customer_feedback",
    "expo": "expo",
    "campaigns": "campaigns",
    "getting-started": "shared",
    "billing": "shared",
    "security": "shared",
    "account": "shared",
    "troubleshooting": "shared",
    "integrations": "shared",
}


def _table_exists(table: str) -> bool:
    return table in sa.inspect(op.get_bind()).get_table_names()


def _has_column(table: str, column: str) -> bool:
    if not _table_exists(table):
        return False
    return column in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    if not _table_exists("platform_product_groups"):
        # MySQL rejects DEFAULT on TEXT (error 1101). Values are set on INSERT / ORM default=.
        op.create_table(
            "platform_product_groups",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("key", sa.String(length=64), nullable=False),
            sa.Column("name", sa.String(length=160), nullable=False),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column("always_visible", sa.Boolean(), nullable=False, server_default=sa.text("0")),
            sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.text("0")),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("routes_json", sa.Text(), nullable=False),
            sa.Column("faq_category_slugs_json", sa.Text(), nullable=False),
            sa.Column("pricing_kinds_json", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("key", name="uq_platform_product_groups_key"),
        )
        op.create_index("ix_platform_product_groups_key", "platform_product_groups", ["key"])
        op.create_index("ix_platform_product_groups_enabled", "platform_product_groups", ["enabled"])
        op.create_index("ix_platform_product_groups_sort_order", "platform_product_groups", ["sort_order"])

    bind = op.get_bind()
    now = datetime.utcnow()
    existing_keys = set()
    if _table_exists("platform_product_groups"):
        rows = bind.execute(sa.text("SELECT `key` FROM platform_product_groups")).fetchall()
        existing_keys = {r[0] for r in rows}

    import uuid as _uuid

    for g in _DEFAULT_GROUPS:
        if g["key"] in existing_keys:
            continue
        bind.execute(
            sa.text(
                """
                INSERT INTO platform_product_groups
                (id, `key`, name, description, enabled, always_visible, is_system, sort_order,
                 routes_json, faq_category_slugs_json, pricing_kinds_json, created_at, updated_at)
                VALUES
                (:id, :key, :name, :description, 1, :always_visible, :is_system, :sort_order,
                 :routes_json, :faq_json, :pricing_json, :created_at, :updated_at)
                """
            ),
            {
                "id": str(_uuid.uuid4()),
                "key": g["key"],
                "name": g["name"],
                "description": g["description"],
                "always_visible": 1 if g["always_visible"] else 0,
                "is_system": 1 if g["is_system"] else 0,
                "sort_order": g["sort_order"],
                "routes_json": json.dumps(g["routes"]),
                "faq_json": json.dumps(g["faq_category_slugs"]),
                "pricing_json": json.dumps(g["pricing_kinds"]),
                "created_at": now,
                "updated_at": now,
            },
        )

    if _table_exists("faq_items") and not _has_column("faq_items", "linked_service"):
        op.add_column(
            "faq_items",
            sa.Column("linked_service", sa.String(length=64), nullable=True),
        )
        op.create_index("ix_faq_items_linked_service", "faq_items", ["linked_service"])

    # Backfill linked_service from category slug when empty.
    if _table_exists("faq_items") and _table_exists("faq_categories") and _has_column("faq_items", "linked_service"):
        cats = bind.execute(sa.text("SELECT id, slug FROM faq_categories")).fetchall()
        slug_by_id = {int(r[0]): str(r[1] or "").strip().lower() for r in cats}
        items = bind.execute(
            sa.text("SELECT id, category_id, linked_service FROM faq_items")
        ).fetchall()
        for item_id, category_id, linked_service in items:
            if linked_service:
                continue
            if category_id is None:
                continue
            slug = slug_by_id.get(int(category_id), "")
            service = _FAQ_SLUG_TO_SERVICE.get(slug)
            if not service:
                continue
            bind.execute(
                sa.text("UPDATE faq_items SET linked_service = :svc WHERE id = :id"),
                {"svc": service, "id": item_id},
            )


def downgrade() -> None:
    if _table_exists("faq_items") and _has_column("faq_items", "linked_service"):
        bind = op.get_bind()
        indexes = {idx["name"] for idx in sa.inspect(bind).get_indexes("faq_items")}
        if "ix_faq_items_linked_service" in indexes:
            op.drop_index("ix_faq_items_linked_service", table_name="faq_items")
        op.drop_column("faq_items", "linked_service")
    if _table_exists("platform_product_groups"):
        op.drop_table("platform_product_groups")
