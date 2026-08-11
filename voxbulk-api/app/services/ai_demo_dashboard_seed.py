"""Idempotent Expo + Smart Card sample rows for the Voxbulk Demo org."""

from __future__ import annotations

import logging
import secrets
import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.expo import ExpoBooth, ExpoExhibition, ExpoLead
from app.models.smart_card import (
    SmartCardCategory,
    SmartCardCompany,
    SmartCardLead,
    SmartCardProduct,
    SmartCardRepresentative,
)
from app.services.expo.booth_service import build_booth_qr_token
from app.services.smart_card.company_service import build_rep_qr_token

logger = logging.getLogger(__name__)

DEMO_PACK_TAG = "ai_demo_dashboard_v1"


def ensure_expo_and_smart_card_demo_data(
    db: Session,
    *,
    org_id: str,
    user_id: str | None = None,
) -> dict[str, Any]:
    """Create paid Expo booth + leads and Smart Card reps if missing."""
    expo = _ensure_expo(db, org_id=org_id, user_id=user_id)
    smart = _ensure_smart_card(db, org_id=org_id, user_id=user_id)
    db.commit()
    return {"expo": expo, "smart_card": smart}


def _ensure_expo(db: Session, *, org_id: str, user_id: str | None) -> dict[str, Any]:
    existing = db.execute(
        select(ExpoBooth).where(ExpoBooth.org_id == org_id, ExpoBooth.name == "Demo Stand A")
    ).scalar_one_or_none()
    if existing is not None:
        leads = db.execute(select(ExpoLead).where(ExpoLead.booth_id == existing.id)).scalars().all()
        if not leads:
            _seed_expo_leads(db, org_id=org_id, booth=existing)
            db.flush()
        return {"booth_id": existing.id, "created": False, "leads": len(leads) or 6}

    now = datetime.utcnow()
    exhibition = ExpoExhibition(
        id=str(uuid.uuid4()),
        org_id=org_id,
        name="TechNorth Live 2026",
        venue="Manchester Central",
        starts_on=now - timedelta(days=2),
        ends_on=now + timedelta(days=1),
        timezone="Europe/London",
        preferred_language="en",
        status="active",
        created_by_user_id=user_id,
        created_at=now,
        updated_at=now,
    )
    db.add(exhibition)
    db.flush()

    token = build_booth_qr_token(company="VoxBulk Demo", booth="Stand A")
    # Avoid rare collisions
    while db.execute(select(ExpoBooth.id).where(ExpoBooth.qr_token == token).limit(1)).scalar_one_or_none():
        token = build_booth_qr_token(company="VoxBulk Demo", booth=f"Stand A {secrets.token_hex(2)}")

    booth = ExpoBooth(
        id=str(uuid.uuid4()),
        org_id=org_id,
        exhibition_id=exhibition.id,
        name="Demo Stand A",
        company_display_name="VoxBulk Demo",
        booth_code="A12",
        qr_token=token,
        status="active",
        activated_at=now - timedelta(days=2),
        expires_at=now + timedelta(days=14),
        scan_count=137,
        payment_status="paid",
        paid_at=now - timedelta(days=3),
        payment_provider="demo",
        is_preview_draft=False,
        company_website="https://voxbulk.com",
        notify_mobile="+447700900111",
        visitor_contact_email="voxbulk-demo@voxbulk.com",
        question_config_json='{"demo_account_pack":"%s"}' % DEMO_PACK_TAG,
        created_by_user_id=user_id,
        created_at=now,
        updated_at=now,
    )
    db.add(booth)
    db.flush()
    _seed_expo_leads(db, org_id=org_id, booth=booth)
    logger.info("ai_demo_expo_seeded org=%s booth=%s", org_id, booth.id)
    return {"booth_id": booth.id, "created": True, "leads": 6}


def _seed_expo_leads(db: Session, *, org_id: str, booth: ExpoBooth) -> None:
    samples = [
        ("Nina Park", "Orbit Labs", "Hot", 1),
        ("Chris Adey", "Northwind", "Warm", 2),
        ("Sara Quinn", "Beacon", "Hot", 0),
        ("Omar Hale", "Fieldline", "Cold", 2),
        ("Elena Moss", "Brightwork", "Warm", 1),
        ("Priya Shah", "Lumen Co", "Hot", 0),
    ]
    now = datetime.utcnow()
    for i, (name, company, score, days_ago) in enumerate(samples):
        db.add(
            ExpoLead(
                id=str(uuid.uuid4()),
                org_id=org_id,
                booth_id=booth.id,
                exhibition_id=booth.exhibition_id,
                name=name,
                company=company,
                visitor_email=f"{name.split()[0].lower()}@example.com",
                visitor_phone=f"+44770090{1000 + i}",
                interest="Product demo at the booth",
                buying_timeline="This quarter",
                lead_score=score,
                consent_acknowledged=True,
                follow_up_status="none",
                created_at=now - timedelta(days=days_ago, hours=i),
                updated_at=now - timedelta(days=days_ago, hours=i),
            )
        )


def _ensure_smart_card(db: Session, *, org_id: str, user_id: str | None) -> dict[str, Any]:
    company = db.execute(select(SmartCardCompany).where(SmartCardCompany.org_id == org_id)).scalar_one_or_none()
    now = datetime.utcnow()
    created_company = False
    if company is None:
        company = SmartCardCompany(
            id=str(uuid.uuid4()),
            org_id=org_id,
            name="VoxBulk Demo",
            website="https://voxbulk.com",
            description="Demo Smart Card company for AI product walkthroughs.",
            products_summary="AI interviews, WhatsApp surveys, Customer Feedback, Expo, Smart Card.",
            contact_email="voxbulk-demo@voxbulk.com",
            contact_phone="+442045770000",
            created_at=now,
            updated_at=now,
        )
        db.add(company)
        db.flush()
        created_company = True

    category = db.execute(
        select(SmartCardCategory).where(
            SmartCardCategory.org_id == org_id,
            SmartCardCategory.name == "Core products",
        )
    ).scalar_one_or_none()
    if category is None:
        category = SmartCardCategory(
            id=str(uuid.uuid4()),
            org_id=org_id,
            name="Core products",
            accent_color="sky",
            sort_order=10,
            created_at=now,
            updated_at=now,
        )
        db.add(category)
        db.flush()

    product = db.execute(
        select(SmartCardProduct).where(
            SmartCardProduct.org_id == org_id,
            SmartCardProduct.name == "VoxBulk Platform",
        )
    ).scalar_one_or_none()
    if product is None:
        product = SmartCardProduct(
            id=str(uuid.uuid4()),
            org_id=org_id,
            category_id=category.id,
            name="VoxBulk Platform",
            short_description="AI interviews, surveys, feedback, expo and smart cards in one workspace.",
            match_keywords="platform,ai,whatsapp",
            sort_order=10,
            created_at=now,
            updated_at=now,
        )
        db.add(product)
        db.flush()

    rep_specs = [
        ("Alex Morgan", 22),
        ("Sam Rivera", 18),
        ("Jordan Lee", 25),
    ]
    reps: list[SmartCardRepresentative] = []
    for name, scans in rep_specs:
        rep = db.execute(
            select(SmartCardRepresentative).where(
                SmartCardRepresentative.org_id == org_id,
                SmartCardRepresentative.name == name,
            )
        ).scalar_one_or_none()
        if rep is None:
            token = build_rep_qr_token(company_slug=company.name or "voxbulk", rep_name=name)
            while db.execute(
                select(SmartCardRepresentative.id).where(SmartCardRepresentative.qr_token == token).limit(1)
            ).scalar_one_or_none():
                token = build_rep_qr_token(
                    company_slug=company.name or "voxbulk",
                    rep_name=f"{name}-{secrets.token_hex(2)}",
                )
            rep = SmartCardRepresentative(
                id=str(uuid.uuid4()),
                org_id=org_id,
                name=name,
                email=f"{name.split()[0].lower()}@voxbulk.com",
                mobile=f"+44770091{scans:04d}",
                website="https://voxbulk.com",
                qr_token=token,
                status="active",
                scan_count=scans,
                created_by_user_id=user_id,
                created_at=now,
                updated_at=now,
            )
            db.add(rep)
            db.flush()
        reps.append(rep)

    # Seed a few attributed leads if none exist
    lead_count = db.execute(select(SmartCardLead).where(SmartCardLead.org_id == org_id)).scalars().all()
    if not lead_count and reps:
        samples = [
            (reps[0], "Hot", "Maya Chen", "North Peak"),
            (reps[0], "Warm", "Tom Ellis", "Harbor Soft"),
            (reps[1], "Hot", "Rita Gomez", "Pulse AI"),
            (reps[1], "Cold", "Ben Cole", "Idle Labs"),
            (reps[2], "Warm", "Ava Brooks", "Summit"),
            (reps[2], "Hot", "Kai Nguyen", "Orbit"),
        ]
        for i, (rep, score, name, company_name) in enumerate(samples):
            db.add(
                SmartCardLead(
                    id=str(uuid.uuid4()),
                    org_id=org_id,
                    representative_id=rep.id,
                    name=name,
                    company=company_name,
                    visitor_email=f"{name.split()[0].lower()}@example.com",
                    visitor_phone=f"+44770092{1000 + i}",
                    lead_score=score,
                    consent="yes",
                    channel="web",
                    follow_up_status="open",
                    created_at=now - timedelta(hours=i * 5),
                    updated_at=now - timedelta(hours=i * 5),
                )
            )

    logger.info(
        "ai_demo_smart_card_seeded org=%s company=%s reps=%s created_company=%s",
        org_id,
        company.id,
        len(reps),
        created_company,
    )
    return {
        "company_id": company.id,
        "created_company": created_company,
        "representatives": len(reps),
    }
