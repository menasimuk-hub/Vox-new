"""Platform-wide product/service visibility registry (public catalogue, not org grants)."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.platform_product_group import PlatformProductGroup

# Pricing kind shared by Interview + Survey — hide only when both groups are disabled.
SHARED_CORE_PRICING_KIND = "core"
CORE_PRODUCT_KEYS = frozenset({"interview", "survey"})

VALID_PRICING_KINDS = frozenset({"core", "feedback", "expo", "smart_card", "campaign"})

DEFAULT_PRODUCT_GROUPS: list[dict[str, Any]] = [
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

FAQ_CATEGORY_SLUG_TO_SERVICE: dict[str, str] = {
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

_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{1,62}$")


class PlatformProductVisibilityError(ValueError):
    pass


def _dumps(values: list[str]) -> str:
    return json.dumps(list(values), separators=(",", ":"))


def _loads(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(data, list):
        return []
    out: list[str] = []
    for item in data:
        s = str(item or "").strip()
        if s and s not in out:
            out.append(s)
    return out


def _normalize_path(path: str) -> str:
    p = (path or "").strip()
    if not p:
        return ""
    if not p.startswith("/"):
        p = "/" + p
    if len(p) > 1 and p.endswith("/"):
        p = p.rstrip("/")
    return p


def _normalize_routes(raw: list[str] | None) -> list[str]:
    out: list[str] = []
    for item in raw or []:
        p = _normalize_path(str(item))
        if p and p not in out:
            out.append(p)
    return out


def _normalize_slugs(raw: list[str] | None) -> list[str]:
    out: list[str] = []
    for item in raw or []:
        s = str(item or "").strip().lower()
        if s and s not in out:
            out.append(s)
    return out


def _normalize_pricing_kinds(raw: list[str] | None) -> list[str]:
    out: list[str] = []
    for item in raw or []:
        s = str(item or "").strip().lower()
        if s in VALID_PRICING_KINDS and s not in out:
            out.append(s)
    return out


def _normalize_key(raw: str) -> str:
    key = (raw or "").strip().lower().replace("-", "_").replace(" ", "_")
    if not _KEY_RE.match(key):
        raise PlatformProductVisibilityError(
            "Product key must be 2–63 chars: lowercase letter, then letters/digits/underscores."
        )
    return key


def group_to_dict(row: PlatformProductGroup) -> dict[str, Any]:
    return {
        "id": row.id,
        "key": row.key,
        "name": row.name,
        "description": row.description or "",
        "enabled": bool(row.enabled) or bool(row.always_visible),
        "always_visible": bool(row.always_visible),
        "is_system": bool(row.is_system),
        "sort_order": int(row.sort_order or 0),
        "routes": _loads(row.routes_json),
        "faq_category_slugs": _loads(row.faq_category_slugs_json),
        "pricing_kinds": _loads(row.pricing_kinds_json),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _validate_bindings(
    *,
    always_visible: bool,
    routes: list[str],
    faq_category_slugs: list[str],
    pricing_kinds: list[str],
) -> None:
    if always_visible:
        return
    if not routes and not faq_category_slugs and not pricing_kinds:
        raise PlatformProductVisibilityError(
            "Public product groups need at least one route, FAQ category, or pricing binding."
        )


class PlatformProductVisibilityService:
    @staticmethod
    def ensure_defaults(db: Session) -> list[PlatformProductGroup]:
        """Insert missing system groups (enabled). Does not overwrite admin edits."""
        existing = {
            r.key: r
            for r in db.execute(select(PlatformProductGroup)).scalars().all()
        }
        now = datetime.utcnow()
        created = False
        for spec in DEFAULT_PRODUCT_GROUPS:
            if spec["key"] in existing:
                continue
            row = PlatformProductGroup(
                id=str(uuid.uuid4()),
                key=spec["key"],
                name=spec["name"],
                description=spec["description"],
                enabled=True,
                always_visible=bool(spec["always_visible"]),
                is_system=bool(spec["is_system"]),
                sort_order=int(spec["sort_order"]),
                routes_json=_dumps(spec["routes"]),
                faq_category_slugs_json=_dumps(spec["faq_category_slugs"]),
                pricing_kinds_json=_dumps(spec["pricing_kinds"]),
                created_at=now,
                updated_at=now,
            )
            db.add(row)
            existing[spec["key"]] = row
            created = True
        if created:
            db.commit()
        return list(
            db.execute(
                select(PlatformProductGroup).order_by(
                    PlatformProductGroup.sort_order.asc(),
                    PlatformProductGroup.name.asc(),
                )
            ).scalars()
        )

    @staticmethod
    def list_groups(db: Session) -> list[PlatformProductGroup]:
        return PlatformProductVisibilityService.ensure_defaults(db)

    @staticmethod
    def get_by_key(db: Session, key: str) -> PlatformProductGroup | None:
        PlatformProductVisibilityService.ensure_defaults(db)
        return db.execute(
            select(PlatformProductGroup).where(PlatformProductGroup.key == key.strip().lower())
        ).scalar_one_or_none()

    @staticmethod
    def get_by_id(db: Session, group_id: str) -> PlatformProductGroup | None:
        PlatformProductVisibilityService.ensure_defaults(db)
        return db.get(PlatformProductGroup, group_id)

    @staticmethod
    def create_group(
        db: Session,
        *,
        key: str,
        name: str,
        description: str = "",
        enabled: bool = True,
        always_visible: bool = False,
        sort_order: int = 200,
        routes: list[str] | None = None,
        faq_category_slugs: list[str] | None = None,
        pricing_kinds: list[str] | None = None,
    ) -> PlatformProductGroup:
        PlatformProductVisibilityService.ensure_defaults(db)
        norm_key = _normalize_key(key)
        if PlatformProductVisibilityService.get_by_key(db, norm_key):
            raise PlatformProductVisibilityError(f"Product group '{norm_key}' already exists.")
        label = (name or "").strip()
        if len(label) < 2:
            raise PlatformProductVisibilityError("Name must be at least 2 characters.")
        routes_n = _normalize_routes(routes)
        faqs_n = _normalize_slugs(faq_category_slugs)
        pricing_n = _normalize_pricing_kinds(pricing_kinds)
        _validate_bindings(
            always_visible=bool(always_visible),
            routes=routes_n,
            faq_category_slugs=faqs_n,
            pricing_kinds=pricing_n,
        )
        now = datetime.utcnow()
        row = PlatformProductGroup(
            id=str(uuid.uuid4()),
            key=norm_key,
            name=label,
            description=(description or "").strip(),
            enabled=True if always_visible else bool(enabled),
            always_visible=bool(always_visible),
            is_system=False,
            sort_order=int(sort_order or 200),
            routes_json=_dumps(routes_n),
            faq_category_slugs_json=_dumps(faqs_n),
            pricing_kinds_json=_dumps(pricing_n),
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def update_group(
        db: Session,
        group_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        enabled: bool | None = None,
        sort_order: int | None = None,
        routes: list[str] | None = None,
        faq_category_slugs: list[str] | None = None,
        pricing_kinds: list[str] | None = None,
    ) -> PlatformProductGroup:
        row = PlatformProductVisibilityService.get_by_id(db, group_id)
        if row is None:
            raise PlatformProductVisibilityError("Product group not found.")
        if name is not None:
            label = name.strip()
            if len(label) < 2:
                raise PlatformProductVisibilityError("Name must be at least 2 characters.")
            row.name = label
        if description is not None:
            row.description = description.strip()
        if sort_order is not None:
            row.sort_order = int(sort_order)
        if routes is not None:
            row.routes_json = _dumps(_normalize_routes(routes))
        if faq_category_slugs is not None:
            row.faq_category_slugs_json = _dumps(_normalize_slugs(faq_category_slugs))
        if pricing_kinds is not None:
            row.pricing_kinds_json = _dumps(_normalize_pricing_kinds(pricing_kinds))
        if enabled is not None:
            if row.always_visible and not enabled:
                raise PlatformProductVisibilityError(
                    "Shared account/billing/support group cannot be disabled."
                )
            row.enabled = bool(enabled)
        routes_n = _loads(row.routes_json)
        faqs_n = _loads(row.faq_category_slugs_json)
        pricing_n = _loads(row.pricing_kinds_json)
        _validate_bindings(
            always_visible=bool(row.always_visible),
            routes=routes_n,
            faq_category_slugs=faqs_n,
            pricing_kinds=pricing_n,
        )
        row.updated_at = datetime.utcnow()
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def set_enabled(db: Session, group_id: str, enabled: bool) -> PlatformProductGroup:
        return PlatformProductVisibilityService.update_group(db, group_id, enabled=enabled)

    @staticmethod
    def _effective_enabled(row: PlatformProductGroup) -> bool:
        return bool(row.always_visible) or bool(row.enabled)

    @staticmethod
    def enabled_group_keys(db: Session) -> set[str]:
        return {
            r.key
            for r in PlatformProductVisibilityService.list_groups(db)
            if PlatformProductVisibilityService._effective_enabled(r)
        }

    @staticmethod
    def enabled_routes(db: Session) -> set[str]:
        routes: set[str] = set()
        for row in PlatformProductVisibilityService.list_groups(db):
            if not PlatformProductVisibilityService._effective_enabled(row):
                continue
            for path in _loads(row.routes_json):
                routes.add(_normalize_path(path))
        return routes

    @staticmethod
    def disabled_routes(db: Session) -> set[str]:
        """Routes bound only to disabled groups (or all bindings disabled)."""
        enabled_keys = PlatformProductVisibilityService.enabled_group_keys(db)
        route_owners: dict[str, set[str]] = {}
        for row in PlatformProductVisibilityService.list_groups(db):
            for path in _loads(row.routes_json):
                p = _normalize_path(path)
                route_owners.setdefault(p, set()).add(row.key)
        disabled: set[str] = set()
        for path, owners in route_owners.items():
            if not any(k in enabled_keys for k in owners):
                disabled.add(path)
        return disabled

    @staticmethod
    def is_route_enabled(db: Session, path: str) -> bool:
        p = _normalize_path(path)
        # Unbound routes stay visible (contact, legal, home, etc.).
        bound = False
        for row in PlatformProductVisibilityService.list_groups(db):
            if p in {_normalize_path(x) for x in _loads(row.routes_json)}:
                bound = True
                if PlatformProductVisibilityService._effective_enabled(row):
                    return True
        return not bound

    @staticmethod
    def enabled_faq_category_slugs(db: Session) -> set[str]:
        slugs: set[str] = set()
        for row in PlatformProductVisibilityService.list_groups(db):
            if not PlatformProductVisibilityService._effective_enabled(row):
                continue
            for slug in _loads(row.faq_category_slugs_json):
                slugs.add(slug)
        return slugs

    @staticmethod
    def bound_faq_category_slugs(db: Session) -> set[str]:
        slugs: set[str] = set()
        for row in PlatformProductVisibilityService.list_groups(db):
            for slug in _loads(row.faq_category_slugs_json):
                slugs.add(slug)
        return slugs

    @staticmethod
    def is_faq_visible(
        db: Session,
        *,
        category_slug: str | None = None,
        linked_service: str | None = None,
    ) -> bool:
        """FAQ visible unless tied to a disabled product group."""
        enabled_keys = PlatformProductVisibilityService.enabled_group_keys(db)
        svc = (linked_service or "").strip().lower() or None
        if svc:
            if svc not in {r.key for r in PlatformProductVisibilityService.list_groups(db)}:
                return True
            return svc in enabled_keys

        slug = (category_slug or "").strip().lower()
        if not slug:
            return True
        bound = PlatformProductVisibilityService.bound_faq_category_slugs(db)
        if slug not in bound:
            return True
        return slug in PlatformProductVisibilityService.enabled_faq_category_slugs(db)

    @staticmethod
    def enabled_pricing_kinds(db: Session) -> set[str]:
        """Core pricing stays visible unless both interview and survey are disabled."""
        groups = PlatformProductVisibilityService.list_groups(db)
        by_key = {r.key: r for r in groups}
        kinds: set[str] = set()
        for row in groups:
            if not PlatformProductVisibilityService._effective_enabled(row):
                continue
            for kind in _loads(row.pricing_kinds_json):
                if kind == SHARED_CORE_PRICING_KIND:
                    continue
                kinds.add(kind)

        interview_on = PlatformProductVisibilityService._effective_enabled(
            by_key["interview"]
        ) if "interview" in by_key else True
        survey_on = PlatformProductVisibilityService._effective_enabled(
            by_key["survey"]
        ) if "survey" in by_key else True
        if interview_on or survey_on:
            kinds.add(SHARED_CORE_PRICING_KIND)
        return kinds

    @staticmethod
    def is_pricing_kind_enabled(db: Session, kind: str) -> bool:
        k = (kind or "").strip().lower()
        if not k:
            return True
        return k in PlatformProductVisibilityService.enabled_pricing_kinds(db)

    @staticmethod
    def public_payload(db: Session) -> dict[str, Any]:
        groups = [group_to_dict(r) for r in PlatformProductVisibilityService.list_groups(db)]
        enabled_keys = sorted(PlatformProductVisibilityService.enabled_group_keys(db))
        return {
            "groups": groups,
            "enabled_keys": enabled_keys,
            "enabled_routes": sorted(PlatformProductVisibilityService.enabled_routes(db)),
            "disabled_routes": sorted(PlatformProductVisibilityService.disabled_routes(db)),
            "enabled_faq_category_slugs": sorted(
                PlatformProductVisibilityService.enabled_faq_category_slugs(db)
            ),
            "enabled_pricing_kinds": sorted(
                PlatformProductVisibilityService.enabled_pricing_kinds(db)
            ),
        }

    @staticmethod
    def filter_static_sitemap_paths(db: Session, paths: list[str]) -> list[str]:
        disabled = PlatformProductVisibilityService.disabled_routes(db)
        # Also omit /pricing when no pricing kinds remain visible.
        kinds = PlatformProductVisibilityService.enabled_pricing_kinds(db)
        out: list[str] = []
        for path in paths:
            p = _normalize_path(path)
            if p in disabled:
                continue
            if p == "/pricing" and not kinds:
                continue
            out.append(path)
        return out

    @staticmethod
    def backfill_faq_linked_service(db: Session) -> int:
        """Set linked_service from category slug when empty. Returns updated count."""
        from app.models.faq import FAQCategory, FAQItem

        cats = {
            int(c.id): str(c.slug or "").strip().lower()
            for c in db.execute(select(FAQCategory)).scalars().all()
        }
        updated = 0
        for item in db.execute(select(FAQItem)).scalars().all():
            if getattr(item, "linked_service", None):
                continue
            if not item.category_id:
                continue
            slug = cats.get(int(item.category_id), "")
            svc = FAQ_CATEGORY_SLUG_TO_SERVICE.get(slug)
            if not svc:
                continue
            item.linked_service = svc
            db.add(item)
            updated += 1
        if updated:
            db.commit()
        return updated
