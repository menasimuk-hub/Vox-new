"""Smart Waiter Agent — opt-in DeepSeek tool-calling pipeline for Abuu WhatsApp ordering.

Goals (vs the current chat-only ``agent`` mode):
- LLM controls the cart by calling tools with real menu item ids (no fuzzy drift).
- Tool results expose allergen/dietary/recipe/protein tags so the model can reason and explain.
- Allergies are merged from each message AND persisted on the customer profile.
- Confirm is the single source of truth: confirm_draft + mark_paid_manual + optional webhook.
"""

from app.abuu.smart_agent.runner import SmartWaiterAgent

__all__ = ["SmartWaiterAgent"]
