"""Tests for grounded VoxBulk application-aware assistant."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.core.dependencies import CurrentPrincipal
from app.core.security import hash_password
from app.schemas.assistant import AssistantChatIn
from app.services.assistant.intent import classify_intent
from app.services.assistant.orchestrator import AssistantOrchestrator
from app.services.assistant.policy_gate import check_policy
from app.services.assistant.safe_tools import INVOICE_READ_ERROR
from app.services.assistant.tools import AssistantTools


def _seed_org_user(db):
    from app.models.membership import OrganisationMembership
    from app.models.organisation import Organisation
    from app.models.user import User

    org = Organisation(name="Assistant Test Org")
    db.add(org)
    db.flush()
    user = User(email="wallet.user@test.com", password_hash=hash_password("pass123"), is_active=True)
    db.add(user)
    db.flush()
    db.add(OrganisationMembership(org_id=org.id, user_id=user.id, role="owner"))
    db.commit()
    return user, org


def test_policy_blocks_hard_delete():
    decision = check_policy("hard delete all candidate records")
    assert decision.allowed is False


def test_policy_blocks_webhook_modification():
    decision = check_policy("disable telnyx webhook integration")
    assert decision.allowed is False


def test_intent_wallet_low():
    match = classify_intent("Why is my wallet so low?")
    assert match.intent == "wallet_low"


def test_intent_product_compare():
    match = classify_intent("What is the difference between survey and feedback?")
    assert match.intent == "product_compare"


def test_intent_launch_check():
    match = classify_intent("Can I launch my survey campaign today?")
    assert match.intent == "launch_check"


def test_intent_manage_services():
    match = classify_intent("how to change my services?")
    assert match.intent == "manage_services"


@pytest.mark.parametrize(
    "message",
    [
        "how do I enable surveys in the sidebar",
        "turn off interviews module",
        "manage my services",
    ],
)
def test_intent_manage_services_variants(message):
    match = classify_intent(message)
    assert match.intent == "manage_services"


@pytest.mark.parametrize(
    "message,expected",
    [
        ("create a custom template", "create_template"),
        ("Why is my wallet so low?", "wallet_low"),
        ("can I launch", "launch_check"),
        ("show survey results", "survey_results"),
        ("create support ticket", "create_ticket"),
    ],
)
def test_intent_routing_prioritizes_explicit_task(message, expected):
    match = classify_intent(message)
    assert match.intent == expected


def test_policy_blocks_billing_tampering():
    decision = check_policy("void my invoice without paying")
    assert decision.allowed is False


def test_pending_action_token_exceeds_legacy_confirm_limit():
    from app.services.assistant.pending_actions import issue_pending_action

    token = issue_pending_action(
        org_id="org-1",
        user_id="user-1",
        action_type="create_support_ticket",
        payload={"category": "technical", "subject": "Test subject", "message": "A" * 200},
    )
    assert len(token) > 128


def test_wallet_low_invoice_failure_returns_safe_fallback(app_client):
    from app.core.database import get_sessionmaker

    with get_sessionmaker()() as db:
        user, org = _seed_org_user(db)

    principal = CurrentPrincipal(user_id=user.id, org_id=org.id, token_payload={})
    payload = AssistantChatIn(message="Why is my wallet so low?")

    with patch.object(
        AssistantTools,
        "invoices",
        side_effect=TypeError("InvoiceService.invoice_to_dict() missing 1 required positional argument: 'invoice'"),
    ):
        with get_sessionmaker()() as db:
            out = AssistantOrchestrator.handle_chat(db, principal=principal, payload=payload)

    assert out.primary_message
    assert "invoice_to_dict" not in out.primary_message
    assert "missing 1 required positional argument" not in out.primary_message
    assert "Traceback" not in out.primary_message
    assert INVOICE_READ_ERROR in out.primary_message
    assert out.blocking_reason == INVOICE_READ_ERROR
    assert out.highlight_type in {"", "wallet_transaction", "service_order", "usage"}
    assert any(a.route in {"/account/billing", "/account/usage"} for a in out.next_actions)
    assert out.confidence > 0


def test_greeting_welcomes_user_by_name(app_client):
    from app.core.database import get_sessionmaker

    with get_sessionmaker()() as db:
        user, org = _seed_org_user(db)

    principal = CurrentPrincipal(user_id=user.id, org_id=org.id, token_payload={})
    with get_sessionmaker()() as db:
        out = AssistantOrchestrator.handle_chat(db, principal=principal, payload=AssistantChatIn(message="Hello"))

    assert "Hi Wallet" in out.primary_message
    assert "read-only" in out.primary_message.lower()


def test_create_template_not_overridden_by_billing_state(app_client):
    from app.core.database import get_sessionmaker

    with get_sessionmaker()() as db:
        user, org = _seed_org_user(db)

    principal = CurrentPrincipal(user_id=user.id, org_id=org.id, token_payload={})
    exhausted_access = {
        "next_action_label": "Package exhausted — launches can use wallet balance.",
        "next_action": "top_up_wallet",
        "block_reason": "",
    }

    with patch.object(AssistantTools, "billing_access", return_value=exhausted_access):
        with get_sessionmaker()() as db:
            out = AssistantOrchestrator.handle_chat(
                db,
                principal=principal,
                payload=AssistantChatIn(message="create a custom template"),
            )

    assert out.intent == "create_template"
    assert "billing needs attention" not in out.primary_message
    assert "Package exhausted" not in out.primary_message
    assert "template" in out.primary_message.lower()
    assert any(a.route == "/surveys/new?channel=whatsapp" for a in out.next_actions)


def test_registry_includes_all_intents_in_prompt():
    from app.services.assistant.prompt_builder import build_classify_system_prompt
    from app.services.assistant.service_registry import registry_intent_names

    prompt = build_classify_system_prompt()
    for name in registry_intent_names():
        assert name in prompt


def test_support_report_token_dedupe(app_client):
    from app.core.database import get_sessionmaker
    from app.services.assistant.support_report import issue_support_report_token

    with get_sessionmaker()() as db:
        user, org = _seed_org_user(db)

    token = issue_support_report_token(
        org_id=org.id,
        user_id=user.id,
        payload={"user_message": "test", "intent": "wallet_low", "error_code": "tool_failed"},
    )

    headers = {"Authorization": f"Bearer {_token_for(user, org)}"}
    r1 = app_client.post("/assistant/report-support", json={"support_report_token": token}, headers=headers)
    assert r1.status_code == 200
    body1 = r1.json()
    assert body1["ok"] is True
    assert body1["ticket_ref"]

    r2 = app_client.post("/assistant/report-support", json={"support_report_token": token}, headers=headers)
    assert r2.status_code == 200
    body2 = r2.json()
    assert body2["already_reported"] is True
    assert body2["ticket_ref"] == body1["ticket_ref"]


def test_llm_path_wallet_low_without_llm(app_client, monkeypatch):
    from app.core.config import get_settings
    from app.core.database import get_sessionmaker

    monkeypatch.setenv("ASSISTANT_LLM_ENABLED", "true")
    get_settings.cache_clear()

    with get_sessionmaker()() as db:
        user, org = _seed_org_user(db)

    headers = {"Authorization": f"Bearer {_token_for(user, org)}"}
    r = app_client.post("/assistant/chat", json={"message": "Why is my wallet so low?"}, headers=headers)
    assert r.status_code == 200
    out = r.json()
    assert out["primary_message"]
    assert "Traceback" not in out["primary_message"]


def _token_for(user, org) -> str:
    from app.core.security import create_access_token

    return create_access_token(subject=str(user.id), org_id=str(org.id))


def test_policy_coach_includes_suggestions():
    from app.services.assistant.policy_coach import build_policy_refusal_response

    decision = check_policy("void my invoice without paying")
    assert decision.allowed is False
    assert len(decision.suggested_prompts) >= 2
    assert decision.nav_route == "/account/billing"

    out = build_policy_refusal_response(
        reason=decision.reason or "",
        suggested_prompts=list(decision.suggested_prompts),
        nav_route=decision.nav_route,
    )
    assert out.policy_refused is True
    assert out.suggested_prompts
    assert any(a.route == "/account/billing" for a in out.next_actions)


def test_dashboard_catalog_coverage():
    from app.services.assistant.dashboard_catalog import CATALOG, catalog_for_prompt

    assert len(CATALOG) >= 25
    routes = {e.route for e in CATALOG}
    assert "/recovery" in routes
    assert "/follow-up" in routes
    assert "/account/support/faq" in routes
    assert "/settings/integrations" in routes

    filtered = catalog_for_prompt(enabled_services=["surveys"])
    titles = {e.title for e in filtered}
    assert "Surveys" in titles
    assert "Recovery" not in titles


def test_should_delegate_rich_handlers():
    from app.services.assistant.assistant_llm import should_delegate_to_handler

    assert should_delegate_to_handler("create_survey") is True
    assert should_delegate_to_handler("create_template") is True
    assert should_delegate_to_handler("product_compare") is True
    assert should_delegate_to_handler("create_ticket") is True
    assert should_delegate_to_handler("general_help") is True
    assert should_delegate_to_handler("wallet_low") is False


def test_assistant_llm_provider_config(app_client, monkeypatch):
    from app.core.config import get_settings
    from app.services.assistant.assistant_llm import assistant_llm_provider

    monkeypatch.setenv("ASSISTANT_LLM_PROVIDER", "deepinfra")
    get_settings.cache_clear()

    from app.core.database import get_sessionmaker

    with get_sessionmaker()() as db:
        assert assistant_llm_provider(db) == "deepinfra"


@pytest.mark.parametrize(
    "message,expected",
    [
        ("list my support tickets", "list_tickets"),
        ("show invoice details", "invoice_detail"),
        ("create an interview campaign", "create_interview"),
        ("open FAQ", "open_faq"),
        ("recovery queue", "recovery_overview"),
        ("follow up reminders", "followup_overview"),
        ("survey reports", "survey_reports"),
        ("usage breakdown by campaign", "usage_breakdown"),
        ("what is my subscription plan", "billing_subscription"),
    ],
)
def test_expanded_intents(message, expected):
    match = classify_intent(message)
    assert match.intent == expected


def test_general_help_suggested_prompts(app_client):
    from app.core.database import get_sessionmaker

    with get_sessionmaker()() as db:
        user, org = _seed_org_user(db)

    principal = CurrentPrincipal(user_id=user.id, org_id=org.id, token_payload={})
    with get_sessionmaker()() as db:
        out = AssistantOrchestrator.handle_chat(
            db,
            principal=principal,
            payload=AssistantChatIn(message="something completely random xyz"),
        )

    assert out.suggested_prompts
    assert "didn't match" in out.primary_message.lower() or "not sure" in out.primary_message.lower()


def test_create_ticket_includes_diagnostic_context(app_client):
    from app.core.database import get_sessionmaker
    from app.services.assistant.pending_actions import verify_pending_action
    from app.services.assistant.ticket_diagnostic import format_assistant_diagnostic_plain_text

    with get_sessionmaker()() as db:
        user, org = _seed_org_user(db)

    principal = CurrentPrincipal(user_id=user.id, org_id=org.id, token_payload={})
    payload = AssistantChatIn(
        message="I have a billing problem with my last invoice",
        history=[{"role": "user", "text": "Hello"}, {"role": "assistant", "text": "Hi!"}],
        context={"current_route": "/account/billing", "enabled_services": ["surveys"]},
    )
    with get_sessionmaker()() as db:
        out = AssistantOrchestrator.handle_chat(db, principal=principal, payload=payload)

    assert out.intent == "create_ticket"
    assert out.pending_action is not None
    confirm = out.next_actions[0]
    assert confirm.label == "Send ticket to support"
    body = verify_pending_action(confirm.action_id, org_id=org.id, user_id=user.id)
    assert body is not None
    pending = body.get("payload") or {}
    diagnostic = pending.get("diagnostic") or {}
    assert diagnostic.get("current_route") == "/account/billing"
    assert diagnostic.get("user_message")
    assert len(diagnostic.get("recent_history") or []) >= 1
    assert "{" not in str(pending.get("message") or "")
    note = format_assistant_diagnostic_plain_text(diagnostic)
    assert "Customer request:" in note
    assert "---" not in note
    assert "user_email" not in note


def test_create_ticket_intent_beats_packages_when_opening_ticket():
    match = classify_intent("can you open a tickt and ask to upgrade my package")
    assert match.intent == "create_ticket"


def test_create_ticket_meta_request_uses_plain_customer_message(app_client):
    from app.core.database import get_sessionmaker
    from app.services.assistant.pending_actions import verify_pending_action

    with get_sessionmaker()() as db:
        user, org = _seed_org_user(db)

    principal = CurrentPrincipal(user_id=user.id, org_id=org.id, token_payload={})
    with get_sessionmaker()() as db:
        out = AssistantOrchestrator.handle_chat(
            db,
            principal=principal,
            payload=AssistantChatIn(message="open a ticket for me"),
        )

    assert out.intent == "create_ticket"
    body = verify_pending_action(out.next_actions[0].action_id, org_id=org.id, user_id=user.id)
    pending = (body or {}).get("payload") or {}
    message = str(pending.get("message") or "")
    assert "{" not in message
    assert "Assistant context" not in message
    assert "support team" in message.lower()


def test_list_interviews_returns_handler_not_generic_fallback(app_client):
    from app.core.database import get_sessionmaker

    with get_sessionmaker()() as db:
        user, org = _seed_org_user(db)

    principal = CurrentPrincipal(user_id=user.id, org_id=org.id, token_payload={})
    with get_sessionmaker()() as db:
        out = AssistantOrchestrator.handle_chat(
            db,
            principal=principal,
            payload=AssistantChatIn(message="List my interviews"),
        )

    assert out.intent == "list_interviews"
    assert "not sure I matched" not in out.primary_message.lower()


def test_billing_subscription_uses_registry_handler(app_client):
    from app.core.database import get_sessionmaker

    with get_sessionmaker()() as db:
        user, org = _seed_org_user(db)

    principal = CurrentPrincipal(user_id=user.id, org_id=org.id, token_payload={})
    with get_sessionmaker()() as db:
        out = AssistantOrchestrator.handle_chat(
            db,
            principal=principal,
            payload=AssistantChatIn(message="What is my subscription plan?"),
        )

    assert out.intent == "billing_subscription"
    assert "not sure I matched" not in out.primary_message.lower()

