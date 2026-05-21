from __future__ import annotations

import json
import re

from sqlalchemy.orm import Session

from app.services.agents.base import AgentMessage
from app.constants.frontpage_consent import SALES_RECORDING_NOTICE_SHORT
from app.services.providers.openai_service import OpenAIProviderService

_META = (
    "You are an expert prompt engineer for outbound B2B sales voice agents (Telnyx AI).\n\n"
    "Write the complete system prompt for a scheduled follow-up sales call.\n\n"
    "Output rules:\n"
    "- Return ONLY the system prompt plain text (no JSON, no markdown fences).\n"
    "- British English. Confident, consultative, never pushy or deceptive.\n"
    "- Open by confirming you are calling back as agreed and use their first name only (from Contact below).\n"
    "- Reference what they asked about on the website call; do not invent colleague or agent names not in the transcript.\n"
    "- Handle objections calmly; aim to book a clear next step or close if they are ready.\n"
    "- If they are not interested, thank them and end politely.\n"
    "- Before ending a soft no, say you will WhatsApp them and they can reply SEND OFFER anytime to receive their trial link.\n"
    "- Do not invent pricing or contract terms not provided in the lead data.\n"
    f"- Include this rule verbatim: {SALES_RECORDING_NOTICE_SHORT}"
)


def generate_lead_sales_prompt(
    db: Session,
    *,
    contact_name: str,
    company_name: str,
    interest_summary: str,
    sales_intent: str,
    lead_payload: dict,
    transcript_excerpt: str,
    playbook: str | None,
    scheduled_label: str,
) -> str:
    payload_block = json.dumps(lead_payload or {}, ensure_ascii=False, indent=2)
    user = "\n\n".join(
        [
            f"Scheduled callback: {scheduled_label}",
            f"Contact: {contact_name} at {company_name}",
            f"Interest: {interest_summary or 'Not specified'}",
            f"Sales intent: {sales_intent or 'Follow up on website enquiry'}",
            f"Structured lead facts:\n{payload_block}",
            f"Transcript excerpt:\n{transcript_excerpt[:6000] if transcript_excerpt else '(none)'}",
            f"Operator playbook:\n{(playbook or '').strip() or 'Close professionally; confirm needs; propose a clear next step.'}",
        ]
    )
    result = OpenAIProviderService.complete(
        db,
        system_prompt=_META,
        messages=[AgentMessage(role="user", content=user)],
        max_tokens=2000,
        temperature=0.35,
        provider="deepseek",
    )
    text = str(result.assistant_text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:\w+)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    if not text:
        raise ValueError("Empty sales prompt from DeepSeek")
    return text
