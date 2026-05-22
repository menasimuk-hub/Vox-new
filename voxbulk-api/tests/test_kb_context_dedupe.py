from app.services.knowledge_base_service import kb_context_already_in_prompt


def test_kb_context_already_in_prompt_detects_embedded():
    kb = "### services.md\nVOXBULK is an AI voice platform for dental teams."
    master = f"Behaviour rules here.\n\n{kb}"
    assert kb_context_already_in_prompt(master, kb) is True


def test_kb_context_already_in_prompt_false_when_distinct():
    master = "Short behavioural prompt only."
    kb = "### pricing.md\nPlans start at specific GBP amounts."
    assert kb_context_already_in_prompt(master, kb) is False
