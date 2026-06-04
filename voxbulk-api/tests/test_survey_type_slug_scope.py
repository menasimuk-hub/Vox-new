"""Survey type slugs are unique per industry, not globally."""

from __future__ import annotations

import uuid
from datetime import datetime

import pytest
from sqlalchemy import select

from app.models.industry import Industry
from app.models.survey_type import SurveyType
from app.services.industry_service import IndustryService
from app.services.platform_catalog_service import PlatformCatalogService
from app.services.survey_type_service import SurveyTypeService


@pytest.fixture()
def db():
    from app.core.database import Base, get_engine, get_sessionmaker
    import app.models  # noqa: F401

    engine = get_engine()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    SessionLocal = get_sessionmaker()
    session = SessionLocal()
    try:
        PlatformCatalogService.ensure_defaults(session)
        IndustryService.ensure_defaults(session)
        yield session
    finally:
        session.close()


def _industry(db, slug: str) -> Industry:
    now = datetime.utcnow()
    row = Industry(
        id=str(uuid.uuid4()),
        slug=slug,
        name=slug.title(),
        is_active=True,
        sort_order=10,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.flush()
    return row


def test_same_slug_allowed_in_different_industries(db):
    a = _industry(db, "test_ind_a")
    b = _industry(db, "test_ind_b")
    db.commit()

    t1 = SurveyTypeService.create_type(
        db, {"name": "Customer Satisfaction", "industry_id": a.id}
    )
    t2 = SurveyTypeService.create_type(
        db, {"name": "Customer Satisfaction", "industry_id": b.id}
    )
    assert t1.slug == t2.slug
    assert t1.industry_id != t2.industry_id

    rows = list(
        db.execute(
            select(SurveyType).where(SurveyType.slug == t1.slug)
        ).scalars()
    )
    assert len(rows) == 2


def test_duplicate_slug_rejected_within_same_industry(db):
    ind = _industry(db, "test_ind_dup")
    db.commit()
    SurveyTypeService.create_type(db, {"name": "NPS", "slug": "nps", "industry_id": ind.id})
    with pytest.raises(ValueError, match="already exists"):
        SurveyTypeService.create_type(db, {"name": "NPS copy", "slug": "nps", "industry_id": ind.id})
