"""Tests for WA Survey Markdown seed parser and DB seed."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.database import get_sessionmaker
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.survey_industry_seed_service import SurveyIndustrySeedService
from app.services.survey_wa_md_seed_service import SurveyWaMdSeedService, parse_md_survey_pack


SAMPLE_MD = """\
Morale
📈 How would you describe the current mood and spirit within our team?
A) Low B) Moderate C) High

Work-life balance
⚖️ How well are you able to separate work from personal time?
A) Poorly B) Adequately C) Very well
"""


@pytest.fixture(autouse=True)
def _schema():
    from app.core.database import Base, get_engine
    import app.models  # noqa: F401

    engine = get_engine()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


def test_parse_md_survey_pack_reads_blocks():
    pack = parse_md_survey_pack(SAMPLE_MD)
    assert not pack.parse_errors
    assert len(pack.questions) == 2
    assert pack.questions[0].name == "Morale"
    assert "mood and spirit" in pack.questions[0].body
    assert pack.questions[0].options == ["Low", "Moderate", "High"]
    assert pack.questions[0].wizard_description == pack.questions[0].body


def test_seed_from_markdown_file_creates_templates():
    md_path = Path(__file__).resolve().parents[1] / "seed-data/wa-survey/employee-experience.md"
    with get_sessionmaker()() as db:
        SurveyIndustrySeedService.ensure_catalog(db)
        result = SurveyWaMdSeedService.seed_from_markdown_file(
            db,
            md_path=md_path,
            industry_slug="employee_survey",
            overwrite_templates=True,
        )
        assert result["ok"] is True
        assert result["question_count"] == 20
        assert result["templates_created"] >= 1

        morale_row = next(row for row in result["rows"] if row["survey_type_name"] == "Morale")
        tpl = db.get(TelnyxWhatsappTemplate, morale_row["template_id"])
        assert tpl is not None
        assert tpl.step_role == "abc_choice"
        assert tpl.category == "UTILITY"
        assert tpl.privacy_mode == "off"
        assert tpl.customer_description == morale_row["wizard_description"]
        components = json.loads(tpl.draft_components_json or "[]")
        buttons = next(c for c in components if c.get("type") == "BUTTONS")["buttons"]
        assert [b["text"] for b in buttons] == ["Low", "Moderate", "High"]
