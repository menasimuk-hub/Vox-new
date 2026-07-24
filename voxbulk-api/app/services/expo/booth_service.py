"""Expo booth QR tokens, CRUD helpers, and package listing."""

from __future__ import annotations

import json
import re
import secrets
import uuid
from datetime import datetime
from typing import Any
from urllib.parse import quote

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.expo import (
    ExpoBooth,
    ExpoBoothAsset,
    ExpoExhibition,
    ExpoIndustry,
    ExpoLead,
    ExpoPackage,
    ExpoSession,
)
from app.models.organisation import Organisation
from app.models.plan import Plan
from app.models.plan_price import PlanPrice
from app.services.expo.question_bank import default_question_config, parse_question_config
from app.services.customer_feedback.feedback_wa_phone import resolve_feedback_wa_phone_for_qr

TRIGGER_TEMPLATE = "Hi! I visited {company} at {booth} at {event}. {token}"
TOKEN_PATTERN = re.compile(r"\b([a-z0-9]{2,24}-[a-z0-9]{2,24}-[a-z0-9]{6})\b", re.IGNORECASE)


def _slug_part(text: str, *, max_len: int = 20) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", str(text or "").lower()).strip("-")
    return (base or "booth")[:max_len]


def _random_suffix(length: int = 6) -> str:
    alphabet = "abcdefghijklmnopqrstuvwxyz0123456789"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def build_booth_qr_token(*, company: str, booth: str) -> str:
    return f"{_slug_part(company)}-{_slug_part(booth)}-{_random_suffix(6)}"


def build_trigger_text(*, company: str, booth: str, event: str, token: str) -> str:
    return TRIGGER_TEMPLATE.format(
        company=str(company or "Our stand").strip(),
        booth=str(booth or "Stand").strip(),
        event=str(event or "the exhibition").strip(),
        token=str(token or "").strip().lower(),
    )


def _qr_image_for(target_url: str) -> str:
    return f"https://api.qrserver.com/v1/create-qr-code/?size=280x280&data={quote(target_url, safe='')}"


def extract_expo_token(text: str) -> str | None:
    m = TOKEN_PATTERN.search(str(text or ""))
    return m.group(1).lower() if m else None


class ExpoBoothService:
    @staticmethod
    def list_packages(db: Session, *, market_zone: str = "gb") -> list[dict[str, Any]]:
        zone = str(market_zone or "gb").lower()
        rows = db.execute(
            select(ExpoPackage, Plan, PlanPrice)
            .join(Plan, Plan.id == ExpoPackage.plan_id)
            .outerjoin(PlanPrice, (PlanPrice.plan_id == Plan.id) & (PlanPrice.currency == ("GBP" if zone == "gb" else PlanPrice.currency)))
            .where(ExpoPackage.is_active.is_(True), ExpoPackage.market_zone == zone)
            .order_by(ExpoPackage.display_order.asc())
        ).all()
        # Prefer currency match via zone map
        currency_by_zone = {"gb": "GBP", "eu": "EUR", "us": "USD", "ca": "CAD", "au": "AUD"}
        want = currency_by_zone.get(zone, "GBP")
        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        for pkg, plan, _ in rows:
            if pkg.id in seen:
                continue
            seen.add(pkg.id)
            price = db.execute(
                select(PlanPrice).where(PlanPrice.plan_id == plan.id, PlanPrice.currency == want)
            ).scalar_one_or_none()
            features: list[str] = []
            try:
                features = json.loads(plan.features_json or "[]")
            except (json.JSONDecodeError, TypeError):
                features = []
            out.append(
                {
                    "id": pkg.id,
                    "plan_id": plan.id,
                    "plan_code": plan.code,
                    "name": plan.name,
                    "tier": pkg.tier,
                    "market_zone": pkg.market_zone,
                    "currency": want,
                    "price_minor": int(price.monthly_price_minor) if price else int(plan.price_gbp_pence or 0),
                    "max_booths": pkg.max_booths,
                    "max_assets": pkg.max_assets,
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
        settings = get_settings()
        api = str(getattr(settings, "public_api_base_url", None) or getattr(settings, "api_public_origin", "") or "").rstrip("/")
        site = str(getattr(settings, "public_site_url", None) or "https://voxbulk.com").rstrip("/")
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
            "api_asset_base": f"{api}/public/expo/assets/{booth.qr_token}" if api else f"/public/expo/assets/{booth.qr_token}",
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
        qr_target = wa_url or urls["web_url"]
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
            "scan_count": booth.scan_count,
            "lead_count": int(lead_count),
            "hot_count": int(hot_count),
            "question_config": {"steps": parse_question_config(booth.question_config_json)},
            "trigger_text": trigger,
            "whatsapp_url": wa_url,
            "web_url": urls["web_url"],
            "qr_image_url": _qr_image_for(qr_target),
            "assets": [ExpoBoothService.serialize_asset(a) for a in assets],
            "created_at": booth.created_at.isoformat() if booth.created_at else None,
        }

    @staticmethod
    def serialize_asset(asset: ExpoBoothAsset) -> dict[str, Any]:
        return {
            "id": asset.id,
            "asset_key": asset.asset_key,
            "title": asset.title,
            "short_description": asset.short_description,
            "kind": asset.kind,
            "external_url": asset.external_url,
            "storage_path": asset.storage_path,
            "match_keywords": asset.match_keywords,
            "is_default": asset.is_default,
            "sort_order": asset.sort_order,
        }

    @staticmethod
    def list_booths(db: Session, *, org_id: str, owner_user_id: str | None = None) -> list[dict[str, Any]]:
        q = select(ExpoBooth).where(ExpoBooth.org_id == org_id).order_by(ExpoBooth.created_at.desc())
        if owner_user_id:
            q = q.where(ExpoBooth.created_by_user_id == owner_user_id)
        rows = db.execute(q).scalars().all()
        return [ExpoBoothService.serialize_booth(db, b) for b in rows]

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
        qcfg = payload.get("question_config")
        if isinstance(qcfg, dict) and qcfg.get("steps"):
            question_json = json.dumps(qcfg)
        else:
            question_json = json.dumps(default_question_config(include_industry_addon=include_addon, addon_question=addon))

        package_id = str(payload.get("package_id") or "").strip() or None
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
            question_config_json=question_json,
            created_by_user_id=user_id,
            created_at=now,
            updated_at=now,
        )
        db.add(booth)
        db.flush()

        for idx, raw in enumerate(payload.get("assets") or []):
            if not isinstance(raw, dict):
                continue
            title = str(raw.get("title") or "").strip()
            if not title:
                continue
            key = str(raw.get("asset_key") or re.sub(r"[^a-z0-9]+", "_", title.lower())).strip("_")[:64] or f"asset_{idx+1}"
            db.add(
                ExpoBoothAsset(
                    id=str(uuid.uuid4()),
                    org_id=org_id,
                    booth_id=booth.id,
                    asset_key=key,
                    title=title[:255],
                    short_description=(str(raw.get("short_description") or "").strip() or None),
                    kind=str(raw.get("kind") or "pdf")[:16],
                    external_url=(str(raw.get("external_url") or "").strip() or None),
                    match_keywords=(str(raw.get("match_keywords") or "").strip() or None),
                    is_default=bool(raw.get("is_default")),
                    sort_order=int(raw.get("sort_order") or (idx + 1) * 10),
                    created_at=now,
                    updated_at=now,
                )
            )
        db.commit()
        db.refresh(booth)
        return ExpoBoothService.serialize_booth(db, booth)

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
        booth = ExpoBoothService.get_booth(db, org_id=org_id, booth_id=booth_id)
        if booth is None:
            raise ValueError("Booth not found")
        db.execute(select(ExpoBoothAsset).where(ExpoBoothAsset.booth_id == booth.id))
        for asset in db.execute(select(ExpoBoothAsset).where(ExpoBoothAsset.booth_id == booth.id)).scalars().all():
            db.delete(asset)
        for lead in db.execute(select(ExpoLead).where(ExpoLead.booth_id == booth.id)).scalars().all():
            db.delete(lead)
        for session in db.execute(select(ExpoSession).where(ExpoSession.booth_id == booth.id)).scalars().all():
            db.delete(session)
        exhibition_id = booth.exhibition_id
        db.delete(booth)
        remaining = db.execute(
            select(func.count()).select_from(ExpoBooth).where(ExpoBooth.exhibition_id == exhibition_id)
        ).scalar() or 0
        if int(remaining) == 0:
            exhibition = db.get(ExpoExhibition, exhibition_id)
            if exhibition is not None:
                db.delete(exhibition)
        db.commit()
