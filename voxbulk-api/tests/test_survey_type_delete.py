"""Survey type delete — templates and Telnyx cleanup."""

from __future__ import annotations

import uuid
from datetime import datetime

import pytest

from app.core.database import get_sessionmaker
from app.models.survey_type_template import SurveyTypeTemplate
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.industry_service import IndustryService
from app.services.survey_type_service import SurveyTypeService


@pytest.fixture(autouse=True)
def _schema():
    from app.core.database import Base, get_engine
    import app.models  # noqa: F401

    engine = get_engine()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


def test_delete_survey_type_removes_linked_templates(db=None):
    Session = get_sessionmaker()
    with Session() as db:
        industry = IndustryService.create_industry(db, {"name": "Retail QA", "slug": "retail_qa"})
        st = SurveyTypeService.create_type(
            db,
            {"name": "Checkout feedback", "slug": "checkout_feedback", "industry_id": industry.id},
        )
        now = datetime.utcnow()
        local_id = f"local-{uuid.uuid4().hex}"
        tpl = TelnyxWhatsappTemplate(
            telnyx_record_id=local_id,
            template_id=local_id,
            name="voxbulk_survey_checkout_feedback",
            language="en_US",
            category="MARKETING",
            status="APPROVED",
            industry_id=industry.id,
            survey_type_id=st.id,
            body_preview="Hi",
            draft_components_json='[{"type":"BODY","text":"Hi {{1}}"}]',
            local_sync_status="draft",
            active_for_survey=True,
            created_at=now,
            updated_at=now,
            synced_at=now,
        )
        db.add(tpl)
        db.flush()
        db.add(
            SurveyTypeTemplate(
                survey_type_id=st.id,
                template_id=int(tpl.id),
                industry_id=industry.id,
                usable_as_standard=True,
                usable_as_anonymous=False,
            )
        )
        db.commit()

        type_id = st.id
        template_id = int(tpl.id)
        result = SurveyTypeService.delete_type(db, st)
        assert result["ok"] is True
        assert result["deleted_templates"] == 1
        assert SurveyTypeService.get_type(db, type_id) is None
        assert db.get(TelnyxWhatsappTemplate, template_id) is None


def test_delete_system_survey_type_blocked():
    Session = get_sessionmaker()
    with Session() as db:
        from app.services.survey_system_template_service import SurveySystemTemplateService

        types = SurveySystemTemplateService.ensure_system_survey_types(db)
        welcome = next(t for t in types if t.system_template_kind == "welcome")
        with pytest.raises(ValueError, match="System survey template types"):
            SurveyTypeService.delete_type(db, welcome)
