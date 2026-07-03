"""Survey type ↔ template scoping — prevent sync from linking unrelated templates."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.core.database import get_sessionmaker
from app.models.survey_type_template import SurveyTypeTemplate
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.survey_type_service import SurveyTypeService
from app.services.survey_type_template_service import (
    SurveyTypeTemplateService,
    template_belongs_to_survey_type,
)
from app.services.survey_whatsapp_template_service import SurveyWhatsappTemplateService


@pytest.fixture(autouse=True)
def _schema():
    from app.core.database import Base, get_engine
    import app.models  # noqa: F401

    engine = get_engine()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


def _seed_types(db):
    SurveyTypeService.ensure_defaults(db)
    cs = SurveyTypeService.get_by_slug(db, "customer_satisfaction")
    sq = SurveyTypeService.get_by_slug(db, "service_quality")
    assert cs is not None and sq is not None
    return cs, sq


def _remote_template(*, slug: str, suffix: str, record_id: str | None = None) -> dict:
    rid = record_id or str(uuid.uuid4())
    return {
        "id": rid,
        "template_id": "999",
        "name": f"voxbulk_survey_{slug}_{suffix}",
        "language": "en_US",
        "status": "APPROVED",
        "category": "MARKETING",
        "components": [{"type": "BODY", "text": "Hi {{1}}", "example": {"body_text": [["Alex"]]}}],
    }


def test_scoped_sync_does_not_link_unrelated_templates(monkeypatch):
    remote = [
        _remote_template(slug="customer_satisfaction", suffix="std_intro"),
        _remote_template(slug="service_quality", suffix="std_intro"),
        {"id": str(uuid.uuid4()), "template_id": "888", "name": "generic_survey_reminder", "language": "en_US", "status": "APPROVED", "components": []},
    ]
    monkeypatch.setattr(
        "app.services.survey_whatsapp_template_service.TelnyxWhatsappTemplateSyncService.fetch_remote_templates",
        lambda db, filter_waba_id=True: remote,
    )

    with get_sessionmaker()() as db:
        cs, sq = _seed_types(db)
        summary = SurveyWhatsappTemplateService.sync_from_telnyx(db, survey_type_id=cs.id)
        assert summary["survey_matched"] == 3

        cs_links = SurveyTypeTemplateService.list_for_survey_type(db, cs.id)
        cs_ids = {m.template_id for m in cs_links}
        assert len(cs_ids) == 1

        sq_links = SurveyTypeTemplateService.list_for_survey_type(db, sq.id)
        assert len(sq_links) == 0

        listed = SurveyWhatsappTemplateService.list_for_survey_type(db, cs.id)
        assert len(listed) == 1
        assert "customer_satisfaction" in listed[0]["name"]


def test_cleanup_removes_mistaken_links():
    with get_sessionmaker()() as db:
        cs, sq = _seed_types(db)
        row = TelnyxWhatsappTemplate(
            telnyx_record_id=f"local-{uuid.uuid4().hex}",
            template_id=f"local-{uuid.uuid4().hex}",
            name="voxbulk_survey_service_quality_std_intro",
            display_name="Wrong link",
            language="en_US",
            status="LOCAL_DRAFT",
            survey_type_id=sq.id,
            active_for_survey=True,
        )
        db.add(row)
        db.flush()
        db.add(
            SurveyTypeTemplate(
                industry_id=cs.industry_id,
                survey_type_id=cs.id,
                template_id=row.id,
                usable_as_standard=True,
            )
        )
        db.commit()

        assert len(SurveyWhatsappTemplateService.list_for_survey_type(db, cs.id)) == 0
        result = SurveyTypeTemplateService.cleanup_mistaken_links(db, survey_type_id=cs.id, dry_run=False)
        assert result["removed"] == 1
        assert len(SurveyWhatsappTemplateService.list_for_survey_type(db, cs.id)) == 0


def test_list_for_survey_type_includes_hidden_by_default_and_can_filter_for_dashboard():
    with get_sessionmaker()() as db:
        cs, _ = _seed_types(db)
        active_tpl = TelnyxWhatsappTemplate(
            telnyx_record_id=f"local-{uuid.uuid4().hex}",
            template_id=f"local-{uuid.uuid4().hex}",
            name="voxbulk_survey_customer_satisfaction_std_visible",
            language="en_US",
            status="LOCAL_DRAFT",
            survey_type_id=cs.id,
            active_for_survey=True,
        )
        hidden_tpl = TelnyxWhatsappTemplate(
            telnyx_record_id=f"local-{uuid.uuid4().hex}",
            template_id=f"local-{uuid.uuid4().hex}",
            name="voxbulk_survey_customer_satisfaction_std_hidden",
            language="en_US",
            status="LOCAL_DRAFT",
            survey_type_id=cs.id,
            active_for_survey=False,
        )
        db.add(active_tpl)
        db.add(hidden_tpl)
        db.flush()
        db.add(
            SurveyTypeTemplate(
                industry_id=cs.industry_id,
                survey_type_id=cs.id,
                template_id=active_tpl.id,
                usable_as_standard=True,
            )
        )
        db.add(
            SurveyTypeTemplate(
                industry_id=cs.industry_id,
                survey_type_id=cs.id,
                template_id=hidden_tpl.id,
                usable_as_standard=True,
            )
        )
        db.commit()

        admin_listed = SurveyWhatsappTemplateService.list_for_survey_type(db, cs.id)
        admin_ids = {int(item["id"]) for item in admin_listed}
        assert active_tpl.id in admin_ids
        assert hidden_tpl.id in admin_ids

        dashboard_listed = SurveyWhatsappTemplateService.list_for_survey_type(db, cs.id, include_inactive=False)
        dashboard_ids = {int(item["id"]) for item in dashboard_listed}
        assert active_tpl.id in dashboard_ids
        assert hidden_tpl.id not in dashboard_ids


def test_template_belongs_uses_survey_type_id():
    with get_sessionmaker()() as db:
        cs, _ = _seed_types(db)
        row = TelnyxWhatsappTemplate(
            telnyx_record_id="x",
            template_id="x",
            name="unrelated_name",
            language="en_US",
            status="LOCAL_DRAFT",
            survey_type_id=cs.id,
            active_for_survey=True,
        )
        assert template_belongs_to_survey_type(row, cs) is True


def test_admin_list_includes_mapped_meta_rows_without_name_match():
    """Meta-synced rows may lack survey_type_id / matching name; admin must still list mappings."""
    with get_sessionmaker()() as db:
        cs, _ = _seed_types(db)
        meta_row = TelnyxWhatsappTemplate(
            telnyx_record_id="meta-12345",
            template_id="12345",
            name="generic_meta_template_name",
            language="en_US",
            status="APPROVED",
            survey_type_id=None,
            industry_id=None,
            active_for_survey=True,
        )
        db.add(meta_row)
        db.flush()
        db.add(
            SurveyTypeTemplate(
                industry_id=cs.industry_id,
                survey_type_id=cs.id,
                template_id=meta_row.id,
                usable_as_standard=True,
            )
        )
        db.commit()

        strict = SurveyWhatsappTemplateService.list_for_survey_type(db, cs.id, strict_scope=True)
        assert len(strict) == 0

        admin = SurveyWhatsappTemplateService.list_for_survey_type(db, cs.id, strict_scope=False)
        assert len(admin) == 1
        assert admin[0]["id"] == meta_row.id
        assert str(admin[0]["status"]).upper() == "APPROVED"


def test_repair_creates_mapping_for_owned_template_without_mapping():
    """Templates with survey_type_id but no mapping row get repaired."""
    with get_sessionmaker()() as db:
        cs, _ = _seed_types(db)
        row = TelnyxWhatsappTemplate(
            telnyx_record_id=f"meta-{uuid.uuid4().hex[:8]}",
            template_id="555",
            name="voxbulk_survey_customer_satisfaction_abc_de3a48",
            language="en_US",
            status="APPROVED",
            survey_type_id=cs.id,
            industry_id=cs.industry_id,
            active_for_survey=True,
        )
        db.add(row)
        db.commit()

        assert SurveyTypeTemplateService.list_for_survey_type(db, cs.id) == []
        result = SurveyWhatsappTemplateService.repair_survey_type_mappings(db)
        assert result["repaired"] == 1
        links = SurveyTypeTemplateService.list_for_survey_type(db, cs.id)
        assert len(links) == 1
        assert links[0].template_id == row.id


def test_shared_slug_links_only_matching_industry():
    """Shared topic slug across industries links via industry_id, not inventing a link."""
    from app.services.industry_service import IndustryService

    with get_sessionmaker()() as db:
        ind_a = IndustryService.create_industry(db, {"name": "Industry A", "slug": "industry_a_link"})
        ind_b = IndustryService.create_industry(db, {"name": "Industry B", "slug": "industry_b_link"})
        type_a = SurveyTypeService.create_type(
            db,
            {"name": "Would Recommend", "slug": "would_recommend", "industry_id": ind_a.id},
        )
        type_b = SurveyTypeService.create_type(
            db,
            {"name": "Would Recommend", "slug": "would_recommend", "industry_id": ind_b.id},
        )
        row = TelnyxWhatsappTemplate(
            telnyx_record_id=f"meta-{uuid.uuid4().hex[:8]}",
            template_id="777",
            name="voxbulk_survey_would_recommend_abc_a7145a",
            language="en_US",
            status="APPROVED",
            survey_type_id=None,
            industry_id=ind_a.id,
            active_for_survey=True,
        )
        db.add(row)
        db.commit()

        linked = SurveyWhatsappTemplateService._ensure_mapping_for_sync(
            db,
            template=row,
            name=row.name,
            survey_type_id=None,
        )
        db.commit()
        assert linked is True
        assert len(SurveyTypeTemplateService.list_for_survey_type(db, type_a.id)) == 1
        assert len(SurveyTypeTemplateService.list_for_survey_type(db, type_b.id)) == 0
        assert str(row.survey_type_id) == str(type_a.id)


def test_shared_slug_without_ownership_does_not_invent_link():
    """Ambiguous shared slug with no survey_type_id / industry_id must not invent a mapping."""
    from app.services.industry_service import IndustryService

    with get_sessionmaker()() as db:
        ind_a = IndustryService.create_industry(db, {"name": "Industry A2", "slug": "industry_a2_link"})
        ind_b = IndustryService.create_industry(db, {"name": "Industry B2", "slug": "industry_b2_link"})
        SurveyTypeService.create_type(
            db,
            {"name": "Viewing Experience", "slug": "viewing_experience", "industry_id": ind_a.id},
        )
        SurveyTypeService.create_type(
            db,
            {"name": "Viewing Experience", "slug": "viewing_experience", "industry_id": ind_b.id},
        )
        row = TelnyxWhatsappTemplate(
            telnyx_record_id=f"meta-{uuid.uuid4().hex[:8]}",
            template_id="888",
            name="voxbulk_survey_viewing_experience_abc_111111",
            language="en_US",
            status="APPROVED",
            survey_type_id=None,
            industry_id=None,
            active_for_survey=True,
        )
        db.add(row)
        db.commit()

        linked = SurveyWhatsappTemplateService._ensure_mapping_for_sync(
            db,
            template=row,
            name=row.name,
            survey_type_id=None,
        )
        assert linked is False
        assert row.survey_type_id is None


def test_relink_repairs_owned_templates():
    with get_sessionmaker()() as db:
        cs, _ = _seed_types(db)
        row = TelnyxWhatsappTemplate(
            telnyx_record_id=f"meta-{uuid.uuid4().hex[:8]}",
            template_id="999",
            name="voxbulk_survey_customer_satisfaction_utu_abcdef",
            language="en_US",
            status="APPROVED",
            survey_type_id=cs.id,
            industry_id=cs.industry_id,
            active_for_survey=True,
        )
        db.add(row)
        db.commit()

        result = SurveyWhatsappTemplateService.relink_survey_templates(db)
        assert result["linked_to_survey_type"] >= 1
        assert len(SurveyTypeTemplateService.list_for_survey_type(db, cs.id)) == 1
