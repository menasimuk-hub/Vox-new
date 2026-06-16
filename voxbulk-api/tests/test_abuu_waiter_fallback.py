"""DeepSeek timeout fallback for waiter reply composer."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.abuu.agent.session import Session as AgentSession
from app.abuu.conversation.action_runner import ActionResult
from app.abuu.conversation.fact_bundle import FactBundle
from app.abuu.conversation.intent_router import AbuuIntent
from app.abuu.waiter.deepseek_client import DeepSeekResult, WaiterDeepSeekClient
from app.abuu.waiter.reply_composer import WaiterReplyComposer


def test_reply_composer_uses_template_on_deepseek_fallback():
    session = AgentSession(customer_wa_number="+972509991301", language="ar")
    intent = AbuuIntent(name="food_search", categories=["chicken"], confidence=0.9)
    facts = FactBundle(intent="food_search", customer_lines=["• دجاج — 45 ₪"])
    action = ActionResult(action="none")
    customer = MagicMock()

    with patch.object(WaiterDeepSeekClient, "complete", return_value=DeepSeekResult(text="", fallback_used=True)):
        reply = WaiterReplyComposer.compose(
            MagicMock(),
            intent,
            facts,
            action,
            session,
            customer=customer,
            user_text="دجاج",
            deepseek_ready=True,
        )
    assert reply
    assert "[id=" not in reply
