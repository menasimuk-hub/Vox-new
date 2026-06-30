from app.models.agent import AgentDefinition
from app.services.interview_agent_display_service import interview_agent_dialect_meta


def test_sultan_dialect_meta():
    agent = AgentDefinition(
        name="interview_AR-Sultan",
        slug="interview-ar-sultan",
        voice_label="Sultan",
        voice_type_label="Saudi Gulf · ElevenLabs Sultan",
        system_prompt="test",
    )
    meta = interview_agent_dialect_meta(agent)
    assert meta["dialect_code"] == "SA"
    assert "Saudi" in meta["dialect_label"]


def test_jammal_dialect_meta():
    agent = AgentDefinition(
        name="Jamal - Ar",
        slug="jamal-ar",
        voice_label="Jammal",
        voice_type_label="Egyptian",
        system_prompt="test",
    )
    meta = interview_agent_dialect_meta(agent)
    assert meta["dialect_code"] == "EG"
    assert "Egyptian" in meta["dialect_label"]
