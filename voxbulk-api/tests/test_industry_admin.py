"""Industry CRUD and ensure_defaults backfill."""

from __future__ import annotations

import pytest

from app.core.database import get_sessionmaker
from app.services.industry_service import DEFAULT_INDUSTRIES, IndustryService
from app.services.survey_type_service import SurveyTypeService


@pytest.fixture(autouse=True)
def _schema():
    from app.core.database import Base, get_engine
    import app.models  # noqa: F401

    engine = get_engine()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


def test_ensure_defaults_seeds_all_slugs():
    Session = get_sessionmaker()
    with Session() as db:
        IndustryService.ensure_defaults(db)
        slugs = {r["slug"] for r in IndustryService.list_industries_admin(db)}
        for item in DEFAULT_INDUSTRIES:
            assert item["slug"] in slugs


def test_create_update_and_disable_without_survey_types():
    Session = get_sessionmaker()
    with Session() as db:
        row = IndustryService.create_industry(
            db,
            {"name": "Retail", "slug": "retail", "sort_order": 15},
        )
        assert row.slug == "retail"
        updated = IndustryService.update_industry(db, row, {"name": "Retail & CPG"})
        assert updated.name == "Retail & CPG"
        disabled = IndustryService.set_active(db, updated, is_active=False)
        assert disabled.is_active is False
        active_list = IndustryService.list_industries(db, active_only=True)
        assert not any(i["id"] == row.id for i in active_list)


def test_cannot_disable_industry_with_survey_types():
    Session = get_sessionmaker()
    with Session() as db:
        industry = IndustryService.get_by_slug(db, "healthcare")
        SurveyTypeService.create_type(
            db,
            {"name": "HC Test", "slug": "hc_test_type", "industry_id": industry.id},
        )
        with pytest.raises(ValueError, match="survey types"):
            IndustryService.set_active(db, industry, is_active=False)


def test_duplicate_slug_rejected():
    Session = get_sessionmaker()
    with Session() as db:
        IndustryService.ensure_defaults(db)
        with pytest.raises(ValueError, match="already exists"):
            IndustryService.create_industry(db, {"name": "Dup", "slug": "healthcare"})
