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
    assert "I can help with billing, usage, survey" not in out.primary_message


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
