from __future__ import annotations

import json
import re

from sqlalchemy.orm import Session

from app.services.agents.base import AgentMessage
from app.services.providers.openai_service import OpenAIProviderService

_SURVEY_META = """You are an expert survey designer for VOXBULK outbound AI phone and WhatsApp surveys.
Return ONLY valid JSON with these fields:
- "intro": short opening the AI says on phone (mention recording if phone, friendly British English)
- "questions": array of 3-8 clear survey questions as strings
- "closing": short thank-you and goodbye
- "script_text": full readable script for the customer to review (intro, numbered questions, closing)
- "system_prompt": instructions for the AI agent running the survey (tone, pacing, when to probe)

British English. Practical for clinics and businesses. No markdown fences.
Never mention Voxbulk, VOXBULK, or any platform provider to the recipient — all messages are on behalf of the client's organisation."""

_SURVEY_WA_META = """You are an expert WhatsApp survey designer for VOXBULK.
Return ONLY valid JSON with these fields:
- "intro": short phone script opening (if both channels)
- "questions": array of 3-8 survey questions as plain strings (for phone / readable script)
- "closing": short thank-you
- "script_text": full readable script (intro, numbered questions, closing)
- "system_prompt": instructions for the AI agent
- "whatsapp_intro": WhatsApp opening message using {first_name} and {clinic_name} placeholders, friendly and concise
- "whatsapp_questions": array of 3-8 objects, each with:
  - "text": question shown in WhatsApp
  - "reply_type": one of "buttons", "rating", "nps", "text", "likert", "slider", "single_choice", "multi", "true_false", "long_text", "emoji", "thumbs", "time_slot", "date", "contact"
  - "options": array of quick-reply labels (rating uses ["1".."5"]; nps uses ["0".."10"]; text uses [])
- "whatsapp_closing": final WhatsApp thank-you message

Keep WhatsApp messages short (under 280 chars each). British English. No markdown fences.
Never mention Voxbulk, VOXBULK, or any platform provider — the survey is from the client's business only."""

_INTERVIEW_META = """You are an expert interview screener for VOXBULK outbound AI phone or Zoom interviews.
Return ONLY valid JSON with these fields:
- "intro": short opening the AI says (mention recording, role name)
- "questions": array of 4-10 screening questions as strings
- "closing": next steps and goodbye
- "script_text": full readable script for the customer to review (intro, numbered questions, closing)
- "system_prompt": instructions for the AI interviewer (scoring hints, follow-ups, professionalism)

British English. No markdown fences.
Never mention Voxbulk, VOXBULK, or any platform provider — the interview is on behalf of the hiring organisation only."""


def _extract_json_object(raw: str) -> dict:
    text = str(raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("AI response was not valid JSON") from None
        data = json.loads(text[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("AI response must be a JSON object")
    return data


def _format_script(intro: str, questions: list[str], closing: str) -> str:
    lines = ["INTRO", intro.strip(), "", "QUESTIONS"]
    for i, q in enumerate(questions, 1):
        lines.append(f"{i}. {str(q).strip()}")
    lines.extend(["", "CLOSING", closing.strip()])
    return "\n".join(lines)


def _guess_reply_type(question: str) -> str:
    q = question.lower()
    if any(w in q for w in ("recommend", "nps", "0-10", "0 to 10", "not likely", "very likely")):
        return "nps"
    if any(w in q for w in ("strongly disagree", "likert", "agree or disagree")):
        return "likert"
    if any(w in q for w in ("slider", "out of 100", "0 =", "100 =")):
        return "slider"
    if any(w in q for w in ("select all", "multiple", "which features")):
        return "multi"
    if any(w in q for w in ("true or false", "true/false")):
        return "true_false"
    if any(w in q for w in ("emoji", "how do you feel")):
        return "emoji"
    if any(w in q for w in ("thumb", "helpful")):
        return "thumbs"
    if any(w in q for w in ("time slot", "when would you prefer", "follow-up call")):
        return "time_slot"
    if any(w in q for w in ("when did you", "date", "last use")):
        return "date"
    if any(w in q for w in ("email", "phone number", "contact details")):
        return "contact"
    if any(w in q for w in ("describe", "in detail", "tell us more")):
        return "long_text"
    if any(w in q for w in ("rate", "scale", "1-5", "1 to 5", "score", "out of 5", "stars", "experience")):
        return "rating"
    if any(w in q for w in ("choose one", "select one", "which option", "prefer")):
        return "single_choice"
    if any(w in q for w in ("yes or no", "yes/no", "would you", "did you", "have you")):
        return "buttons"
    if any(w in q for w in ("improve", "feedback", "anything else")):
        return "text"
    return "buttons"


def _default_options(reply_type: str) -> list[str]:
    if reply_type == "rating":
        return ["1", "2", "3", "4", "5"]
    if reply_type == "nps":
        return [str(i) for i in range(11)]
    if reply_type == "likert":
        return ["Strongly Disagree", "Disagree", "Neutral", "Agree", "Strongly Agree"]
    if reply_type == "emoji":
        return ["😞 Terrible", "😕 Meh", "😐 Okay", "😊 Good", "🤩 Amazing"]
    if reply_type == "thumbs":
        return ["👍 Thumbs up", "👎 Thumbs down"]
    if reply_type == "true_false":
        return ["True", "False"]
    if reply_type == "time_slot":
        return ["9:00 AM", "10:30 AM", "12:00 PM", "2:00 PM", "3:30 PM", "5:00 PM"]
    if reply_type in {"text", "long_text", "contact", "date", "slider"}:
        return []
    return ["Yes", "No"]


def _is_platform_brand(name: str) -> bool:
    return bool(re.search(r"voxbulk|retover", str(name or ""), re.I))


def _scrub_recipient_script(text: str, *, organisation_name: str, organiser_name: str) -> str:
    org = organisation_name.strip() or "your business"
    organiser = organiser_name.strip() or org
    if not text:
        return text
    out = str(text)
    replacements = [
        (r"\[Your Name\]", organiser),
        (r"\[your name\]", organiser),
        (r"\[Clinic/Business Name\]", org),
        (r"\[Clinic Name\]", org),
        (r"\[Business Name\]", org),
        (r"\[Company Name\]", org),
        (r"\[Organisation Name\]", org),
    ]
    for pattern, value in replacements:
        out = re.sub(pattern, value, out, flags=re.I)
    out = re.sub(r"\bVOXBULK\b", org, out, flags=re.I)
    out = re.sub(r"\bfrom VOXBULK\b", f"from {org}", out, flags=re.I)
    out = re.sub(r"\bon behalf of VOXBULK\b", f"on behalf of {org}", out, flags=re.I)
    return out


def _intro_is_invalid(intro: str) -> bool:
    low = str(intro or "").lower()
    if not low.strip():
        return True
    bad = ("voxbulk", "[your", "[clinic", "[business", "your name", "[company", "[organisation")
    return any(token in low for token in bad)


def _build_phone_intro(*, organisation_name: str, organiser_name: str) -> str:
    org = organisation_name.strip() or "your business"
    organiser = organiser_name.strip() or org
    return (
        f"Hello, this is {organiser} from {org}. "
        f"I'm calling on behalf of {org} to get your quick feedback. "
        "This call may be recorded for quality and training purposes. "
        "It'll only take a minute or two."
    )


def _apply_org_placeholders(text: str, *, organisation_name: str, assistant_name: str) -> str:
    org = organisation_name.strip()
    assistant = assistant_name.strip() or org
    if not text:
        return text
    out = str(text)
    if org:
        for key in ("clinic_name", "organisation_name", "business_name"):
            out = out.replace(f"{{{key}}}", org)
    if assistant:
        out = out.replace("{assistant_name}", assistant)
    return out


def _materialise_script_result(data: dict, *, organisation_name: str, assistant_name: str, organiser_name: str = "") -> dict:
    org = organisation_name.strip()
    organiser = (organiser_name or assistant_name).strip() or org
    out = dict(data)

    intro = str(out.get("intro") or "")
    if _intro_is_invalid(intro):
        intro = _build_phone_intro(organisation_name=org, organiser_name=organiser)
    else:
        intro = _scrub_recipient_script(intro, organisation_name=org, organiser_name=organiser)
    out["intro"] = _apply_org_placeholders(intro, organisation_name=org, assistant_name=organiser)

    for field in ("closing", "system_prompt"):
        if out.get(field):
            cleaned = _scrub_recipient_script(str(out[field]), organisation_name=org, organiser_name=organiser)
            out[field] = _apply_org_placeholders(cleaned, organisation_name=org, assistant_name=organiser)

    questions = out.get("questions") or []
    if isinstance(questions, list):
        out["questions"] = [
            _apply_org_placeholders(
                _scrub_recipient_script(str(q), organisation_name=org, organiser_name=organiser),
                organisation_name=org,
                assistant_name=organiser,
            )
            for q in questions
        ]

    script_text = str(out.get("script_text") or "").strip()
    if script_text:
        script_text = _scrub_recipient_script(script_text, organisation_name=org, organiser_name=organiser)
        script_text = _apply_org_placeholders(script_text, organisation_name=org, assistant_name=organiser)
        intro_block = re.search(r"INTRO\s*\r?\n([\s\S]*?)(?=\r?\n\s*QUESTIONS|\r?\n\s*CLOSING|$)", script_text, re.I)
        if not intro_block or _intro_is_invalid(intro_block.group(1)):
            script_text = _format_script(out["intro"], out["questions"], str(out.get("closing") or ""))
        out["script_text"] = script_text
    else:
        out["script_text"] = _format_script(out["intro"], out.get("questions") or [], str(out.get("closing") or ""))

    wa = out.get("whatsapp_flow")
    if isinstance(wa, dict):
        wa_out = dict(wa)
        for field in ("intro", "closing"):
            if wa_out.get(field):
                cleaned = _scrub_recipient_script(str(wa_out[field]), organisation_name=org, organiser_name=organiser)
                wa_out[field] = _apply_org_placeholders(cleaned, organisation_name=org, assistant_name=organiser)
            elif field == "intro":
                wa_out["intro"] = (
                    f"Hi {{first_name}}, we're running a quick survey for {org} on WhatsApp. "
                    "It takes about 2 minutes — reply to each question below."
                )
        qs = wa_out.get("questions")
        if isinstance(qs, list):
            wa_out["questions"] = [
                {
                    **q,
                    "text": _apply_org_placeholders(
                        _scrub_recipient_script(str(q.get("text") or ""), organisation_name=org, organiser_name=organiser),
                        organisation_name=org,
                        assistant_name=organiser,
                    ),
                }
                if isinstance(q, dict)
                else _apply_org_placeholders(
                    _scrub_recipient_script(str(q), organisation_name=org, organiser_name=organiser),
                    organisation_name=org,
                    assistant_name=organiser,
                )
                for q in qs
            ]
        out["whatsapp_flow"] = wa_out
    return out


def _brand_context_block(*, organisation_name: str, assistant_name: str, organiser_name: str = "", terminology_label: str = "customer") -> str:
    org = organisation_name.strip() or "the client organisation"
    organiser = (organiser_name or assistant_name).strip() or org
    term = terminology_label.strip() or "customer"
    return (
        f"Client organisation (company name): {org}\n"
        f"Survey organiser (caller name): {organiser}\n"
        f"Refer to recipients as {term}s.\n"
        f"MANDATORY phone intro format (use these exact names, no placeholders):\n"
        f"\"Hello, this is {organiser} from {org}. I'm calling on behalf of {org} to get your quick feedback...\"\n"
        f"NEVER use [Your Name], [Clinic/Business Name], VOXBULK, Voxbulk, or any platform name.\n"
        f"NEVER invent example business names — only use {org} and {organiser}.\n"
        f"WhatsApp intro must greet {{first_name}} and name {org} directly.\n"
        f"Only {{first_name}} may remain as a merge field for each contact.\n"
    )


def _build_whatsapp_flow(intro: str, questions: list[str], closing: str, data: dict | None = None, *, organisation_name: str = "") -> dict:
    payload = data or {}
    wa_intro = str(payload.get("whatsapp_intro") or "").strip()
    wa_closing = str(payload.get("whatsapp_closing") or "").strip()
    wa_questions_raw = payload.get("whatsapp_questions") or []

    if not wa_intro:
        org_label = organisation_name.strip() or "{clinic_name}"
        wa_intro = (
            f"Hi {{first_name}}, we're running a quick survey for {org_label} on WhatsApp. "
            "It takes about 2 minutes — reply to each question below."
        )
    if not wa_closing:
        wa_closing = closing or "Thank you for your feedback — we really appreciate it."

    wa_questions: list[dict] = []
    if isinstance(wa_questions_raw, list) and wa_questions_raw:
        for item in wa_questions_raw:
            if not isinstance(item, dict):
                continue
            text = str(item.get("text") or "").strip()
            if not text:
                continue
            reply_type = str(item.get("reply_type") or "buttons").strip().lower()
            if reply_type not in {
                "buttons", "rating", "text", "nps", "likert", "slider", "single_choice",
                "multi", "true_false", "long_text", "emoji", "thumbs", "time_slot", "date", "contact",
            }:
                reply_type = _guess_reply_type(text)
            options_raw = item.get("options") or []
            options = [str(o).strip() for o in options_raw if str(o).strip()] if isinstance(options_raw, list) else []
            if reply_type != "text" and not options:
                options = _default_options(reply_type)
            wa_questions.append({"text": text, "reply_type": reply_type, "options": options})

    if not wa_questions:
        for q in questions:
            reply_type = _guess_reply_type(q)
            wa_questions.append({"text": q, "reply_type": reply_type, "options": _default_options(reply_type)})

    return {"intro": wa_intro, "questions": wa_questions, "closing": wa_closing}


def _parse_script_payload(
    raw: str,
    *,
    include_whatsapp: bool = False,
    organisation_name: str = "",
    assistant_name: str = "",
    organiser_name: str = "",
) -> dict:
    data = _extract_json_object(raw)
    intro = str(data.get("intro") or "").strip()
    closing = str(data.get("closing") or "").strip()
    questions_raw = data.get("questions") or []
    if not isinstance(questions_raw, list):
        raise ValueError("questions must be an array")
    questions = [str(q).strip() for q in questions_raw if str(q).strip()]
    if include_whatsapp:
        wa_flow = _build_whatsapp_flow(intro, questions, closing, data, organisation_name=organisation_name)
        if not wa_flow["questions"]:
            raise ValueError("Generated WhatsApp survey must include questions")
        intro = intro or wa_flow["intro"]
        closing = closing or wa_flow["closing"]
    if not intro or not questions or not closing:
        raise ValueError("Generated script must include intro, questions, and closing")
    script_text = str(data.get("script_text") or "").strip() or _format_script(intro, questions, closing)
    system_prompt = str(data.get("system_prompt") or "").strip()
    if not system_prompt:
        system_prompt = f"Follow this approved script closely.\n\n{script_text}"
    out = {
        "intro": intro,
        "questions": questions,
        "closing": closing,
        "script_text": script_text,
        "system_prompt": system_prompt,
    }
    if include_whatsapp:
        out["whatsapp_flow"] = _build_whatsapp_flow(intro, questions, closing, data, organisation_name=organisation_name)
    return _materialise_script_result(
        out,
        organisation_name=organisation_name,
        assistant_name=assistant_name,
        organiser_name=organiser_name,
    )


def _complete_json(db: Session, *, meta: str, user: str) -> str:
    result = OpenAIProviderService.complete(
        db,
        system_prompt=meta,
        messages=[AgentMessage(role="user", content=user)],
        max_tokens=2500,
        temperature=0.45,
        provider="deepseek",
    )
    return result.assistant_text


def generate_survey_script(
    db: Session,
    *,
    goal: str,
    contact_method: str = "AI phone call",
    max_call_length: str = "3 minutes",
    organisation_name: str = "",
    assistant_name: str = "",
    organiser_name: str = "",
    terminology_label: str = "customer",
) -> dict:
    goal_text = str(goal or "").strip() or "General customer satisfaction"
    uses_whatsapp = "whatsapp" in str(contact_method or "").lower()
    meta = _SURVEY_WA_META if uses_whatsapp else _SURVEY_META
    brand = _brand_context_block(
        organisation_name=organisation_name,
        assistant_name=assistant_name,
        organiser_name=organiser_name,
        terminology_label=terminology_label,
    )
    channel_note = (
        "Design primarily for WhatsApp interactive quick replies. Also include phone script fields."
        if uses_whatsapp
        else "Write a concise survey script the customer can read and approve before launch."
    )
    user = (
        f"{brand}\n"
        f"Survey goal:\n{goal_text}\n\n"
        f"Contact method: {contact_method}\n"
        f"Max call length: {max_call_length}\n\n"
        f"{channel_note}"
    )
    raw = _complete_json(db, meta=meta, user=user)
    return _parse_script_payload(
        raw,
        include_whatsapp=uses_whatsapp,
        organisation_name=organisation_name,
        assistant_name=assistant_name,
        organiser_name=organiser_name,
    )


def generate_interview_script(
    db: Session,
    *,
    role: str,
    criteria: str,
    delivery: str = "ai_call",
    organisation_name: str = "",
    assistant_name: str = "",
    organiser_name: str = "",
) -> dict:
    role_text = str(role or "").strip() or "Open role"
    criteria_text = str(criteria or "").strip() or "General screening"
    channel = "Zoom video interview with AI" if str(delivery).lower() == "zoom" else "AI phone call"
    brand = _brand_context_block(
        organisation_name=organisation_name,
        assistant_name=assistant_name,
        organiser_name=organiser_name,
        terminology_label="candidate",
    )
    user = (
        f"{brand}\n"
        f"Role / position:\n{role_text}\n\n"
        f"Screening criteria:\n{criteria_text}\n\n"
        f"Delivery: {channel}\n\n"
        "Write screening questions the customer can read and approve before launch."
    )
    raw = _complete_json(db, meta=_INTERVIEW_META, user=user)
    return _parse_script_payload(
        raw,
        organisation_name=organisation_name,
        assistant_name=assistant_name,
        organiser_name=organiser_name,
    )
