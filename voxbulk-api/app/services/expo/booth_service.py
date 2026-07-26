"""Expo booth QR tokens, CRUD helpers, and package listing."""

from __future__ import annotations

import json
import re
import secrets
import uuid
from datetime import date, datetime, timedelta, time
from typing import Any
from urllib.parse import quote
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.expo import (
    ExpoBooth,
    ExpoBoothAsset,
    ExpoBoothCategory,
    ExpoBoothProduct,
    ExpoExhibition,
    ExpoIndustry,
    ExpoLead,
    ExpoPackage,
    ExpoResponse,
    ExpoSession,
    ExpoVoiceNoteJob,
)
from app.models.organisation import Organisation
from app.models.plan import Plan
from app.models.plan_price import PlanPrice
from app.services.expo.question_bank import (
    build_vcard,
    default_free_gift_text,
    default_question_config,
    parse_closing_config,
    parse_contact_capture,
    parse_question_config,
    parse_representative_contacts,
)
from app.services.customer_feedback.feedback_wa_phone import resolve_feedback_wa_phone_for_qr

TRIGGER_TEMPLATE = "Hi! I visited {company} at {booth} at {event}. {token}"
BOOTH_CLOSED_MESSAGE = (
    "Thanks for stopping by! This Expo stand has closed for this exhibition. "
    "Please ask the stand team if you still need information."
)
BOOTH_PREVIEW_EXHAUSTED_MESSAGE = (
    "This Expo booth is not live yet, and the preview test allowance (15) has been used. "
    "Ask the stand team when the exhibition package starts."
)
BOOTH_UNPAID_EXHAUSTED_MESSAGE = (
    "This Expo booth is saved for testing only. Preview tests are used up — "
    "the exhibitor must pay for the package before it can go live."
)
PREVIEW_TESTS_LIMIT = 15
EXPO_PACKAGE_CHECKOUT_KIND = "expo_package_checkout"
_LONDON = ZoneInfo("Europe/London")
_UTC = ZoneInfo("UTC")


def parse_package_start_at(raw: str | datetime | None, *, fallback: datetime | None = None) -> datetime:
    """Parse YYYY-MM-DD (or ISO) as London start-of-day, return naive UTC."""
    stamp = fallback or datetime.utcnow()
    if raw is None or raw == "":
        return stamp
    if isinstance(raw, datetime):
        dt = raw
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_UTC)
        local = dt.astimezone(_LONDON)
        start_local = datetime.combine(local.date(), time(0, 0, 0), tzinfo=_LONDON)
        return start_local.astimezone(_UTC).replace(tzinfo=None)
    text = str(raw).strip()
    if not text:
        return stamp
    try:
        if "T" in text:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=_UTC)
            local = dt.astimezone(_LONDON)
        else:
            day = date.fromisoformat(text[:10])
            local = datetime.combine(day, time(0, 0, 0), tzinfo=_LONDON)
        start_local = datetime.combine(local.date(), time(0, 0, 0), tzinfo=_LONDON)
        return start_local.astimezone(_UTC).replace(tzinfo=None)
    except ValueError:
        return stamp


def compute_booth_expires_at(*, activated_at: datetime, duration_days: int) -> datetime:
    """End of (activation London calendar day + duration_days - 1), stored as naive UTC."""
    days = max(1, int(duration_days or 1))
    if activated_at.tzinfo is None:
        act_local = activated_at.replace(tzinfo=_UTC).astimezone(_LONDON)
    else:
        act_local = activated_at.astimezone(_LONDON)
    end_date = act_local.date() + timedelta(days=days - 1)
    end_local = datetime.combine(end_date, time(23, 59, 59), tzinfo=_LONDON)
    return end_local.astimezone(_UTC).replace(tzinfo=None)


def booth_is_expired(booth: ExpoBooth, *, now: datetime | None = None) -> bool:
    if booth.expires_at is None:
        return False
    return booth.expires_at <= (now or datetime.utcnow())


def booth_is_before_start(booth: ExpoBooth, *, now: datetime | None = None) -> bool:
    if booth.activated_at is None:
        return False
    return (now or datetime.utcnow()) < booth.activated_at


def booth_is_paid(booth: ExpoBooth) -> bool:
    return str(getattr(booth, "payment_status", "") or "").strip().lower() == "paid"


def booth_requires_preview_quota(booth: ExpoBooth, *, now: datetime | None = None) -> bool:
    """Unpaid booths are always preview-only; paid booths use preview only before start."""
    if not booth_is_paid(booth):
        return True
    return booth_is_before_start(booth, now=now)


def booth_is_live(booth: ExpoBooth, *, now: datetime | None = None) -> bool:
    stamp = now or datetime.utcnow()
    return (
        booth_is_paid(booth)
        and str(booth.status or "").lower() == "active"
        and not booth_is_expired(booth, now=stamp)
        and not booth_is_before_start(booth, now=stamp)
    )


def booth_preview_remaining(booth: ExpoBooth) -> int:
    used = int(getattr(booth, "preview_tests_used", 0) or 0)
    return max(0, PREVIEW_TESTS_LIMIT - used)


def booth_access_block_reason(booth: ExpoBooth, *, now: datetime | None = None) -> str | None:
    """Return a visitor-facing error if the booth must not accept a new session."""
    stamp = now or datetime.utcnow()
    if str(booth.status or "").lower() != "active":
        return BOOTH_CLOSED_MESSAGE
    if booth_is_expired(booth, now=stamp):
        return BOOTH_CLOSED_MESSAGE
    if booth_requires_preview_quota(booth, now=stamp) and booth_preview_remaining(booth) <= 0:
        if not booth_is_paid(booth):
            return BOOTH_UNPAID_EXHAUSTED_MESSAGE
        return BOOTH_PREVIEW_EXHAUSTED_MESSAGE
    return None


def apply_package_window(
    db: Session,
    booth: ExpoBooth,
    *,
    now: datetime | None = None,
    start_at: datetime | None = None,
) -> None:
    """Set activated_at / expires_at from package duration and optional start date."""
    stamp = start_at or now or datetime.utcnow()
    days = 1
    if booth.package_id:
        pkg = db.get(ExpoPackage, booth.package_id)
        if pkg is not None:
            days = max(1, int(getattr(pkg, "duration_days", None) or 1))
    booth.activated_at = stamp
    booth.expires_at = compute_booth_expires_at(activated_at=stamp, duration_days=days)
    booth.updated_at = now or datetime.utcnow()

def _slug_part(text: str, *, max_len: int = 20) -> str:
    """Alphanumeric-only slug segment so QR tokens stay exactly 3 parts (company-booth-xxxxxx)."""
    base = re.sub(r"[^a-z0-9]+", "", str(text or "").lower())
    return (base or "booth")[:max_len]


def _random_suffix(length: int = 16) -> str:
    alphabet = "abcdefghijklmnopqrstuvwxyz0123456789"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def build_booth_qr_token(*, company: str, booth: str) -> str:
    # New booths get a 16-char suffix; existing 6-char tokens remain valid forever.
    return f"{_slug_part(company)}-{_slug_part(booth)}-{_random_suffix(16)}"


def build_trigger_text(*, company: str, booth: str, event: str, token: str) -> str:
    return TRIGGER_TEMPLATE.format(
        company=str(company or "Our stand").strip(),
        booth=str(booth or "Stand").strip(),
        event=str(event or "the exhibition").strip(),
        token=str(token or "").strip().lower(),
    )


def _qr_image_for(target_url: str) -> str:
    return f"https://api.qrserver.com/v1/create-qr-code/?size=280x280&data={quote(target_url, safe='')}"


# Accept legacy 6-char and new 16-char suffixes (and anything in between for forward compat).
TOKEN_PATTERN = re.compile(r"\b([a-z0-9]{2,24}-[a-z0-9]{2,24}-[a-z0-9]{6,32})\b", re.IGNORECASE)
TOKEN_SUFFIX_PATTERN = re.compile(r"\b([a-z0-9]+(?:-[a-z0-9]+)+-[a-z0-9]{6,32})\b", re.IGNORECASE)


def extract_expo_token(text: str) -> str | None:
    raw = str(text or "")
    m = TOKEN_PATTERN.search(raw)
    if m:
        return m.group(1).lower()
    m2 = TOKEN_SUFFIX_PATTERN.search(raw)
    return m2.group(1).lower() if m2 else None


def find_expo_token_in_text(db: Session, text: str) -> str | None:
    """Prefer an exact booth qr_token that appears in the inbound message (most reliable).

    Only returns tokens that exist on an ExpoBooth row — never a bare regex match that could
    steal Customer Feedback QR tokens on the shared WhatsApp line.
    """
    raw = str(text or "").lower()
    if not raw.strip():
        return None
    # Fast path: regex candidates that match a booth
    candidates: list[str] = []
    for pat in (TOKEN_PATTERN, TOKEN_SUFFIX_PATTERN):
        for m in pat.finditer(raw):
            tok = m.group(1).lower()
            if tok not in candidates:
                candidates.append(tok)
    for tok in candidates:
        if db.execute(select(ExpoBooth.id).where(ExpoBooth.qr_token == tok).limit(1)).scalar_one_or_none():
            return tok
    # Slow path: known tokens contained in message (handles odd punctuation)
    rows = db.execute(select(ExpoBooth.qr_token)).scalars().all()
    for tok in rows:
        t = str(tok or "").strip().lower()
        if t and t in raw:
            return t
    return None


class ExpoBoothService:
    @staticmethod
    def list_packages(
        db: Session,
        *,
        market_zone: str = "gb",
        currency: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return active Expo duration packages priced in the requested currency.

        ``market_zone`` is accepted for backward compatibility and mapped to currency
        when ``currency`` is not provided. Catalog rows are zone-agnostic (``market_zone=all``).
        """
        currency_by_zone = {"gb": "GBP", "eu": "EUR", "us": "USD", "ca": "CAD", "au": "AUD"}
        zone = str(market_zone or "gb").lower()
        want = str(currency or currency_by_zone.get(zone, "GBP")).upper()
        rows = db.execute(
            select(ExpoPackage, Plan)
            .join(Plan, Plan.id == ExpoPackage.plan_id)
            .where(
                ExpoPackage.is_active.is_(True),
                Plan.is_active.is_(True),
                ExpoPackage.market_zone.in_(("all", zone)),
            )
            .order_by(ExpoPackage.display_order.asc())
        ).all()
        out: list[dict[str, Any]] = []
        seen_tiers: set[str] = set()
        for pkg, plan in rows:
            tier_key = str(pkg.tier or plan.code or pkg.id)
            if tier_key in seen_tiers:
                continue
            # Prefer canonical ``all`` over any leftover zone row for the same tier.
            if pkg.market_zone != "all" and any(
                other.market_zone == "all" and other.tier == pkg.tier for other, _ in rows
            ):
                continue
            seen_tiers.add(tier_key)
            price = db.execute(
                select(PlanPrice).where(PlanPrice.plan_id == plan.id, PlanPrice.currency == want)
            ).scalar_one_or_none()
            features: list[str] = []
            try:
                features = json.loads(plan.features_json or "[]")
            except (json.JSONDecodeError, TypeError):
                features = []
            yearly = int(price.yearly_price_minor) if price and price.yearly_price_minor is not None else None
            out.append(
                {
                    "id": pkg.id,
                    "plan_id": plan.id,
                    "plan_code": plan.code,
                    "name": plan.name,
                    "tier": pkg.tier,
                    "duration_days": int(getattr(pkg, "duration_days", None) or 1),
                    "market_zone": pkg.market_zone,
                    "currency": want,
                    "price_minor": int(price.monthly_price_minor) if price and price.monthly_price_minor is not None else int(plan.price_gbp_pence or 0),
                    "yearly_price_minor": yearly,
                    "max_booths": pkg.max_booths,
                    "max_assets": pkg.max_assets,
                    "max_categories": getattr(pkg, "max_categories", None),
                    "lead_scoring_enabled": pkg.lead_scoring_enabled,
                    "post_show_followup_enabled": pkg.post_show_followup_enabled,
                    "post_event_survey_enabled": pkg.post_event_survey_enabled,
                    "ai_summary_report_enabled": pkg.ai_summary_report_enabled,
                    "features": features,
                    "is_featured": bool(plan.is_featured),
                }
            )
        return out

    @staticmethod
    def list_industries(db: Session) -> list[dict[str, Any]]:
        rows = db.execute(
            select(ExpoIndustry).where(ExpoIndustry.is_active.is_(True)).order_by(ExpoIndustry.sort_order.asc())
        ).scalars().all()
        return [
            {
                "id": r.id,
                "slug": r.slug,
                "name": r.name,
                "description": r.description,
                "addon_question": r.addon_question,
            }
            for r in rows
        ]

    @staticmethod
    def booth_public_urls(booth: ExpoBooth, *, event_name: str) -> dict[str, str]:
        """URLs that don't need a DB-resolved WhatsApp number. See serialize_booth for whatsapp_url."""
        from app.services.brand_assets import api_public_origin

        settings = get_settings()
        api = api_public_origin().rstrip("/")
        site = str(
            getattr(settings, "public_site_base_url", None)
            or getattr(settings, "public_site_url", None)
            or "https://voxbulk.com"
        ).rstrip("/")
        trigger = build_trigger_text(
            company=booth.company_display_name,
            booth=booth.booth_code or booth.name,
            event=event_name,
            token=booth.qr_token,
        )
        web_url = f"{site}/expo/{booth.qr_token}"
        return {
            "trigger_text": trigger,
            "whatsapp_url": "",
            "web_url": web_url,
            "qr_image_url": _qr_image_for(web_url),
            "api_asset_base": f"{api}/public/expo/assets/{booth.qr_token}",
        }

    @staticmethod
    def serialize_booth(db: Session, booth: ExpoBooth) -> dict[str, Any]:
        exhibition = db.get(ExpoExhibition, booth.exhibition_id)
        event_name = exhibition.name if exhibition else "Exhibition"
        urls = ExpoBoothService.booth_public_urls(booth, event_name=event_name)
        org = db.get(Organisation, booth.org_id)
        country_code = str(getattr(org, "country_code", None) or "gb")
        phone = resolve_feedback_wa_phone_for_qr(db, country_code, org_id=booth.org_id)
        trigger = urls["trigger_text"]
        digits = re.sub(r"\D+", "", str(phone or ""))
        wa_url = f"https://wa.me/{digits}?text={quote(trigger)}" if digits else ""
        # QR always opens the public landing (WA vs Web choice), same pattern as Customer Feedback.
        qr_target = urls["web_url"]
        lead_count = db.execute(
            select(func.count()).select_from(ExpoLead).where(ExpoLead.booth_id == booth.id)
        ).scalar() or 0
        hot_count = db.execute(
            select(func.count())
            .select_from(ExpoLead)
            .where(ExpoLead.booth_id == booth.id, ExpoLead.lead_score == "hot")
        ).scalar() or 0
        assets = db.execute(
            select(ExpoBoothAsset)
            .where(ExpoBoothAsset.booth_id == booth.id)
            .order_by(ExpoBoothAsset.sort_order.asc())
        ).scalars().all()
        return {
            "id": booth.id,
            "org_id": booth.org_id,
            "exhibition_id": booth.exhibition_id,
            "exhibition_name": event_name,
            "package_id": booth.package_id,
            "name": booth.name,
            "company_display_name": booth.company_display_name,
            "booth_code": booth.booth_code,
            "qr_token": booth.qr_token,
            "status": booth.status,
            "activated_at": booth.activated_at.isoformat() if booth.activated_at else None,
            "expires_at": booth.expires_at.isoformat() if booth.expires_at else None,
            "is_expired": booth_is_expired(booth),
            "is_before_start": booth_is_before_start(booth),
            "is_live": booth_is_live(booth),
            "is_paid": booth_is_paid(booth),
            "payment_status": str(getattr(booth, "payment_status", None) or "unpaid"),
            "paid_at": booth.paid_at.isoformat() if getattr(booth, "paid_at", None) else None,
            "payment_provider": getattr(booth, "payment_provider", None),
            "scan_count": booth.scan_count,
            "preview_tests_used": int(getattr(booth, "preview_tests_used", 0) or 0),
            "preview_tests_limit": PREVIEW_TESTS_LIMIT,
            "preview_tests_remaining": booth_preview_remaining(booth),
            "lead_count": int(lead_count),
            "hot_count": int(hot_count),
            "question_config": {"steps": parse_question_config(booth.question_config_json)},
            "closing": parse_closing_config(booth.question_config_json),
            "contact_capture": parse_contact_capture(booth.question_config_json),
            "trigger_text": trigger,
            "whatsapp_url": wa_url,
            "web_url": urls["web_url"],
            "qr_image_url": _qr_image_for(qr_target),
            "assets": [ExpoBoothService.serialize_asset(a) for a in assets],
            "categories": ExpoBoothService.serialize_catalog_tree(db, booth.id),
            "representatives": parse_representative_contacts(
                getattr(booth, "representative_contacts_json", None)
            ),
            "company_website": getattr(booth, "company_website", None),
            "notify_mobile": getattr(booth, "notify_mobile", None),
            "max_categories": ExpoBoothService.package_max_categories(db, booth.package_id),
            "venue": exhibition.venue if exhibition else None,
            "industry_id": exhibition.industry_id if exhibition else None,
            "created_at": booth.created_at.isoformat() if booth.created_at else None,
        }

    @staticmethod
    def serialize_asset(asset: ExpoBoothAsset) -> dict[str, Any]:
        from app.services.expo.offer_delivery_service import normalize_asset_purpose

        return {
            "id": asset.id,
            "product_id": getattr(asset, "product_id", None),
            "asset_key": asset.asset_key,
            "title": asset.title,
            "short_description": asset.short_description,
            "kind": asset.kind,
            "purpose": normalize_asset_purpose(getattr(asset, "purpose", None) or "product"),
            "external_url": asset.external_url,
            "storage_path": asset.storage_path,
            "match_keywords": asset.match_keywords,
            "is_default": asset.is_default,
            "sort_order": asset.sort_order,
        }

    @staticmethod
    def serialize_catalog_tree(db: Session, booth_id: str) -> list[dict[str, Any]]:
        try:
            cats = db.execute(
                select(ExpoBoothCategory)
                .where(ExpoBoothCategory.booth_id == booth_id)
                .order_by(ExpoBoothCategory.sort_order.asc())
            ).scalars().all()
            products = db.execute(
                select(ExpoBoothProduct)
                .where(ExpoBoothProduct.booth_id == booth_id)
                .order_by(ExpoBoothProduct.sort_order.asc())
            ).scalars().all()
            assets = db.execute(
                select(ExpoBoothAsset)
                .where(ExpoBoothAsset.booth_id == booth_id)
                .order_by(ExpoBoothAsset.sort_order.asc())
            ).scalars().all()
        except Exception:
            # Missing migration / table — never hide the booth (QR / pay UI).
            return []
        assets_by_product: dict[str, list[dict[str, Any]]] = {}
        for a in assets:
            pid = str(getattr(a, "product_id", None) or "")
            if not pid:
                continue
            assets_by_product.setdefault(pid, []).append(ExpoBoothService.serialize_asset(a))
        products_by_cat: dict[str, list[dict[str, Any]]] = {}
        for p in products:
            products_by_cat.setdefault(p.category_id, []).append(
                {
                    "id": p.id,
                    "category_id": p.category_id,
                    "name": p.name,
                    "short_description": p.short_description,
                    "sort_order": p.sort_order,
                    "assets": assets_by_product.get(p.id, []),
                }
            )
        return [
            {
                "id": c.id,
                "name": c.name,
                "accent_color": c.accent_color or "#E8F0FE",
                "sort_order": c.sort_order,
                "products": products_by_cat.get(c.id, []),
            }
            for c in cats
        ]

    @staticmethod
    def package_max_categories(db: Session, package_id: str | None) -> int | None:
        if not package_id:
            return 1
        pkg = db.get(ExpoPackage, package_id)
        if pkg is None:
            return 1
        return getattr(pkg, "max_categories", 1)

    @staticmethod
    def assert_category_limit(db: Session, *, package_id: str | None, category_count: int) -> None:
        limit = ExpoBoothService.package_max_categories(db, package_id)
        if limit is None:
            return
        if int(category_count) > int(limit):
            raise ValueError(
                f"This package allows up to {limit} product categor{'y' if limit == 1 else 'ies'}. "
                "Upgrade your package or remove a category."
            )

    @staticmethod
    def assert_can_create_booth(db: Session, *, org_id: str) -> None:
        unpaid = db.execute(
            select(func.count())
            .select_from(ExpoBooth)
            .where(
                ExpoBooth.org_id == org_id,
                ExpoBooth.payment_status != "paid",
                ExpoBooth.status == "active",
            )
        ).scalar() or 0
        if int(unpaid) >= 1:
            raise ValueError(
                "You already have an unpaid Expo QR draft. Pay for that package first, "
                "or delete it — each QR code requires its own package purchase."
            )

    @staticmethod
    def _normalize_reps(payload: dict[str, Any] | list | None) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return parse_representative_contacts(json.dumps(payload))
        if isinstance(payload, dict) and isinstance(payload.get("representatives"), list):
            return parse_representative_contacts(json.dumps(payload.get("representatives")))
        return []

    @staticmethod
    def _save_catalog_tree(
        db: Session,
        *,
        org_id: str,
        booth: ExpoBooth,
        categories_payload: list[Any],
        legacy_assets: list[Any] | None = None,
        now: datetime | None = None,
    ) -> None:
        stamp = now or datetime.utcnow()
        ExpoBoothService.assert_category_limit(
            db, package_id=booth.package_id, category_count=len(categories_payload or [])
        )
        # Wipe existing tree then recreate (edit-friendly).
        from sqlalchemy import delete

        db.execute(delete(ExpoBoothAsset).where(ExpoBoothAsset.booth_id == booth.id))
        db.execute(delete(ExpoBoothProduct).where(ExpoBoothProduct.booth_id == booth.id))
        db.execute(delete(ExpoBoothCategory).where(ExpoBoothCategory.booth_id == booth.id))
        db.flush()

        from app.services.expo.offer_delivery_service import normalize_asset_purpose

        asset_idx = 0
        for c_idx, raw_cat in enumerate(categories_payload or []):
            if not isinstance(raw_cat, dict):
                continue
            cname = str(raw_cat.get("name") or "").strip()
            if not cname:
                continue
            cat = ExpoBoothCategory(
                id=str(uuid.uuid4()),
                org_id=org_id,
                booth_id=booth.id,
                name=cname[:128],
                accent_color=str(raw_cat.get("accent_color") or "#E8F0FE")[:32],
                sort_order=int(raw_cat.get("sort_order") or (c_idx + 1) * 10),
                created_at=stamp,
                updated_at=stamp,
            )
            db.add(cat)
            db.flush()
            for p_idx, raw_prod in enumerate(raw_cat.get("products") or []):
                if not isinstance(raw_prod, dict):
                    continue
                pname = str(raw_prod.get("name") or "").strip()
                if not pname:
                    continue
                prod = ExpoBoothProduct(
                    id=str(uuid.uuid4()),
                    org_id=org_id,
                    booth_id=booth.id,
                    category_id=cat.id,
                    name=pname[:255],
                    short_description=(str(raw_prod.get("short_description") or "").strip() or None),
                    sort_order=int(raw_prod.get("sort_order") or (p_idx + 1) * 10),
                    created_at=stamp,
                    updated_at=stamp,
                )
                db.add(prod)
                db.flush()
                for raw_asset in raw_prod.get("assets") or []:
                    if not isinstance(raw_asset, dict):
                        continue
                    title = str(raw_asset.get("title") or pname).strip()
                    if not title:
                        continue
                    storage_path = (str(raw_asset.get("storage_path") or "").strip() or None)
                    external_url = (str(raw_asset.get("external_url") or "").strip() or None)
                    if storage_path and (
                        ".." in storage_path.replace("\\", "/").split("/")
                        or not storage_path.startswith("data/expo-assets/")
                    ):
                        raise ValueError("Invalid uploaded file path")
                    if not storage_path and not external_url:
                        continue
                    asset_idx += 1
                    key = (
                        str(raw_asset.get("asset_key") or re.sub(r"[^a-z0-9]+", "_", title.lower()))
                        .strip("_")[:64]
                        or f"asset_{asset_idx}"
                    )
                    kind = str(
                        raw_asset.get("kind")
                        or ("pdf" if (storage_path or "").lower().endswith(".pdf") else "link")
                    )[:16]
                    purpose = normalize_asset_purpose(raw_asset.get("purpose") or "product")
                    db.add(
                        ExpoBoothAsset(
                            id=str(uuid.uuid4()),
                            org_id=org_id,
                            booth_id=booth.id,
                            product_id=prod.id,
                            asset_key=key,
                            title=title[:255],
                            short_description=(str(raw_asset.get("short_description") or "").strip() or None),
                            kind=kind,
                            purpose=purpose,
                            storage_path=storage_path,
                            external_url=external_url,
                            match_keywords=(str(raw_asset.get("match_keywords") or "").strip() or None),
                            is_default=bool(raw_asset.get("is_default")),
                            sort_order=int(raw_asset.get("sort_order") or asset_idx * 10),
                            created_at=stamp,
                            updated_at=stamp,
                        )
                    )

        # Legacy flat assets (pre-category wizard) — keep working.
        for idx, raw in enumerate(legacy_assets or []):
            if not isinstance(raw, dict):
                continue
            title = str(raw.get("title") or "").strip()
            if not title:
                continue
            storage_path = (str(raw.get("storage_path") or "").strip() or None)
            external_url = (str(raw.get("external_url") or "").strip() or None)
            if storage_path and (
                ".." in storage_path.replace("\\", "/").split("/")
                or not storage_path.startswith("data/expo-assets/")
            ):
                raise ValueError("Invalid uploaded file path")
            if not storage_path and not external_url:
                continue
            key = str(raw.get("asset_key") or re.sub(r"[^a-z0-9]+", "_", title.lower())).strip("_")[:64] or f"asset_{idx+1}"
            kind = str(raw.get("kind") or ("pdf" if (storage_path or "").lower().endswith(".pdf") else "link"))[:16]
            purpose = normalize_asset_purpose(raw.get("purpose") or "product")
            db.add(
                ExpoBoothAsset(
                    id=str(uuid.uuid4()),
                    org_id=org_id,
                    booth_id=booth.id,
                    product_id=None,
                    asset_key=key,
                    title=title[:255],
                    short_description=(str(raw.get("short_description") or "").strip() or None),
                    kind=kind,
                    purpose=purpose,
                    storage_path=storage_path,
                    external_url=external_url,
                    match_keywords=(str(raw.get("match_keywords") or "").strip() or None),
                    is_default=bool(raw.get("is_default")),
                    sort_order=int(raw.get("sort_order") or (idx + 1) * 10),
                    created_at=stamp,
                    updated_at=stamp,
                )
            )

    @staticmethod
    def list_booths(db: Session, *, org_id: str, owner_user_id: str | None = None) -> list[dict[str, Any]]:
        import logging

        q = select(ExpoBooth).where(ExpoBooth.org_id == org_id).order_by(ExpoBooth.created_at.desc())
        if owner_user_id:
            # Members see their own booths; also include legacy rows with no owner stamp
            q = q.where(
                or_(ExpoBooth.created_by_user_id == owner_user_id, ExpoBooth.created_by_user_id.is_(None))
            )
        rows = db.execute(q).scalars().all()
        items: list[dict[str, Any]] = []
        for booth in rows:
            try:
                items.append(ExpoBoothService.serialize_booth(db, booth))
            except Exception as exc:
                logging.getLogger(__name__).warning(
                    "expo_serialize_booth_failed booth_id=%s err=%s", booth.id, str(exc)[:200]
                )
        return items

    @staticmethod
    def create_booth(
        db: Session,
        *,
        org_id: str,
        user_id: str | None,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        org = db.get(Organisation, org_id)
        if org is None:
            raise ValueError("Organisation not found")
        ExpoBoothService.assert_can_create_booth(db, org_id=org_id)
        industry_id = str(payload.get("industry_id") or "").strip() or None
        industry = db.get(ExpoIndustry, industry_id) if industry_id else None
        now = datetime.utcnow()
        exhibition = ExpoExhibition(
            id=str(uuid.uuid4()),
            org_id=org_id,
            industry_id=industry.id if industry else None,
            name=str(payload.get("exhibition_name") or "Exhibition").strip()[:255],
            venue=(str(payload.get("venue") or "").strip() or None),
            preferred_language=str(payload.get("preferred_language") or "en")[:16],
            status="active",
            created_by_user_id=user_id,
            created_at=now,
            updated_at=now,
        )
        db.add(exhibition)
        db.flush()

        company = str(payload.get("company_display_name") or org.name or "Company").strip()[:255]
        booth_name = str(payload.get("name") or payload.get("booth_code") or "Stand").strip()[:255]
        booth_code = (str(payload.get("booth_code") or booth_name).strip() or None)
        token = build_booth_qr_token(company=company, booth=booth_code or booth_name)

        include_addon = bool(payload.get("include_industry_addon"))
        addon = industry.addon_question if industry else None
        free_gift_enabled = bool(payload.get("free_gift_enabled"))
        free_gift_text = str(payload.get("free_gift_text") or "").strip() or None
        if free_gift_enabled and not free_gift_text:
            free_gift_text = default_free_gift_text(company)
        thank_you_message = str(payload.get("thank_you_message") or "").strip() or None
        selected_keys_raw = payload.get("selected_question_keys")
        selected_keys = (
            [str(k).strip() for k in selected_keys_raw if str(k).strip()]
            if isinstance(selected_keys_raw, list)
            else None
        )
        contact_capture = str(payload.get("contact_capture") or "offer_both").strip().lower()
        qcfg = payload.get("question_config")
        if isinstance(qcfg, dict) and qcfg.get("steps"):
            merged = dict(qcfg)
            merged["free_gift_enabled"] = free_gift_enabled if "free_gift_enabled" not in qcfg else bool(qcfg.get("free_gift_enabled"))
            if free_gift_text is not None:
                merged["free_gift_text"] = free_gift_text
            if thank_you_message is not None:
                merged["thank_you_message"] = thank_you_message
            elif not merged.get("thank_you_message"):
                merged["thank_you_message"] = default_question_config(db=db)["thank_you_message"]
            if contact_capture:
                merged["contact_capture"] = contact_capture
            question_json = json.dumps(merged)
        else:
            question_json = json.dumps(
                default_question_config(
                    include_industry_addon=include_addon,
                    addon_question=addon,
                    free_gift_enabled=free_gift_enabled,
                    free_gift_text=free_gift_text,
                    thank_you_message=thank_you_message,
                    selected_question_keys=selected_keys,
                    contact_capture=contact_capture,
                    db=db,
                )
            )

        package_id = str(payload.get("package_id") or "").strip() or None
        start_raw = payload.get("start_date") or payload.get("starts_on") or payload.get("package_start_date")
        start_at = parse_package_start_at(start_raw, fallback=now)
        reps = ExpoBoothService._normalize_reps(payload.get("representatives") or payload.get("representative_contacts"))
        company_website = (str(payload.get("company_website") or "").strip() or None)
        if company_website:
            company_website = company_website[:512]
        notify_mobile = (str(payload.get("notify_mobile") or "").strip() or None)
        if not notify_mobile and reps:
            notify_mobile = str(reps[0].get("mobile") or "").strip() or None
        if notify_mobile:
            notify_mobile = notify_mobile[:64]

        booth = ExpoBooth(
            id=str(uuid.uuid4()),
            org_id=org_id,
            exhibition_id=exhibition.id,
            package_id=package_id,
            name=booth_name,
            company_display_name=company,
            booth_code=booth_code,
            qr_token=token,
            status="active",
            scan_count=0,
            preview_tests_used=0,
            payment_status="unpaid",
            question_config_json=question_json,
            representative_contacts_json=json.dumps(reps) if reps else None,
            company_website=company_website,
            notify_mobile=notify_mobile,
            created_by_user_id=user_id,
            created_at=now,
            updated_at=now,
        )
        apply_package_window(db, booth, now=now, start_at=start_at)
        exhibition.starts_on = booth.activated_at
        exhibition.ends_on = booth.expires_at
        exhibition.updated_at = now
        db.add(exhibition)
        db.add(booth)
        db.flush()

        categories_payload = payload.get("categories")
        if isinstance(categories_payload, list) and categories_payload:
            ExpoBoothService._save_catalog_tree(
                db,
                org_id=org_id,
                booth=booth,
                categories_payload=categories_payload,
                legacy_assets=None,
                now=now,
            )
        else:
            ExpoBoothService._save_catalog_tree(
                db,
                org_id=org_id,
                booth=booth,
                categories_payload=[],
                legacy_assets=list(payload.get("assets") or []),
                now=now,
            )
        db.commit()
        db.refresh(booth)
        return ExpoBoothService.serialize_booth(db, booth)

    @staticmethod
    def update_booth(
        db: Session,
        *,
        org_id: str,
        booth_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        booth = ExpoBoothService.get_booth(db, org_id=org_id, booth_id=booth_id)
        if booth is None:
            raise ValueError("Booth not found")
        now = datetime.utcnow()
        exhibition = db.get(ExpoExhibition, booth.exhibition_id)

        if payload.get("exhibition_name") is not None and exhibition is not None:
            exhibition.name = str(payload.get("exhibition_name") or exhibition.name).strip()[:255]
        if payload.get("venue") is not None and exhibition is not None:
            exhibition.venue = str(payload.get("venue") or "").strip() or None
        if payload.get("industry_id") is not None and exhibition is not None:
            iid = str(payload.get("industry_id") or "").strip() or None
            exhibition.industry_id = iid
        if exhibition is not None:
            exhibition.updated_at = now
            db.add(exhibition)

        if payload.get("name") is not None:
            booth.name = str(payload.get("name") or booth.name).strip()[:255]
        if payload.get("company_display_name") is not None:
            booth.company_display_name = str(payload.get("company_display_name") or booth.company_display_name).strip()[:255]
        if payload.get("booth_code") is not None:
            booth.booth_code = str(payload.get("booth_code") or "").strip() or None
        if payload.get("company_website") is not None:
            booth.company_website = str(payload.get("company_website") or "").strip()[:512] or None
        if payload.get("notify_mobile") is not None:
            booth.notify_mobile = str(payload.get("notify_mobile") or "").strip()[:64] or None
        if "representatives" in payload or "representative_contacts" in payload:
            reps = ExpoBoothService._normalize_reps(
                payload.get("representatives") or payload.get("representative_contacts")
            )
            booth.representative_contacts_json = json.dumps(reps) if reps else None
            if not booth.notify_mobile and reps:
                booth.notify_mobile = str(reps[0].get("mobile") or "").strip()[:64] or None

        free_gift_enabled = payload.get("free_gift_enabled")
        free_gift_text = payload.get("free_gift_text")
        thank_you_message = payload.get("thank_you_message")
        selected_keys_raw = payload.get("selected_question_keys")
        contact_capture = payload.get("contact_capture")
        include_addon = payload.get("include_industry_addon")
        if any(
            v is not None
            for v in (free_gift_enabled, free_gift_text, thank_you_message, selected_keys_raw, contact_capture, include_addon)
        ) or payload.get("question_config"):
            industry = None
            if exhibition and exhibition.industry_id:
                industry = db.get(ExpoIndustry, exhibition.industry_id)
            addon = industry.addon_question if industry else None
            selected_keys = (
                [str(k).strip() for k in selected_keys_raw if str(k).strip()]
                if isinstance(selected_keys_raw, list)
                else None
            )
            qcfg = payload.get("question_config")
            if isinstance(qcfg, dict) and qcfg.get("steps"):
                booth.question_config_json = json.dumps(qcfg)
            else:
                closing = parse_closing_config(booth.question_config_json)
                gift_on = bool(free_gift_enabled) if free_gift_enabled is not None else bool(closing.get("free_gift_enabled"))
                gift_text = (
                    str(free_gift_text).strip()
                    if free_gift_text is not None
                    else str(closing.get("free_gift_text") or "")
                )
                thank = (
                    str(thank_you_message).strip()
                    if thank_you_message is not None
                    else str(closing.get("thank_you_message") or "")
                )
                mode = str(contact_capture or "").strip().lower() or None
                if not mode:
                    try:
                        mode = json.loads(booth.question_config_json or "{}").get("contact_capture") or "offer_both"
                    except (json.JSONDecodeError, TypeError):
                        mode = "offer_both"
                booth.question_config_json = json.dumps(
                    default_question_config(
                        include_industry_addon=bool(include_addon) if include_addon is not None else bool(addon),
                        addon_question=addon,
                        free_gift_enabled=gift_on,
                        free_gift_text=gift_text or None,
                        thank_you_message=thank or None,
                        selected_question_keys=selected_keys,
                        contact_capture=str(mode),
                        db=db,
                    )
                )

        if isinstance(payload.get("categories"), list) or isinstance(payload.get("assets"), list):
            ExpoBoothService._save_catalog_tree(
                db,
                org_id=org_id,
                booth=booth,
                categories_payload=list(payload.get("categories") or []),
                legacy_assets=list(payload.get("assets") or []) if not payload.get("categories") else None,
                now=now,
            )

        booth.updated_at = now
        db.add(booth)
        db.commit()
        db.refresh(booth)
        return ExpoBoothService.serialize_booth(db, booth)

    @staticmethod
    def booth_vcard(db: Session, booth: ExpoBooth) -> str:
        reps = parse_representative_contacts(getattr(booth, "representative_contacts_json", None))
        return build_vcard(
            company_name=booth.company_display_name or booth.name,
            website=getattr(booth, "company_website", None),
            reps=reps,
        )

    @staticmethod
    def get_booth(db: Session, *, org_id: str, booth_id: str) -> ExpoBooth | None:
        return db.execute(
            select(ExpoBooth).where(ExpoBooth.id == booth_id, ExpoBooth.org_id == org_id)
        ).scalar_one_or_none()

    @staticmethod
    def find_by_token(db: Session, token: str) -> ExpoBooth | None:
        clean = str(token or "").strip().lower()
        if not clean:
            return None
        return db.execute(select(ExpoBooth).where(ExpoBooth.qr_token == clean)).scalar_one_or_none()

    @staticmethod
    def delete_booth(db: Session, *, org_id: str, booth_id: str) -> None:
        from sqlalchemy import delete, text
        from sqlalchemy.exc import IntegrityError, SQLAlchemyError

        booth = ExpoBoothService.get_booth(db, org_id=org_id, booth_id=booth_id)
        if booth is None:
            raise ValueError("Booth not found")
        bid = booth.id
        exhibition_id = booth.exhibition_id
        session_ids = [
            r[0]
            for r in db.execute(select(ExpoSession.id).where(ExpoSession.booth_id == bid)).all()
        ]
        try:
            # Bulk deletes — order respects FKs (responses/voice → leads → sessions → assets → booth)
            db.execute(delete(ExpoResponse).where(ExpoResponse.booth_id == bid))
            if session_ids:
                db.execute(delete(ExpoResponse).where(ExpoResponse.session_id.in_(session_ids)))
                db.execute(delete(ExpoVoiceNoteJob).where(ExpoVoiceNoteJob.session_id.in_(session_ids)))
            db.execute(delete(ExpoVoiceNoteJob).where(ExpoVoiceNoteJob.booth_id == bid))
            # Clear soft session link before removing sessions
            db.execute(
                text("UPDATE expo_leads SET session_id = NULL WHERE booth_id = :bid"),
                {"bid": bid},
            )
            db.execute(delete(ExpoLead).where(ExpoLead.booth_id == bid))
            db.execute(delete(ExpoSession).where(ExpoSession.booth_id == bid))
            db.execute(delete(ExpoBoothAsset).where(ExpoBoothAsset.booth_id == bid))
            db.execute(delete(ExpoBoothProduct).where(ExpoBoothProduct.booth_id == bid))
            db.execute(delete(ExpoBoothCategory).where(ExpoBoothCategory.booth_id == bid))
            db.execute(delete(ExpoBooth).where(ExpoBooth.id == bid, ExpoBooth.org_id == org_id))
            remaining = db.execute(
                select(func.count()).select_from(ExpoBooth).where(ExpoBooth.exhibition_id == exhibition_id)
            ).scalar() or 0
            if int(remaining) == 0:
                # Any stray leads for this exhibition (should be none after booth wipe)
                db.execute(delete(ExpoLead).where(ExpoLead.exhibition_id == exhibition_id))
                db.execute(delete(ExpoExhibition).where(ExpoExhibition.id == exhibition_id))
            db.commit()
        except (IntegrityError, SQLAlchemyError) as exc:
            db.rollback()
            raise ValueError(
                "Could not delete this booth because related records are still linked. "
                "Try again, or contact support if it keeps failing."
            ) from exc
