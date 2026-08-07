"""Smart Card QR — company profile, entitlement, and QR helpers."""

from __future__ import annotations

import json
import re
import secrets
from datetime import datetime
from typing import Any
from urllib.parse import quote

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.smart_card import (
    SMART_CARD_PREVIEW_TESTS_LIMIT,
    SMART_CARD_SERVICE_CODE,
    SmartCardCompany,
    SmartCardRepresentative,
)
from app.models.subscription import Subscription

ALLOWED_SMART_CARD_THEME_IDS = frozenset(
    {"smartcard", "smartcard1", "smartcard2", "smartcard3", "smartcard4"}
)


def normalize_smart_card_theme_id(raw: Any) -> str:
    v = str(raw or "").strip().lower()
    return v if v in ALLOWED_SMART_CARD_THEME_IDS else "smartcard"


def normalize_brand_defaults(raw: Any) -> dict[str, Any]:
    brand = dict(raw) if isinstance(raw, dict) else {}
    theme = brand.get("theme_id") or brand.get("theme")
    brand["theme_id"] = normalize_smart_card_theme_id(theme)
    brand.pop("theme", None)
    return brand


def build_rep_qr_token(*, company_slug: str, rep_name: str) -> str:
    co = re.sub(r"[^a-z0-9]+", "-", (company_slug or "co").lower()).strip("-")[:16] or "co"
    rn = re.sub(r"[^a-z0-9]+", "-", (rep_name or "rep").lower()).strip("-")[:12] or "rep"
    return f"{co}-{rn}-{secrets.token_hex(8)}"


def _qr_image_for(url: str, *, fg: str = "000000", bg: str = "ffffff", size: int = 280) -> str:
    """Legacy external QR URL (opaque backgrounds only). Prefer qr_image_url() for reps."""
    fg = re.sub(r"[^0-9a-fA-F]", "", fg or "000000")[:6] or "000000"
    bg = re.sub(r"[^0-9a-fA-F]", "", bg or "ffffff")[:6] or "ffffff"
    return (
        "https://api.qrserver.com/v1/create-qr-code/"
        f"?size={int(size)}x{int(size)}&data={quote(url, safe='')}&color={fg}&bgcolor={bg}"
    )


class SmartCardEntitlementService:
    """Paid live vs preview (15 tests) vs expired."""

    @staticmethod
    def active_subscription(db: Session, org_id: str) -> Subscription | None:
        now = datetime.utcnow()
        rows = (
            db.execute(
                select(Subscription)
                .where(
                    Subscription.org_id == org_id,
                    Subscription.service_code == SMART_CARD_SERVICE_CODE,
                    Subscription.status.in_(("active", "trialing", "past_due")),
                )
                .order_by(Subscription.created_at.desc())
            )
            .scalars()
            .all()
        )
        for sub in rows:
            status = str(sub.status or "").lower()
            if status in {"cancelled", "canceled", "expired"}:
                continue
            end = sub.current_period_end
            if end is not None and end < now and status != "past_due":
                continue
            seats = int(sub.seat_quantity or 0)
            if seats < 1:
                continue
            return sub
        return None

    @staticmethod
    def is_expired(db: Session, org_id: str) -> bool:
        """True when org had a smart_card sub that is past period_end with no active replacement."""
        if SmartCardEntitlementService.active_subscription(db, org_id) is not None:
            return False
        now = datetime.utcnow()
        row = db.execute(
            select(Subscription)
            .where(
                Subscription.org_id == org_id,
                Subscription.service_code == SMART_CARD_SERVICE_CODE,
            )
            .order_by(Subscription.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        if row is None:
            return False
        end = row.current_period_end
        if end is None:
            return str(row.status or "").lower() in {"expired", "cancelled", "canceled"}
        return end < now

    @staticmethod
    def seat_quantity(db: Session, org_id: str) -> int:
        sub = SmartCardEntitlementService.active_subscription(db, org_id)
        return int(sub.seat_quantity or 0) if sub else 0

    @staticmethod
    def active_rep_count(db: Session, org_id: str) -> int:
        return int(
            db.execute(
                select(func.count())
                .select_from(SmartCardRepresentative)
                .where(
                    SmartCardRepresentative.org_id == org_id,
                    SmartCardRepresentative.status == "active",
                )
            ).scalar()
            or 0
        )

    @staticmethod
    def access_mode(db: Session, org_id: str) -> str:
        """live | preview | expired | preview_exhausted"""
        if SmartCardEntitlementService.active_subscription(db, org_id) is not None:
            return "live"
        if SmartCardEntitlementService.is_expired(db, org_id):
            return "expired"
        company = SmartCardCompanyService.get_or_create(db, org_id)
        used = int(company.preview_tests_used or 0)
        if used >= SMART_CARD_PREVIEW_TESTS_LIMIT:
            return "preview_exhausted"
        return "preview"


class SmartCardCompanyService:
    @staticmethod
    def get_or_create(db: Session, org_id: str) -> SmartCardCompany:
        row = db.execute(
            select(SmartCardCompany).where(SmartCardCompany.org_id == org_id)
        ).scalar_one_or_none()
        if row is not None:
            return row
        row = SmartCardCompany(org_id=org_id, name="")
        db.add(row)
        db.flush()
        return row

    @staticmethod
    def serialize(company: SmartCardCompany) -> dict[str, Any]:
        cfg: Any = None
        if company.question_config_json:
            try:
                cfg = json.loads(company.question_config_json)
            except Exception:
                cfg = None
        brand: Any = {}
        if company.brand_defaults_json:
            try:
                parsed = json.loads(company.brand_defaults_json)
                if isinstance(parsed, dict):
                    brand = parsed
            except Exception:
                brand = {}
        brand = normalize_brand_defaults(brand)
        return {
            "id": company.id,
            "org_id": company.org_id,
            "name": company.name or "",
            "website": company.website,
            "description": company.description,
            "products_summary": company.products_summary,
            "pricing_notes": company.pricing_notes,
            "contact_email": company.contact_email,
            "contact_phone": company.contact_phone,
            "brand_defaults": brand,
            "theme_id": brand.get("theme_id") or "smartcard",
            "question_config": cfg,
            "preview_tests_used": int(company.preview_tests_used or 0),
            "preview_tests_limit": SMART_CARD_PREVIEW_TESTS_LIMIT,
        }

    @staticmethod
    def update(db: Session, org_id: str, payload: dict[str, Any]) -> SmartCardCompany:
        company = SmartCardCompanyService.get_or_create(db, org_id)
        for key in (
            "name",
            "website",
            "description",
            "products_summary",
            "pricing_notes",
            "contact_email",
            "contact_phone",
        ):
            if key in payload:
                val = payload[key]
                setattr(company, key, (str(val).strip() if val is not None else None) or ("" if key == "name" else None))
        if "brand_defaults" in payload:
            company.brand_defaults_json = json.dumps(normalize_brand_defaults(payload.get("brand_defaults")))
        elif "theme_id" in payload:
            existing: dict[str, Any] = {}
            if company.brand_defaults_json:
                try:
                    parsed = json.loads(company.brand_defaults_json)
                    if isinstance(parsed, dict):
                        existing = parsed
                except Exception:
                    existing = {}
            existing["theme_id"] = normalize_smart_card_theme_id(payload.get("theme_id"))
            company.brand_defaults_json = json.dumps(normalize_brand_defaults(existing))
        if "question_config" in payload:
            company.question_config_json = json.dumps(payload["question_config"] or {})
        company.updated_at = datetime.utcnow()
        db.add(company)
        db.flush()
        return company

    @staticmethod
    def public_web_url(qr_token: str) -> str:
        settings = get_settings()
        base = (getattr(settings, "PUBLIC_SITE_URL", None) or "https://voxbulk.com").rstrip("/")
        return f"{base}/smart-card/{qr_token}"

    @staticmethod
    def qr_image_url(rep: SmartCardRepresentative) -> str:
        """Absolute PNG URL served by our API (supports true transparent backgrounds)."""
        from app.services.brand_assets import api_public_origin

        token = str(rep.qr_token or "").strip()
        api = (api_public_origin() or "").rstrip("/") or "https://api.voxbulk.com"
        fg = re.sub(r"[^0-9a-fA-F]", "", str(rep.qr_fg_color or "000000"))[:6] or "000000"
        bg = re.sub(r"[^0-9a-fA-F]", "", str(rep.qr_bg_color or "ffffff"))[:6] or "ffffff"
        tr = "1" if rep.qr_transparent else "0"
        # Cache-bust when colours / transparency change
        return f"{api}/public/smart-card/{token}/qr.png?fg={fg}&bg={bg}&t={tr}&s=512"
