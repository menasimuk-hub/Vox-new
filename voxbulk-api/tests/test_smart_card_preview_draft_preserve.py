"""Smart Card preview-draft must not wipe an existing representative."""

from __future__ import annotations

import json
import uuid

from sqlalchemy import select

from app.core.database import get_sessionmaker
from app.core.security import hash_password
from app.models.organisation import Organisation
from app.models.smart_card import SmartCardRepresentative, SmartCardRepresentativeProduct
from app.models.user import User
from app.services.smart_card.catalogue_service import SmartCardCatalogueService
from app.services.smart_card.company_service import SmartCardCompanyService
from app.services.smart_card.representative_service import SmartCardRepresentativeService
from app.services.smart_card.setup_service import SmartCardSetupService


def test_preview_draft_preserves_rep_fields_and_photo_path():
    db = get_sessionmaker()()
    try:
        org = Organisation(name=f"SC Preserve {uuid.uuid4().hex[:6]}")
        db.add(org)
        db.flush()
        user = User(
            email=f"owner-{uuid.uuid4().hex[:6]}@test.local",
            password_hash=hash_password("pass123"),
            is_active=True,
        )
        db.add(user)
        db.flush()

        company = SmartCardCompanyService.get_or_create(db, org.id)
        company.name = "Acme Corp"
        company.contact_email = "hello@acme.test"
        company.website = "https://acme.test"
        db.add(company)
        db.flush()

        cat = SmartCardCatalogueService.create_category(db, org_id=org.id, name="Gear")
        product = SmartCardCatalogueService.create_product(
            db,
            org_id=org.id,
            payload={"category_id": cat.id, "name": "Widget", "short_description": "A widget"},
        )
        rep = SmartCardRepresentativeService.create(
            db,
            org_id=org.id,
            user_id=user.id,
            payload={
                "name": "Zaghlol Rep",
                "email": "zaghlolno@gmail.com",
                "mobile": "+447700900999",
                "landline": "+442012345678",
                "website": "https://rep.example",
                "social_links": {"linkedin": "https://linkedin.com/in/zag"},
                "extra": {"job_title": "Sales"},
                "product_ids": [product.id],
            },
        )
        rep.photo_storage_path = f"data/smart_card_photos/{org.id}/{rep.id}.jpg"
        db.add(rep)
        db.commit()
        rep_id = rep.id

        SmartCardSetupService.preview_draft(
            db,
            org_id=org.id,
            user_id=user.id,
            payload={
                "name": "Acme Corp",
                "website": None,
                "contact_email": None,
                "description": None,
                "selected_keys": ["interest", "role", "follow_up"],
                "contact_capture": "offer_both",
                "representative": {
                    "name": "Zaghlol Rep",
                    "email": "zaghlolno@gmail.com",
                    "mobile": None,
                    "landline": None,
                    "website": None,
                    "social_links": {},
                    "product_ids": [],
                },
            },
        )
        db.commit()

        refreshed = db.get(SmartCardRepresentative, rep_id)
        assert refreshed is not None
        assert refreshed.name == "Zaghlol Rep"
        assert refreshed.email == "zaghlolno@gmail.com"
        assert refreshed.mobile == "+447700900999"
        assert refreshed.landline == "+442012345678"
        assert refreshed.website == "https://rep.example"
        assert refreshed.photo_storage_path == f"data/smart_card_photos/{org.id}/{rep.id}.jpg"
        social = json.loads(refreshed.social_links_json or "{}")
        assert social.get("linkedin")
        links = list(
            db.execute(
                select(SmartCardRepresentativeProduct).where(
                    SmartCardRepresentativeProduct.representative_id == rep_id
                )
            )
            .scalars()
            .all()
        )
        assert len(links) == 1

        company2 = SmartCardCompanyService.get_or_create(db, org.id)
        assert company2.contact_email == "hello@acme.test"
        assert company2.website == "https://acme.test"
    finally:
        db.close()


def test_preview_draft_does_not_overwrite_unrelated_first_rep():
    db = get_sessionmaker()()
    try:
        org = Organisation(name=f"SC Multi {uuid.uuid4().hex[:6]}")
        db.add(org)
        db.flush()
        user = User(
            email=f"owner-{uuid.uuid4().hex[:6]}@test.local",
            password_hash=hash_password("pass123"),
            is_active=True,
        )
        db.add(user)
        db.flush()
        SmartCardCompanyService.get_or_create(db, org.id)

        first = SmartCardRepresentativeService.create(
            db,
            org_id=org.id,
            user_id=user.id,
            payload={"name": "First Rep", "email": "first@test.local", "mobile": "+447711111111"},
        )
        first_id = first.id
        db.commit()

        out = SmartCardSetupService.preview_draft(
            db,
            org_id=org.id,
            user_id=user.id,
            payload={
                "name": "Multi Org",
                "selected_keys": ["interest", "role"],
                "contact_capture": "manual_only",
                "representative": {
                    "name": "Second Rep",
                    "email": "second@test.local",
                    "mobile": "+447722222222",
                },
            },
        )
        db.commit()

        first_ref = db.get(SmartCardRepresentative, first_id)
        assert first_ref is not None
        assert first_ref.name == "First Rep"
        assert first_ref.email == "first@test.local"
        assert first_ref.mobile == "+447711111111"

        second_id = out["representative"]["id"]
        assert second_id != first_id
        second = db.get(SmartCardRepresentative, second_id)
        assert second is not None
        assert second.name == "Second Rep"
        assert second.email == "second@test.local"
    finally:
        db.close()
