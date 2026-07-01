from __future__ import annotations

from app.constants.interview_agent_regions import (
    INTERVIEW_ENGLISH_ROSTER,
    INTERVIEW_REGIONS,
    accent_region_from_org_country,
)
from app.models.agent import AgentDefinition
from app.services.interview_agent_display_service import dashboard_agent_row, interview_agent_dialect_meta
from app.services.survey_voice_agent_service import _agent_dashboard_gender, _agent_region_match, _agent_zone_match


def _agent(**kwargs) -> AgentDefinition:
    row = AgentDefinition(
        name=kwargs.get("name", "interview_US-Marcus"),
        slug=kwargs.get("slug", "interview-us-marcus"),
        system_prompt="test",
        voice_label=kwargs.get("voice_label", "Marcus"),
        voice_type_label=kwargs.get("voice_type_label", "US English · professional male"),
        accent_region=kwargs.get("accent_region"),
        gender=kwargs.get("gender"),
        supports_interview=True,
        is_active=True,
    )
    return row


def test_accent_region_from_org_country():
    assert accent_region_from_org_country("Ireland") == "IE"
    assert accent_region_from_org_country("Scotland") == "SC"
    assert accent_region_from_org_country("United States") == "US"
    assert accent_region_from_org_country("Canada") == "CA"
    assert accent_region_from_org_country("Australia") == "AU"


def test_interview_agent_dialect_meta_us_female():
    agent = _agent(accent_region="US", gender="female", voice_label="Elena", name="interview_US-Elena")
    meta = interview_agent_dialect_meta(agent)
    assert meta["dialect_code"] == "US"
    assert meta["flag_emoji"] == "🇺🇸"
    assert "Elena" in meta["sample_phrase"] or "Hi" in meta["sample_phrase"]


def test_dashboard_agent_row_includes_flag_and_gender():
    agent = _agent(accent_region="CA", gender="female", voice_label="Maya", name="interview_CA-Maya")
    row = dashboard_agent_row(agent, assigned_id=None, default_field="is_default_interview", zone="ca", org_country="Canada")
    assert row["accent_region"] == "CA"
    assert row["gender"] == "female"
    assert row["flag_emoji"] == "🇨🇦"


def test_agent_region_match_ireland():
    agent = _agent(accent_region="IE", gender="male", voice_label="Sean", name="interview_IE-Sean")
    assert _agent_region_match(agent, "Ireland") is True
    assert _agent_zone_match(agent, "eu") is True


def test_roster_has_twelve_english_agents():
    assert len(INTERVIEW_ENGLISH_ROSTER) == 12
    regions = {spec.accent_region for spec in INTERVIEW_ENGLISH_ROSTER}
    assert regions == set(INTERVIEW_REGIONS.keys())
    for region in INTERVIEW_REGIONS:
        specs = [s for s in INTERVIEW_ENGLISH_ROSTER if s.accent_region == region]
        assert len(specs) == 2
        genders = {s.gender for s in specs}
        assert genders == {"male", "female"}


def test_gender_column_overrides_heuristic():
    agent = _agent(accent_region="GB", gender="female", voice_label="Leo", name="interview_GB-Leo")
    assert _agent_dashboard_gender(agent) == "female"
