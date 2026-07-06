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


def test_delete_industry_with_survey_types():
    Session = get_sessionmaker()
    with Session() as db:
        industry = IndustryService.get_by_slug(db, "healthcare")
        SurveyTypeService.create_type(
            db,
            {"name": "HC Test", "slug": "hc_test_type", "industry_id": industry.id},
        )
        industry_id = industry.id
        result = IndustryService.delete_industry(db, industry)
        assert result["ok"] is True
        assert result["deleted_survey_types"] == 1
        assert IndustryService.get_industry(db, industry_id) is None


def test_deleted_default_industry_is_not_resurrected_on_list():
    Session = get_sessionmaker()
    with Session() as db:
        industry = IndustryService.get_by_slug(db, "healthcare")
        assert industry is not None
        IndustryService.delete_industry(db, industry)
        IndustryService.list_industries(db, active_only=True)
        IndustryService.list_industries_admin(db)
        assert IndustryService.get_by_slug(db, "healthcare") is None
        assert IndustryService.is_slug_tombstoned(db, "healthcare") is True


def test_ensure_catalog_skips_tombstoned_industry():
    from app.services.survey_industry_seed_service import SurveyIndustrySeedService

    Session = get_sessionmaker()
    with Session() as db:
        industry = IndustryService.get_by_slug(db, "healthcare")
        IndustryService.delete_industry(db, industry)
        SurveyIndustrySeedService.ensure_catalog(db)
        assert IndustryService.get_by_slug(db, "healthcare") is None


def test_delete_industry_with_survey_session():
    Session = get_sessionmaker()
    with Session() as db:
        from app.models.survey_session import SurveySession

        industry = IndustryService.get_by_slug(db, "healthcare")
        st = SurveyTypeService.create_type(
            db,
            {"name": "HC Session Test", "slug": "hc_session_test", "industry_id": industry.id},
        )
        session = SurveySession(
            id=str(__import__("uuid").uuid4()),
            order_id=str(__import__("uuid").uuid4()),
            recipient_id=str(__import__("uuid").uuid4()),
            org_id=str(__import__("uuid").uuid4()),
            survey_type_id=st.id,
        )
        db.add(session)
        db.commit()
        result = IndustryService.delete_industry(db, industry)
        assert result["ok"] is True
        db.refresh(session)
        assert session.survey_type_id is None
        assert IndustryService.get_industry(db, industry.id) is None


def test_wa_survey_overview_counts():
    from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
    from datetime import datetime
    import uuid

    Session = get_sessionmaker()
    with Session() as db:
        IndustryService.ensure_defaults(db)
        healthcare = IndustryService.get_by_slug(db, "healthcare")
        SurveyTypeService.create_type(
            db,
            {"name": "HC Overview", "slug": "hc_overview_type", "industry_id": healthcare.id},
        )
        now = datetime.utcnow()
        local_id = f"local-{uuid.uuid4().hex}"
        tpl = TelnyxWhatsappTemplate(
            telnyx_record_id=local_id,
            template_id=local_id,
            name="voxbulk_survey_hc_overview_test",
            language="en_US",
            category="MARKETING",
            status="APPROVED",
            industry_id=healthcare.id,
            body_preview="Hi",
            draft_components_json='[{"type":"BODY","text":"Hi {{1}}"}]',
            local_sync_status="draft",
            active_for_survey=True,
            created_at=now,
            updated_at=now,
            synced_at=now,
        )
        db.add(tpl)
        db.commit()

        overview = IndustryService.wa_survey_overview(db)
        assert overview["kpis"]["total_templates"] >= 1
        assert overview["kpis"]["approved_templates"] >= 1
        hc_row = next(row for row in overview["industries"] if row["slug"] == "healthcare")
        assert hc_row["survey_type_count"] >= 1
        assert hc_row["template_count"] >= 1
        assert hc_row["approved_template_count"] >= 1


def test_wa_survey_overview_fast_skips_template_scan():
    Session = get_sessionmaker()
    with Session() as db:
        IndustryService.ensure_defaults(db)
        overview = IndustryService.wa_survey_overview(db, fast=True)
        assert overview.get("fast") is True
        assert len(overview.get("industries") or []) >= 1
        hc_row = next(row for row in overview["industries"] if row["slug"] == "healthcare")
        assert hc_row.get("template_count") is None


def test_duplicate_slug_rejected():
    Session = get_sessionmaker()
    with Session() as db:
        IndustryService.ensure_defaults(db)
        with pytest.raises(ValueError, match="already exists"):
            IndustryService.create_industry(db, {"name": "Dup", "slug": "healthcare"})
