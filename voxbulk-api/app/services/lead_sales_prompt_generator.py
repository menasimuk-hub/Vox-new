from __future__ import annotations

import json
import re

from sqlalchemy.orm import Session

from app.services.agents.base import AgentMessage
from app.services.providers.openai_service import OpenAIProviderService

_META = """You write a SHORT lead-specific fact block for one outbound sales call.

Output rules:
- Plain text only. No JSON, no markdown fences, no dialogue script, no quoted lines to speak.
- Maximum 8 bullet points. Each bullet one line.
- Facts only: name, company, interest, objections heard, callback time, tone from Jode call, one recommended next step.
- Do NOT repeat the master sales script. Do NOT write opening greeting. Adam's greeting is separate.
- Do NOT ask to re-confirm phone at call start unless Jode flagged the number as uncertain."""


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
            f"Structured facts:\n{payload_block}",
            f"Jode transcript excerpt:\n{transcript_excerpt[:2500] if transcript_excerpt else '(none)'}",
            "Write the lead-specific fact bullets now.",
        ]
    )
    result = OpenAIProviderService.complete(
        db,
        system_prompt=_META,
        messages=[AgentMessage(role="user", content=user)],
        max_tokens=600,
        temperature=0.25,
        provider="deepseek",
    )
    text = str(result.assistant_text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:\w+)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    if not text:
        raise ValueError("Empty lead facts from DeepSeek")
    if len(text) > 2000:
        text = text[:2000].rsplit("\n", 1)[0]
    return text
