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
        "app.services.survey_whatsapp_template_service.TelnyxWhatsappTemplateSyncService.fetch_from_telnyx",
        lambda db: remote,
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
