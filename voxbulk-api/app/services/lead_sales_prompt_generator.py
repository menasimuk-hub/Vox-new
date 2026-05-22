from __future__ import annotations

import json
import re

from sqlalchemy.orm import Session

from app.services.agents.base import AgentMessage
from app.constants.frontpage_consent import SALES_RECORDING_NOTICE_SHORT
from app.services.providers.openai_service import OpenAIProviderService

_META = (
    "You are an expert prompt engineer for outbound B2B sales voice agents (Telnyx AI).\n\n"
    "Write ONLY the lead-specific guidance section for a scheduled follow-up sales call.\n\n"
    "Output rules:\n"
    "- Return ONLY plain text (no JSON, no markdown fences).\n"
    "- British English. Confident, consultative, never pushy.\n"
    "- At least 12 short paragraphs or bullet groups — be thorough, not a one-paragraph summary.\n"
    "- The master script and full knowledge base are appended separately — do NOT repeat them verbatim.\n"
    "- Do NOT write the opening greeting or first spoken line — Telnyx speaks the greeting from a separate field.\n"
    "- Do NOT say 'Hi, I'm…' or write dialogue for the first turn.\n"
    "- Reference what they asked about on the website call; do not invent names not in the transcript.\n"
    "- The outbound agent is Adam. The website intake agent is Jode — no live transfer.\n"
    "- Handle objections; aim for a clear next step.\n"
    "- If soft no, mention they can reply SEND OFFER on WhatsApp for their trial link.\n"
    f"- Include this rule verbatim somewhere: {SALES_RECORDING_NOTICE_SHORT}"
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
            f"Operator playbook (for context only — do not copy verbatim):\n{(playbook or '').strip()[:8000] or 'Close professionally.'}",
            "Write the lead-specific guidance section now.",
        ]
    )
    result = OpenAIProviderService.complete(
        db,
        system_prompt=_META,
        messages=[AgentMessage(role="user", content=user)],
        max_tokens=2500,
        temperature=0.35,
        provider="deepseek",
    )
    text = str(result.assistant_text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:\w+)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    if not text:
        raise ValueError("Empty sales prompt from DeepSeek")
    if len(text) < 400:
        raise ValueError("Sales prompt too short from DeepSeek — use Use KB as prompt on master script or retry generate")
    return text
