"""Tests for grounded VoxBulk application-aware assistant."""

from __future__ import annotations

from app.services.assistant.intent import classify_intent
from app.services.assistant.policy_gate import check_policy


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
