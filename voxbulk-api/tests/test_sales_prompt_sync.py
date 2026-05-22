from types import SimpleNamespace

from app.services.lead_sales_service import (
    SALES_KB_MARKER,
    assemble_sales_call_instructions,
    refresh_sales_prompt_kb_tail,
    sales_call_opening_greeting_for_instructions,
)


def test_assemble_sales_call_instructions_includes_kb_and_lead_context():
    settings = SimpleNamespace(
        system_prompt="Master script line",
        prompt_description="Operator note",
        kb_context="KB fact one",
    )
    task = SimpleNamespace(
        contact_name="Jane",
        company_name="Acme",
        phone="+441234",
        email="j@acme.com",
        interest_summary="Dental trial",
        sales_intent="Trial",
        scheduled_at=None,
        callback_timezone=None,
    )
    out = assemble_sales_call_instructions(
        settings,
        task,
        lead_custom="Lead-specific guidance here",
        transcript_excerpt="Visitor asked about pricing",
    )
    assert "Master script line" in out
    assert "Lead-specific guidance" in out
    assert "Jane" in out
    assert SALES_KB_MARKER in out
    assert "KB fact one" in out
    assert "Operator note" in out


def test_refresh_sales_prompt_kb_tail_replaces_old_kb():
    base = f"Intro\n\n{SALES_KB_MARKER} (authoritative — follow closely)\nold kb"
    out = refresh_sales_prompt_kb_tail(base, "new kb text")
    assert "old kb" not in out
    assert "new kb text" in out


def test_greeting_is_separate_from_instructions():
    instructions = "Hi, I'm Adam from VoxBulk — thanks for taking our call. Is now a good time?"
    greeting = sales_call_opening_greeting_for_instructions(instructions, contact_name="Jane Smith")
    assert "Jane" in greeting
    assert "recorded" in greeting.lower()
    assert greeting != instructions
